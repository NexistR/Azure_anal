"""The frozen 22-field contract with a vectorized typed-numeric fast path.

Object/extension dtypes and large floating-point integers use the original
Decimal-aware parser. No input rows, categories or applicability checks are
discarded to gain speed. Caller-owned frames are never modified.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _fail(field, reason, mask):
    positions = np.flatnonzero(np.asarray(mask, dtype=bool))
    if positions.size:
        raise ValueError(
            f"{field}: {reason}; {len(positions)} row(s), positions {positions[:5].tolist()}"
        )


def _numeric(series, field, config):
    dtype = series.dtype
    rule = config["numeric_rules"][field]
    # Only plain NumPy real-number arrays enter the fast path. This excludes
    # bool, complex, object, datetime and nullable extension dtypes.
    plain = isinstance(dtype, np.dtype) and dtype.kind in "iuf"
    if plain and rule["integer"] and dtype.kind == "f":
        values = series.to_numpy(copy=False)
        # Decimal(str(float)) is the inherited contract for large floats.
        plain = not np.any(np.abs(values) >= 2**53)
    if not plain:
        from src.data.clean import _parse_numeric
        return _parse_numeric(series, field, config)

    values = series.to_numpy(copy=False)
    missing = np.isnan(values) if dtype.kind == "f" else np.zeros(len(values), dtype=bool)
    if field not in config["allowed_nulls"]:
        _fail(field, "missing or blank numeric values are not allowed", missing)
    _fail(field, "infinite or non-finite values are not allowed", ~missing & ~np.isfinite(values))
    if rule["integer"]:
        if dtype.kind == "f":
            _fail(field, "must be an integer", ~missing & (values != np.floor(values)))
        if dtype.kind == "u":
            _fail(field, "integer is outside int64 representation", values > np.iinfo(np.int64).max)
    lower, upper = rule["minimum"], rule["maximum"]
    if lower is not None:
        bad = values < lower if rule["minimum_inclusive"] else values <= lower
        _fail(field, "numeric minimum violated", bad)
    if upper is not None:
        _fail(field, "numeric maximum violated", values > upper)
    return series.astype("int64" if rule["integer"] else "float64", copy=False)


def validate_frame(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Match FeatureContract acceptance without copying all object blocks twice."""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Preprocessor requires a pandas DataFrame with feature names")
    if not all(isinstance(name, str) for name in frame.columns):
        raise ValueError("Feature column names must all be strings")
    if frame.columns.duplicated().any():
        raise ValueError("Feature schema has duplicate column names")
    groups = config["features"]
    expected = groups["numeric"] + groups["categorical"] + groups["binary"]
    actual = set(frame.columns)
    if actual != set(expected):
        raise ValueError(
            f"Feature whitelist violation; missing={sorted(set(expected) - actual)}, "
            f"extra={sorted(actual - set(expected))}. "
            "customerID, Churn, churn_label and unregistered fields are forbidden."
        )
    if frame.empty:
        raise ValueError("Preprocessor needs at least one row")
    result = frame.loc[:, expected].copy(deep=False)
    for name in config["numeric_rules"]:
        result[name] = _numeric(result[name], name, config)
    for name in groups["categorical"]:
        _fail(name, "unknown/missing category", ~result[name].isin(config["categories"][name]).to_numpy())
    for name in groups["binary"]:
        _fail(name, "cleaning flag must be numeric 0 or 1", ~result[name].isin([0, 1]).to_numpy())
        result[name] = result[name].astype("int64", copy=False)
    structural = config["structural_categories"]
    no_internet = result["InternetService"].to_numpy() == structural["no_internet"]
    for name in config["internet_service_columns"]:
        not_applicable = result[name].to_numpy() == structural["internet_not_applicable"]
        _fail(name, "contradicts InternetService applicability", no_internet != not_applicable)
    no_phone = result["PhoneService"].to_numpy() == structural["no_phone"]
    _fail("MultipleLines", "contradicts PhoneService applicability",
          no_phone != (result["MultipleLines"].to_numpy() == structural["phone_not_applicable"]))
    checks = {
        "total_charges_missing": result["TotalCharges"].isna().to_numpy(),
        "tenure_zero": result["tenure"].to_numpy() == 0,
        "internet_applicable": ~no_internet,
    }
    for name, computed in checks.items():
        _fail(name, "derived flag must agree with its source field", result[name].to_numpy() != computed)
    return result
