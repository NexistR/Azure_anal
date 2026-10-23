"""Exact path-dependent TreeSHAP for the frozen W7 inference bundle.

All signed attributions and base values have raw binary log-odds units.  Logical
attributions sum the encoded contributions for one logical variable; derived
variables remain separate.  Neither explanation nor ranking fits a model.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shap
import xgboost as xgb

from .runtime import FrozenChurnRuntime


LIMITATIONS = [
    "Tree-path-dependent expectations use the fitted trees' training path counts; no external background sample is fitted.",
    "Correlated raw and derived predictors can share or shift attribution; these associations are not causal effects or intervention estimates.",
    "Logical contributions sum the existing encoded SHAP values, not a separately recomputed 64-player coalition game.",
    "Derived-variable contributions remain assigned to the derived variable; they are not redistributed to its raw input fields.",
    "Signed contributions are log-odds, not additive probability-point changes; apply sigmoid only after summing base and all contributions.",
    "The SHAP TreeExplainer XGBoost shortcut and native pred_contribs share the same underlying implementation; their comparison checks API/configuration agreement, not independent algorithms.",
    "Bootstrap ranking intervals describe resampling of these rows with the frozen model, not model-refit uncertainty or causal confidence intervals.",
]


def _positive_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _sigmoid(values):
    values = np.asarray(values, dtype=np.float64)
    result = np.empty_like(values)
    positive = values >= 0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    negative_exp = np.exp(values[~positive])
    result[~positive] = negative_exp / (1.0 + negative_exp)
    return result


def _feature_mapping(metadata):
    """Use fitted group/category order, never split names on underscores."""
    encoded = list(metadata["output_columns"])
    logical = list(metadata["logical_columns"])
    if len(encoded) != 111 or len(logical) != 64 or len(set(logical)) != 64:
        raise ValueError("Expected the frozen 111-encoded / 64-logical contract")
    rows = []
    for name in metadata["numeric"]["names"]:
        rows.append({"logical_feature": name, "kind": "numeric",
                     "expected_encoded_feature": f"numeric__{name}", "category": None})
    for group in metadata["categorical"]:
        for category in group["categories"]:
            rows.append({"logical_feature": group["name"], "kind": "categorical",
                         "expected_encoded_feature": f"categorical__{group['name']}_{category}",
                         "category": category})
    for name in metadata["binary"]["names"]:
        rows.append({"logical_feature": name, "kind": "binary",
                     "expected_encoded_feature": f"binary__{name}", "category": None})
    if [row["expected_encoded_feature"] for row in rows] != encoded:
        raise ValueError("Fitted output names disagree with numeric/category/binary mapping")
    mapping = {name: [] for name in logical}
    for index, row in enumerate(rows):
        name = row["logical_feature"]
        if name not in mapping:
            raise ValueError(f"Encoded output has unknown logical feature: {name}")
        mapping[name].append(index)
        row["encoded_index"] = index
        row["encoded_feature"] = encoded[index]
        del row["expected_encoded_feature"]
    if any(not indices for indices in mapping.values()):
        raise ValueError("Every logical feature must have encoded contributions")
    if sorted(index for indices in mapping.values() for index in indices) != list(range(111)):
        raise ValueError("Encoded-to-logical mapping must be a complete disjoint partition")
    return mapping, rows


@dataclass
class ShapBatch:
    encoded_matrix: np.ndarray
    encoded_values: np.ndarray
    logical_values: np.ndarray
    base_values: np.ndarray
    raw_margin: np.ndarray
    probabilities: np.ndarray
    metadata: dict

    def save_npz(self, path: str | Path):
        """Store plain arrays and JSON text; reading requires no pickle."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A file handle avoids numpy silently appending an unexpected suffix.
        with path.open("wb") as handle:
            np.savez_compressed(
                handle, encoded_matrix=self.encoded_matrix,
                encoded_values=self.encoded_values, logical_values=self.logical_values,
                base_values=self.base_values, raw_margin=self.raw_margin,
                probabilities=self.probabilities,
                encoded_names=np.asarray(self.metadata["encoded_names"], dtype=str),
                logical_names=np.asarray(self.metadata["logical_names"], dtype=str),
                metadata_json=np.asarray(json.dumps(self.metadata, ensure_ascii=False, allow_nan=False)),
            )
        return path


class FrozenTreeShap:
    """Explain existing train/validation rows without changing the predictor."""

    def __init__(self, runtime: FrozenChurnRuntime):
        if not isinstance(runtime, FrozenChurnRuntime):
            raise TypeError("runtime must be a FrozenChurnRuntime")
        self.runtime = runtime
        self.preprocessing = runtime.metadata["preprocessing"]
        self.mapping, self.mapping_rows = _feature_mapping(self.preprocessing)
        self.encoded_names = list(self.preprocessing["output_columns"])
        self.logical_names = list(self.preprocessing["logical_columns"])
        self.iteration_range = tuple(runtime.metadata["iteration_range"])
        if self.iteration_range[0] != 0:
            raise ValueError("TreeExplainer cross-check requires tree range starting at zero")
        objective = json.loads(runtime.booster.save_config())["learner"]["objective"]["name"]
        if objective != "binary:logistic":
            raise ValueError("This explanation contract requires binary:logistic")
        self.tree_limit = self.iteration_range[1] or runtime.booster.num_boosted_rounds()
        self.explainer = shap.TreeExplainer(
            runtime.booster, data=None, model_output="raw",
            feature_perturbation="tree_path_dependent", feature_names=self.encoded_names,
        )
        self.model_path = None
        self.model_sha256 = None

    @classmethod
    def load(cls, model_path: str | Path, *, n_threads=2):
        result = cls(FrozenChurnRuntime.load(model_path, n_threads=n_threads))
        result.model_path = str(Path(model_path))
        result.model_sha256 = hashlib.sha256(Path(model_path).read_bytes()).hexdigest()
        return result

    def explain(self, frame: pd.DataFrame, *, partition: str, batch_size=512,
                cross_check=True) -> ShapBatch:
        if partition not in {"train", "validation"}:
            raise ValueError("Only train or validation explanations are allowed")
        _positive_int("batch_size", batch_size)
        if not isinstance(cross_check, bool):
            raise ValueError("cross_check must be boolean")
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("Explanation requires a nonempty predictor DataFrame")
        matrices, shap_parts, bases, margins, probabilities = [], [], [], [], []
        native_shap_error = native_base_error = 0.0
        for start in range(0, len(frame), batch_size):
            matrix = self.runtime.encoder.transform(frame.iloc[start:start + batch_size])
            # A DMatrix cannot represent the cast-generated infinities accepted
            # by inplace prediction. Never clip or silently alter such inputs.
            if not np.isfinite(matrix).all():
                raise ValueError("Exact SHAP requires finite encoded float32 values; frozen runtime predictions remain available for extreme cast-overflow inputs")
            dmatrix = xgb.DMatrix(matrix, nthread=self.runtime.n_threads)
            values = np.asarray(self.explainer.shap_values(
                matrix, tree_limit=self.tree_limit, approximate=False, check_additivity=True,
            ))
            expected = np.asarray(self.explainer.expected_value)
            if values.shape != matrix.shape or expected.size != 1:
                raise ValueError("Unexpected binary TreeExplainer output shape")
            base = np.full(len(matrix), float(expected.item()), dtype=np.float64)
            margin = self.runtime.booster.predict(
                dmatrix, output_margin=True, iteration_range=self.iteration_range,
            )
            probability = self.runtime.booster.inplace_predict(
                matrix, iteration_range=self.iteration_range, validate_features=True,
            )
            if cross_check:
                native = self.runtime.booster.predict(
                    dmatrix, pred_contribs=True, approx_contribs=False,
                    iteration_range=self.iteration_range,
                )
                if native.shape != (len(matrix), len(self.encoded_names) + 1):
                    raise ValueError("Unexpected native contribution shape")
                native_shap_error = max(native_shap_error, float(np.max(np.abs(values.astype(np.float64) - native[:, :-1]))))
                native_base_error = max(native_base_error, float(np.max(np.abs(base - native[:, -1]))))
            matrices.append(matrix)
            shap_parts.append(values)
            bases.append(base)
            margins.append(margin)
            probabilities.append(probability)
        matrix = np.concatenate(matrices)
        values = np.concatenate(shap_parts)
        base = np.concatenate(bases)
        margin = np.concatenate(margins)
        probability = np.concatenate(probabilities)
        logical = np.column_stack([
            values[:, self.mapping[name]].sum(axis=1, dtype=np.float64)
            for name in self.logical_names
        ])
        reconstructed_encoded = values.sum(axis=1, dtype=np.float64) + base
        reconstructed_logical = logical.sum(axis=1, dtype=np.float64) + base
        errors = {
            "encoded_additivity_max_abs_error": float(np.max(np.abs(reconstructed_encoded - margin))),
            "logical_additivity_max_abs_error": float(np.max(np.abs(reconstructed_logical - margin))),
            "aggregation_max_abs_error": float(np.max(np.abs(reconstructed_encoded - reconstructed_logical))),
            "sigmoid_margin_probability_max_abs_error": float(np.max(np.abs(_sigmoid(margin) - probability))),
            "sigmoid_reconstructed_probability_max_abs_error": float(np.max(np.abs(_sigmoid(reconstructed_logical) - probability))),
            "shap_native_max_abs_error": native_shap_error if cross_check else None,
            "base_native_max_abs_error": native_base_error if cross_check else None,
        }
        if (not np.isfinite(values).all() or not np.isfinite(base).all()
                or errors["encoded_additivity_max_abs_error"] > 1e-5
                or errors["logical_additivity_max_abs_error"] > 1e-5
                or errors["sigmoid_reconstructed_probability_max_abs_error"] > 1e-6
                or errors["sigmoid_margin_probability_max_abs_error"] > 1e-6
                or (cross_check and max(native_shap_error, native_base_error) > 1e-6)):
            raise AssertionError(f"Frozen TreeSHAP agreement/additivity failed: {errors}")
        metadata = {
            "schema_version": "w7-frozen-treeshap-v1", "partition": partition,
            "rows": len(frame), "encoded_names": self.encoded_names,
            "logical_names": self.logical_names,
            "logical_to_encoded_indices": self.mapping,
            "feature_mapping": self.mapping_rows,
            "grouping": "Sum signed encoded SHAP values within each logical variable before computing mean(abs(logical SHAP)); derived fields remain separate.",
            "units": "raw binary log-odds", "model_output": "raw",
            "feature_perturbation": "tree_path_dependent", "background_data": None,
            "approximate": False, "iteration_range": list(self.iteration_range),
            "tree_limit": self.tree_limit, "decision_threshold_unchanged": self.runtime.threshold,
            "cross_check_native": cross_check,
            "cross_check_independence": "API/configuration agreement only: TreeExplainer uses the same native XGBoost contribution shortcut for this configuration.",
            "errors": errors, "tolerances": {"margin": 1e-5, "probability": 1e-6, "native": 1e-6},
            "model_path": self.model_path, "model_sha256": self.model_sha256,
            "source_model_sha256": self.runtime.metadata["source_model_sha256"],
            "versions": {name: importlib.metadata.version(name) for name in ["shap", "xgboost", "numpy", "pandas"]},
            "limitations": list(LIMITATIONS), "training_performed": False,
            "labels_used": False, "caller_row_order_preserved": True,
            "partition_scope_note": "Caller must supply only the declared inherited partition; this array engine never loads customer files or verifies IDs itself.",
        }
        return ShapBatch(matrix, values, logical, base, margin, probability, metadata)


def _rank_inputs(values, feature_names):
    values = np.asarray(values, dtype=np.float64)
    names = list(feature_names)
    if (values.ndim != 2 or not values.shape[0] or values.shape[1] != len(names)
            or not len(names) or len(set(names)) != len(names)
            or not all(isinstance(name, str) for name in names) or not np.isfinite(values).all()):
        raise ValueError("Ranking requires nonempty finite SHAP rows and unique matching feature names")
    return values, names


def global_rank(values, feature_names) -> pd.DataFrame:
    """Complete ranking; use .head(10) without dropping the remaining fields."""
    values, names = _rank_inputs(values, feature_names)
    importance = np.abs(values).mean(axis=0)
    order = np.argsort(-importance, kind="stable")
    result = pd.DataFrame({
        "feature": names, "feature_index": np.arange(len(names)),
        "mean_abs_shap": importance, "mean_signed_shap": values.mean(axis=0),
        "positive_fraction": (values > 0).mean(axis=0),
        "negative_fraction": (values < 0).mean(axis=0),
        "nonzero_fraction": (values != 0).mean(axis=0),
    }).iloc[order].reset_index(drop=True)
    result.insert(0, "rank", np.arange(1, len(names) + 1))
    return result


def bootstrap_rank_stability(values, feature_names, reference_train_top10,
                             *, n_bootstrap=200, seed=20261016, top_k=10) -> dict:
    """Row bootstrap for an already frozen model, usually on validation SHAP.

    Supply train-selected names to keep the reference ranking independent of
    validation. No labels, threshold search, feature selection or refitting.
    """
    values, names = _rank_inputs(values, feature_names)
    _positive_int("n_bootstrap", n_bootstrap)
    _positive_int("top_k", top_k)
    if top_k > len(names):
        raise ValueError("top_k exceeds feature count")
    reference = list(reference_train_top10)
    if len(reference) != top_k or len(set(reference)) != top_k or not set(reference) <= set(names):
        raise ValueError("reference_train_top10 must contain top_k unique registered feature names")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    rng = np.random.default_rng(seed)
    absolute = np.abs(values)
    ranks = np.empty((n_bootstrap, len(names)), dtype=np.int64)
    means = np.empty((n_bootstrap, len(names)), dtype=np.float64)
    overlap = np.empty(n_bootstrap, dtype=np.int64)
    reference_set = set(reference)
    for iteration in range(n_bootstrap):
        sampled = rng.integers(0, len(values), size=len(values))
        importance = absolute[sampled].mean(axis=0)
        order = np.argsort(-importance, kind="stable")
        means[iteration] = importance
        ranks[iteration, order] = np.arange(1, len(names) + 1)
        overlap[iteration] = len(reference_set & {names[index] for index in order[:top_k]})
    observed = global_rank(values, names)
    statistics = []
    for row in observed.to_dict(orient="records"):
        index = row["feature_index"]
        row.update({
            "bootstrap_top_k_frequency": float(np.mean(ranks[:, index] <= top_k)),
            "bootstrap_rank_median": float(np.median(ranks[:, index])),
            "bootstrap_rank_p025": float(np.quantile(ranks[:, index], .025)),
            "bootstrap_rank_p975": float(np.quantile(ranks[:, index], .975)),
            "bootstrap_mean_abs_p025": float(np.quantile(means[:, index], .025)),
            "bootstrap_mean_abs_p975": float(np.quantile(means[:, index], .975)),
            "in_reference_train_top_k": row["feature"] in reference_set,
        })
        statistics.append(row)
    return {
        "method": "Nonparametric row bootstrap of existing frozen-model SHAP values; percentile intervals",
        "rows": len(values), "features": len(names), "n_bootstrap": n_bootstrap,
        "seed": seed, "top_k": top_k, "reference_train_top_k": reference,
        "observed_top_k": observed.feature.head(top_k).tolist(),
        "observed_reference_overlap_count": len(reference_set & set(observed.feature.head(top_k))),
        "bootstrap_reference_overlap_counts": overlap.tolist(),
        "bootstrap_reference_overlap_mean": float(overlap.mean()),
        "bootstrap_reference_jaccard_mean": float(np.mean(overlap / (2 * top_k - overlap))),
        "feature_statistics": statistics,
        "ties": "Stable original feature order breaks exact importance ties, including unused zero-contribution fields.",
        "limitations": list(LIMITATIONS), "labels_used": False, "training_performed": False,
    }
