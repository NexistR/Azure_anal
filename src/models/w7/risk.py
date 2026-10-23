"""Prespecified risk tiers and descriptive diagnostics for frozen W7 scores.

This module accepts probabilities; it never loads, fits or recalibrates a model.
The 0.10 operational boundary is not an empirically optimal threshold.  The
0.30 boundary exactly preserves the historical positive decision convention.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "w7_risk.json"
RISK_ORDER = ("low", "medium", "high")
RISK_LABELS = {"low": "低", "medium": "中", "high": "高"}
Z_95 = 1.959963984540054


@dataclass(frozen=True)
class RiskConfig:
    low_upper: float
    high_lower: float
    classification_threshold: float
    score_multiplier: float
    display_decimals: int
    calibration_bins: int
    actions: dict[str, str]
    metadata: dict[str, Any]


def load_config(path: str | Path | None = None) -> RiskConfig:
    """Read the fixed protocol, rejecting changes to its numerical contract."""
    data = json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("risk configuration must be a JSON object")
    fixed = {"schema_version": 1, "low_upper_exclusive": .10,
             "high_lower_inclusive": .30, "classification_threshold": .30,
             "score_multiplier": 100., "display_decimals": 1,
             "calibration_bins": 10, "wilson_confidence": .95}
    for key, value in fixed.items():
        if isinstance(data.get(key), bool) or data.get(key) != value:
            raise ValueError(f"risk protocol changed: {key}; expected {value}")
    actions = data.get("actions")
    if not isinstance(actions, dict) or set(actions) != set(RISK_ORDER):
        raise ValueError("actions must contain exactly low, medium and high")
    if any(not isinstance(v, str) or not v.strip() for v in actions.values()):
        raise ValueError("actions must contain nonempty text")
    if data.get("risk_labels") != RISK_LABELS:
        raise ValueError("risk_labels must preserve the low/medium/high Chinese label mapping")
    return RiskConfig(.10, .30, .30, 100., 1, 10, dict(actions), data)


def validate_probabilities(probabilities: Any) -> np.ndarray:
    """Return a 1-D float64 copy of finite numeric probabilities in [0, 1].

    Strings, booleans, scalars, matrices and missing values are rejected rather
    than coerced.  Empty vectors are permitted for empty inference results.
    Casting float32 to float64 preserves each supplied value exactly.
    """
    # Inspect Python containers before NumPy could promote True alongside .2
    # to numeric 1.0.  Already typed numeric arrays have no boolean elements.
    if not isinstance(probabilities, (np.ndarray, pd.Series)):
        uncoerced = np.asarray(probabilities, dtype=object)
        if any(isinstance(v, (bool, np.bool_)) for v in uncoerced.flat):
            raise ValueError("boolean probabilities are not accepted")
    values = np.asarray(probabilities)
    if values.ndim != 1:
        raise ValueError("probabilities must be a one-dimensional vector")
    if values.dtype.kind not in "iuf":
        raise ValueError("probabilities must contain numeric, non-boolean values")
    result = values.astype(np.float64, copy=True)
    if not np.isfinite(result).all() or ((result < 0) | (result > 1)).any():
        raise ValueError("probabilities must be finite and within [0, 1]")
    return result


def score_frame(frame: pd.DataFrame, p_col: str = "p",
                config: RiskConfig | None = None) -> pd.DataFrame:
    """Copy a frame and attach unrounded score, tier and frozen decision.

    All original columns and row/index order are retained.  The named derived
    columns are recomputed from p; display rounding never enters tier logic.
    Customer IDs and labels, when present, do not participate in scoring.
    """
    cfg = config or load_config()
    if not isinstance(frame, pd.DataFrame) or not frame.columns.is_unique:
        raise ValueError("frame must be a DataFrame with unique column names")
    if p_col not in frame:
        raise ValueError(f"missing probability column: {p_col}")
    p = validate_probabilities(frame[p_col].to_numpy())
    result = frame.copy(deep=True)
    result["score"] = p * cfg.score_multiplier
    result["risk"] = np.where(p < cfg.low_upper, "low",
                              np.where(p < cfg.high_lower, "medium", "high"))
    result["risk_label"] = result["risk"].map(RISK_LABELS)
    result["prediction"] = (p >= cfg.classification_threshold).astype(np.int64)
    return result


def wilson_interval(positive: int, count: int) -> tuple[float | None, float | None]:
    """Two-sided 95% Wilson interval for an observed binary fraction."""
    if isinstance(count, bool) or isinstance(positive, bool):
        raise ValueError("Wilson counts must be integers")
    if int(count) != count or int(positive) != positive or not 0 <= positive <= count:
        raise ValueError("Wilson counts must satisfy 0 <= positive <= count")
    if count == 0:
        return None, None
    rate = positive / count
    denominator = 1. + Z_95 ** 2 / count
    center = (rate + Z_95 ** 2 / (2. * count)) / denominator
    half = Z_95 * np.sqrt(rate * (1. - rate) / count + Z_95 ** 2 / (4. * count ** 2)) / denominator
    return max(0., float(center - half)), min(1., float(center + half))


def summarize_scores(frame: pd.DataFrame, split: str,
                     config: RiskConfig | None = None,
                     p_col: str = "p", y_col: str = "y") -> dict[str, Any]:
    """Describe one allowed partition, with no fitting or threshold selection.

    ECE uses ten prespecified equal-width bins, left-closed/right-open except
    the last bin includes 1.  Empty-bin rate/CI remain unavailable, not zero.
    Wilson intervals are descriptive binomial intervals, not calibration or
    transport guarantees.  Train diagnostics are in-sample and optimistic.
    """
    if split not in ("train", "validation"):
        raise ValueError("only train and validation diagnostics are authorized")
    cfg = config or load_config()
    scored = score_frame(frame, p_col, cfg)
    if scored.empty:
        raise ValueError("diagnostics require at least one row")
    if "split" in scored and not scored["split"].eq(split).all():
        raise ValueError("partition rows disagree with the requested split")
    if y_col not in scored:
        raise ValueError(f"missing observed label column: {y_col}")
    y = np.asarray(scored[y_col])
    if y.dtype.kind not in "iufb" or not np.isin(y, [0, 1]).all():
        raise ValueError("observed labels must be binary 0/1 without missing values")
    y = y.astype(np.int64)
    p = validate_probabilities(scored[p_col])
    n, positives = len(p), int(y.sum())
    base_rate = positives / n
    groups = []
    for name in RISK_ORDER:
        mask = scored["risk"].eq(name).to_numpy()
        count, positive = int(mask.sum()), int(y[mask].sum())
        rate = positive / count if count else None
        lo, hi = wilson_interval(positive, count)
        groups.append({"split": split, "risk": name, "n": count, "positive": positive,
                       "population_share": count / n,
                       "mean_probability": float(p[mask].mean()) if count else None,
                       "observed_rate": rate, "observed_rate_ci95_low": lo,
                       "observed_rate_ci95_high": hi,
                       "lift": rate / base_rate if count and positives else None,
                       "recall_share": positive / positives if positives else None})
    bins = np.minimum(np.floor(p * cfg.calibration_bins).astype(int), cfg.calibration_bins - 1)
    calibration = []
    ece = 0.
    for k in range(cfg.calibration_bins):
        mask = bins == k
        count, positive = int(mask.sum()), int(y[mask].sum())
        mean_p = float(p[mask].mean()) if count else None
        rate = positive / count if count else None
        gap = abs(rate - mean_p) if count else None
        if count:
            ece += count / n * gap
        lo, hi = wilson_interval(positive, count)
        calibration.append({"split": split, "bin": k, "lower_inclusive": k / cfg.calibration_bins,
                            "upper": (k + 1) / cfg.calibration_bins,
                            "upper_inclusive": k == cfg.calibration_bins - 1,
                            "n": count, "positive": positive, "mean_probability": mean_p,
                            "observed_rate": rate, "absolute_gap": gap,
                            "observed_rate_ci95_low": lo, "observed_rate_ci95_high": hi})
    return {"split": split, "n": n, "positive": positives, "observed_rate": base_rate,
            "mean_probability": float(p.mean()), "brier_score": float(np.mean((p - y) ** 2)),
            "ece_10_equal_width": float(ece), "risk_groups": groups,
            "calibration_bins": calibration,
            "interpretation": ("Fitted-train descriptive diagnostics; optimistic, not OOF."
                               if split == "train" else
                               "Historical validation descriptive diagnostics; not a new independent holdout."),
            "calibration_fitted": False, "threshold_search": False}
