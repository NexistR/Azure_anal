"""Versioned, lossless Telco cleaning for Week 3.

The raw CSV remains untouched. This transformer validates the data contract,
normalizes representation, and adds traceable flags. It learns no population
statistics, imputes no missing money, and neither drops nor caps observations.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "w3_cleaning.json"
DERIVED_COLUMNS = (
    "churn_label", "total_charges_missing", "tenure_zero", "internet_applicable"
)


def load_config(path: str | Path | None = None) -> dict:
    """Read an independent config; data/output paths are relative to project root."""
    config_path = DEFAULT_CONFIG if path is None else Path(path).expanduser().resolve()
    with config_path.open(encoding="utf-8-sig") as handle:
        config = json.load(handle)
    _validate_config(config)
    return config


def _resolve_config(config=None) -> dict:
    if config is None:
        return load_config()
    if isinstance(config, (str, Path)):
        return load_config(config)
    if not isinstance(config, Mapping):
        raise ValueError("config must be a dictionary, a JSON path, or None")
    result = copy.deepcopy(dict(config))
    _validate_config(result)
    return result


def _validate_config(config: dict) -> None:
    """Fail early if configuration could undermine the schema or leakage boundary."""
    required = {
        "version", "seed", "test_size", "input_path", "output_dir", "model_dir",
        "expected_sha256", "raw_columns", "derived_columns", "categories",
        "numeric_rules", "allowed_nulls", "label_mapping", "features",
        "internet_service_columns", "structural_categories", "preprocessing",
    }
    if not isinstance(config, dict) or required - config.keys():
        missing = required - config.keys() if isinstance(config, dict) else required
        raise ValueError(f"Configuration is missing required keys: {sorted(missing)}")
    raw = config["raw_columns"]
    if not isinstance(raw, list) or len(raw) != 21 or len(set(raw)) != 21:
        raise ValueError("raw_columns must contain exactly 21 unique Telco fields")
    fixed = {
        "customerID", "gender", "SeniorCitizen", "Partner", "Dependents", "tenure",
        "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity",
        "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV",
        "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod",
        "MonthlyCharges", "TotalCharges", "Churn",
    }
    if set(raw) != fixed:
        raise ValueError("raw_columns must describe the Telco 21-field data contract")
    if config["derived_columns"] != list(DERIVED_COLUMNS):
        raise ValueError(f"derived_columns must be {list(DERIVED_COLUMNS)}")
    if config["allowed_nulls"] != ["TotalCharges"]:
        raise ValueError("Only TotalCharges may contain missing values")
    if config["label_mapping"] != {"No": 0, "Yes": 1}:
        raise ValueError("label_mapping must preserve No=0 and Yes=1")
    if not isinstance(config["seed"], int) or isinstance(config["seed"], bool):
        raise ValueError("seed must be an integer")
    if not isinstance(config["test_size"], (int, float)) or not 0 < config["test_size"] < 1:
        raise ValueError("test_size must be strictly between 0 and 1")
    expected_categories = fixed - {"customerID", "tenure", "MonthlyCharges", "TotalCharges"}
    if set(config["categories"]) != expected_categories:
        raise ValueError("categories must define every Telco category, including Churn")
    for name, values in config["categories"].items():
        if not isinstance(values, list) or not values:
            raise ValueError(f"categories.{name} must be a nonempty list of unique values")
        if name == "SeniorCitizen":
            if any(type(value) is not int for value in values) or values != [0, 1]:
                raise ValueError("SeniorCitizen categories must explicitly be integer [0, 1]")
        elif any(not isinstance(value, str) or not value or value != value.strip() for value in values):
            raise ValueError(f"categories.{name} must contain only nonempty, trimmed strings; no null categories")
        if len(values) != len(set(values)):
            raise ValueError(f"categories.{name} must be a nonempty list of unique values")
    if set(config["categories"]["Churn"]) != {"No", "Yes"}:
        raise ValueError("Churn categories must preserve Yes and No")
    if config["categories"]["SeniorCitizen"] != [0, 1]:
        raise ValueError("SeniorCitizen categories must explicitly be [0, 1]")
    if set(config["numeric_rules"]) != {"SeniorCitizen", "tenure", "MonthlyCharges", "TotalCharges"}:
        raise ValueError("numeric_rules must describe SeniorCitizen, tenure and both charges")
    for name, rule in config["numeric_rules"].items():
        if not isinstance(rule, dict) or not {"integer", "minimum", "minimum_inclusive", "maximum"} <= rule.keys():
            raise ValueError(f"numeric_rules.{name} lacks integer/minimum/minimum_inclusive/maximum")
        for flag in ("integer", "minimum_inclusive"):
            if type(rule[flag]) is not bool:
                raise ValueError(f"numeric_rules.{name}.{flag} must be a JSON boolean (true/false)")
        expected_integer = name in {"SeniorCitizen", "tenure"}
        if rule["integer"] != expected_integer:
            raise ValueError(f"numeric_rules.{name}.integer must be {expected_integer} to preserve the output data type")
        for bound in ("minimum", "maximum"):
            value = rule[bound]
            if value is None:
                continue
            try:
                valid_bound = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                valid_bound = False
            if not valid_bound:
                raise ValueError(f"numeric_rules.{name}.{bound} must be a finite JSON number or null")
        lower, upper = rule["minimum"], rule["maximum"]
        if lower is not None and upper is not None:
            if lower > upper or (lower == upper and not rule["minimum_inclusive"]):
                raise ValueError(f"numeric_rules.{name} has an empty or reversed minimum/maximum range")
        if rule["integer"]:
            lowest = Decimal(-(2**63))
            highest = Decimal(2**63 - 1)
            if lower is not None:
                lower_decimal = Decimal(str(lower))
                first = lower_decimal.to_integral_value(rounding=ROUND_CEILING) if rule["minimum_inclusive"] else lower_decimal.to_integral_value(rounding=ROUND_FLOOR) + 1
                lowest = max(lowest, first)
            if upper is not None:
                highest = min(highest, Decimal(str(upper)).to_integral_value(rounding=ROUND_FLOOR))
            if lowest > highest:
                raise ValueError(f"numeric_rules.{name} range contains no representable int64 integer")
    expected_services = {"OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"}
    if set(config["internet_service_columns"]) != expected_services:
        raise ValueError("internet_service_columns must identify all six add-on services")
    expected_structural = {"no_internet": "No", "internet_not_applicable": "No internet service", "no_phone": "No", "phone_not_applicable": "No phone service"}
    if config["structural_categories"] != expected_structural:
        raise ValueError("structural_categories must preserve the original Telco meanings")
    features = config["features"]
    if not isinstance(features, dict) or set(features) != {"numeric", "categorical", "binary"}:
        raise ValueError("features must specify numeric, categorical and binary lists")
    if any(not isinstance(v, list) or not v for v in features.values()):
        raise ValueError("Each feature group must be a nonempty list")
    names = features["numeric"] + features["categorical"] + features["binary"]
    if len(names) != len(set(names)):
        raise ValueError("Feature lists must not overlap or contain duplicate columns")
    if set(features["numeric"]) != {"tenure", "MonthlyCharges", "TotalCharges"}:
        raise ValueError("numeric features must be tenure, MonthlyCharges and TotalCharges")
    if set(features["categorical"]) != expected_categories - {"Churn"}:
        raise ValueError("categorical features must include the 16 predictors and exclude Churn")
    if set(features["binary"]) != set(DERIVED_COLUMNS) - {"churn_label"}:
        raise ValueError("binary features must be the three non-label cleaning flags")
    preprocessing = config["preprocessing"]
    required_preprocessing = {
        "numeric_imputation": "training_median",
        "all_missing_training_column_fallback": 0.0,
        "keep_empty_features": True,
        "numeric_scaling": "training_standard_scaler",
        "unknown_category_policy": "error",
    }
    if preprocessing != required_preprocessing:
        raise ValueError(f"Supported preprocessing settings are {required_preprocessing}")


def read_raw(path: str | Path) -> pd.DataFrame:
    """Read CSV fields literally, retaining empty/whitespace fields for auditing."""
    return pd.read_csv(Path(path), dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _fail_rows(field: str, reason: str, mask: pd.Series) -> None:
    """Describe the field/rule and row positions without leaking customer IDs."""
    hits = np.flatnonzero(mask.to_numpy(dtype=bool))
    if len(hits):
        raise ValueError(f"{field}: {reason}; {len(hits)} row(s), positions {hits[:5].tolist()}")


def _parse_numeric(series: pd.Series, field: str, config: dict) -> pd.Series:
    missing = series.isna() | series.eq("").fillna(False)
    if field not in config["allowed_nulls"]:
        _fail_rows(field, "missing or blank numeric values are not allowed", missing)
    _fail_rows(field, "boolean values are not valid numbers", series.map(lambda value: isinstance(value, (bool, np.bool_))))
    _fail_rows(field, "complex values are not valid real numbers", series.map(lambda value: isinstance(value, (complex, np.complexfloating))))
    rule = config["numeric_rules"][field]
    if rule["integer"]:
        # Parse each integer independently: a float elsewhere in the column must
        # not coerce a large exact string integer through float64. Decimal also
        # distinguishes 9007199254740992.5 from its rounded float representation.
        parsed = []
        errors = {
            "nonempty value cannot be parsed as a number": [],
            "infinite or non-finite values are not allowed": [],
            "must be an integer": [],
            "integer is outside int64 representation": [],
        }
        minimum = Decimal(str(rule["minimum"])) if rule["minimum"] is not None else None
        maximum = Decimal(str(rule["maximum"])) if rule["maximum"] is not None else None
        below, above = [], []
        for position, value in enumerate(series):
            try:
                number = Decimal(str(value))
            except (InvalidOperation, ValueError):
                errors["nonempty value cannot be parsed as a number"].append(position)
                parsed.append(0)
                continue
            if not number.is_finite():
                errors["infinite or non-finite values are not allowed"].append(position)
            elif number != number.to_integral_value():
                errors["must be an integer"].append(position)
            elif not -(2**63) <= number <= 2**63 - 1:
                errors["integer is outside int64 representation"].append(position)
            else:
                if minimum is not None and (number < minimum if rule["minimum_inclusive"] else number <= minimum):
                    below.append(position)
                if maximum is not None and number > maximum:
                    above.append(position)
                parsed.append(int(number))
                continue
            parsed.append(0)
        for reason, positions in errors.items():
            if positions:
                mask = np.zeros(len(series), dtype=bool)
                mask[positions] = True
                _fail_rows(field, reason, pd.Series(mask, index=series.index))
        for positions, reason in (
            (below, f"must be {'>=' if rule['minimum_inclusive'] else '>'} {rule['minimum']}"),
            (above, f"must be <= {rule['maximum']}"),
        ):
            if positions:
                mask = np.zeros(len(series), dtype=bool)
                mask[positions] = True
                _fail_rows(field, reason, pd.Series(mask, index=series.index))
        return pd.Series(parsed, index=series.index, name=series.name, dtype="int64")
    try:
        values = pd.to_numeric(series.mask(missing, np.nan), errors="coerce")
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{field}: cannot convert values to real numbers") from error
    _fail_rows(field, "nonempty value cannot be parsed as a number", ~missing & values.isna())
    _fail_rows(field, "infinite or non-finite values are not allowed", values.notna() & ~np.isfinite(values))
    minimum = rule["minimum"]
    if minimum is not None:
        invalid = values.lt(minimum) if rule["minimum_inclusive"] else values.le(minimum)
        symbol = ">=" if rule["minimum_inclusive"] else ">"
        _fail_rows(field, f"must be {symbol} {minimum}", invalid)
    if rule["maximum"] is not None:
        _fail_rows(field, f"must be <= {rule['maximum']}", values.gt(rule["maximum"]))
    return values.astype("float64")


def _clean_frame(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("TelcoCleaner requires a pandas DataFrame with named columns")
    if not all(isinstance(name, str) for name in frame.columns):
        raise ValueError("Schema column names must all be strings")
    if frame.columns.duplicated().any():
        raise ValueError("Schema has duplicate column names")
    if frame.empty:
        raise ValueError("Telco input must contain at least one row")
    raw_columns = config["raw_columns"]
    derived_columns = config["derived_columns"]
    actual = set(frame.columns)
    raw_set = set(raw_columns)
    complete_set = raw_set | set(derived_columns)
    if actual not in (raw_set, complete_set):
        raise ValueError(
            "Schema must contain exactly the 21 raw columns or all 25 cleaned columns; "
            f"missing raw={sorted(raw_set - actual)}, extra={sorted(actual - complete_set)}, "
            f"partial derived={sorted(actual & set(derived_columns))}"
        )
    result = frame.loc[:, raw_columns].copy(deep=True)
    for name in result.columns:
        result[name] = result[name].map(lambda value: value.strip() if isinstance(value, str) else value)
    id_values = result["customerID"]
    _fail_rows("customerID", "must be a nonempty string", id_values.map(lambda value: not isinstance(value, str) or not value))
    _fail_rows("customerID", "must be unique after trimming whitespace", id_values.duplicated(keep=False))
    for name in config["numeric_rules"]:
        result[name] = _parse_numeric(result[name], name, config)
    for name, allowed in config["categories"].items():
        _fail_rows(name, f"unknown/missing category; allowed={allowed}", ~result[name].isin(allowed))
        if name != "SeniorCitizen":
            result[name] = result[name].astype(object)
    structural = config["structural_categories"]
    no_internet = result["InternetService"].eq(structural["no_internet"])
    for name in config["internet_service_columns"]:
        invalid = no_internet.ne(result[name].eq(structural["internet_not_applicable"]))
        _fail_rows(name, "contradicts InternetService applicability", invalid)
    no_phone = result["PhoneService"].eq(structural["no_phone"])
    _fail_rows("MultipleLines", "contradicts PhoneService applicability", no_phone.ne(result["MultipleLines"].eq(structural["phone_not_applicable"])))
    for name in raw_columns:
        if name not in config["allowed_nulls"]:
            _fail_rows(name, "null values are not allowed", result[name].isna())
    result["churn_label"] = result["Churn"].map(config["label_mapping"]).astype("int64")
    result["total_charges_missing"] = result["TotalCharges"].isna().astype("int64")
    result["tenure_zero"] = result["tenure"].eq(0).astype("int64")
    result["internet_applicable"] = (~no_internet).astype("int64")
    if actual == complete_set:
        for name in derived_columns:
            supplied = frame[name]
            _fail_rows(name, "derived flag must agree with its source field", supplied.isna() | supplied.ne(result[name]))
    return result.loc[:, raw_columns + derived_columns]


class TelcoCleaner(TransformerMixin, BaseEstimator):
    """Strict schema normalization with sklearn fit/transform and stable output.

    Call ``fit_transform(raw)`` first. ``transform(cleaned)`` is idempotent;
    inconsistent pre-existing derived flags fail rather than being overwritten.
    ``fit`` freezes a private copy of the configuration and learns no statistics.
    """

    def __init__(self, config=None):
        self.config = config

    def fit(self, X: pd.DataFrame, y=None):
        config = _resolve_config(self.config)
        _clean_frame(X, config)
        self.config_ = config
        self.n_features_in_ = X.shape[1]
        self.feature_names_in_ = np.asarray(X.columns, dtype=object)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, "config_")
        return _clean_frame(X, self.config_)

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        check_is_fitted(self, "config_")
        if input_features is not None and list(input_features) != list(self.feature_names_in_):
            raise ValueError("input_features must match the fitted input column names")
        return np.asarray(self.config_["raw_columns"] + self.config_["derived_columns"], dtype=object)
