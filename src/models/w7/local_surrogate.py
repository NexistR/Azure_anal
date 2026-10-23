"""LIME local surrogates over valid, observed training customers.

This uses the installed official ``lime.lime_base.LimeBase`` with a custom
empirical neighborhood. No columns are perturbed independently: every model
query is an intact observed customer or the actual instance being explained.
Consequently, the result describes local associations on observed support, not
independent interventions or causal effects. The predictive model stays frozen.

Official API: https://lime-ml.readthedocs.io/en/latest/lime.html#lime.lime_base.LimeBase
Source: https://github.com/marcotcr/lime/blob/master/lime/lime_base.py
"""
from __future__ import annotations

import copy
import hashlib
from importlib.metadata import version
from itertools import combinations
import math

from lime.lime_base import LimeBase
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from .contract import validate_frame


DEFAULT_SEEDS = (42, 43, 44, 45, 46)
METHOD = "official_lime_base_with_observed_train_neighborhood_v1"


def _digest_positions(values) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<i8").tobytes()).hexdigest()


def _json_value(value):
    if pd.isna(value):
        return None
    return value.item() if isinstance(value, np.generic) else value


def _weighted_metrics(truth, prediction, weights):
    mean = float(np.average(truth, weights=weights))
    residual = truth - prediction
    residual_ss = float(np.sum(weights * residual ** 2))
    total_ss = float(np.sum(weights * (truth - mean) ** 2))
    return {
        "weighted_r2": 1.0 - residual_ss / total_ss if total_ss > 0 else None,
        "weighted_mae": float(np.average(np.abs(residual), weights=weights)),
        "weighted_rmse": float(np.sqrt(np.average(residual ** 2, weights=weights))),
        "effective_sample_size": float(np.sum(weights) ** 2 / np.sum(weights ** 2)),
        "target_weighted_mean": mean,
        "prediction_min": float(np.min(prediction)),
        "prediction_max": float(np.max(prediction)),
        "predictions_outside_probability_range": int(np.sum((prediction < 0) | (prediction > 1))),
    }


class EmpiricalLimeExplainer:
    """Explain one-row frames with fixed, fully auditable LIME settings.

    The nearest observed training rows form the candidate neighborhood. Each
    fixed seed divides that pool into disjoint surrogate-fit and fidelity-only
    subsets. The original instance is prepended to the fit subset, as required
    by LimeBase. Targets are frozen model probabilities; no outcome labels are
    accepted by this interface. All 22 coefficients are retained, with ten
    displayed terms selected solely for readability.
    """

    def __init__(self, runtime, train_frame: pd.DataFrame, train_ids=None, *,
                 n_neighbors=1200, holdout_fraction=0.25, seeds=DEFAULT_SEEDS, top_k=10):
        if isinstance(n_neighbors, bool) or not isinstance(n_neighbors, int) or n_neighbors < 8:
            raise ValueError("n_neighbors must be an integer of at least 8")
        if not isinstance(holdout_fraction, (int, float)) or isinstance(holdout_fraction, bool) or not 0 < holdout_fraction < 1:
            raise ValueError("holdout_fraction must be strictly between zero and one")
        if not seeds or len(set(seeds)) != len(seeds) or any(
                isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in seeds):
            raise ValueError("seeds must contain distinct nonnegative integers")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 22:
            raise ValueError("top_k must be an integer between 1 and 22")
        self.runtime = runtime
        self.config = copy.deepcopy(runtime.metadata["preprocessing"]["cleaning_config"])
        self.train_frame = validate_frame(train_frame, self.config).reset_index(drop=True).copy(deep=True)
        if len(self.train_frame) < 8:
            raise ValueError("At least eight observed training rows are required")
        self.names = list(runtime.metadata["preprocessing"]["input_columns"])
        if len(self.names) != 22 or set(self.train_frame) != set(self.names):
            raise ValueError("LIME must use the frozen 22-field raw feature contract")
        self.numeric_names = list(self.config["features"]["numeric"])
        self.categorical_names = list(self.config["features"]["categorical"] + self.config["features"]["binary"])
        if self.names != self.numeric_names + self.categorical_names:
            raise ValueError("Unexpected frozen feature order")
        self.seeds = tuple(seeds)
        self.n_neighbors = min(n_neighbors, len(self.train_frame))
        self.holdout_fraction = float(holdout_fraction)
        self.top_k = top_k
        self.kernel_width = math.sqrt(len(self.names)) * 0.75
        self.background_probability = np.asarray(runtime.predict_score(self.train_frame), dtype=np.float64)
        if (self.background_probability.shape != (len(self.train_frame),)
                or not np.isfinite(self.background_probability).all()
                or ((self.background_probability < 0) | (self.background_probability > 1)).any()):
            raise ValueError("Frozen model returned invalid training probabilities")
        if train_ids is not None:
            self.train_ids = np.asarray(train_ids, dtype=str)
            if self.train_ids.shape != (len(self.train_frame),) or len(set(self.train_ids)) != len(self.train_ids):
                raise ValueError("train_ids must be unique and align with the observed training rows")
        else:
            self.train_ids = None
        numeric = self.train_frame[self.numeric_names].to_numpy(dtype=np.float64)
        self.medians = np.asarray([
            np.nanmedian(numeric[:, index]) if np.isfinite(numeric[:, index]).any() else 0.0
            for index in range(numeric.shape[1])
        ])
        imputed = np.where(np.isnan(numeric), self.medians, numeric)
        self.means = np.mean(imputed, axis=0)
        scales = np.std(imputed, axis=0, ddof=0)
        self.scales = np.where(scales == 0, 1.0, scales)
        self.numeric_standardized = (imputed - self.means) / self.scales
        if not np.isfinite(self.numeric_standardized).all():
            raise ValueError("Non-finite empirical-neighborhood scaling")
        self.categorical_values = self.train_frame[self.categorical_names].to_numpy()

    def metadata(self) -> dict:
        values_hash = hashlib.sha256(
            pd.util.hash_pandas_object(self.train_frame[self.names], index=False).to_numpy(dtype="<u8").tobytes()
        ).hexdigest()
        return {
            "method": METHOD,
            "library": "lime",
            "library_version": version("lime"),
            "official_api": "lime.lime_base.LimeBase.explain_instance_with_data",
            "official_api_url": "https://lime-ml.readthedocs.io/en/latest/lime.html#lime.lime_base.LimeBase",
            "background_source": "observed frozen training rows only",
            "background_rows": len(self.train_frame),
            "background_feature_values_sha256": values_hash,
            "background_ids_sha256": hashlib.sha256("|".join(self.train_ids).encode()).hexdigest() if self.train_ids is not None else None,
            "n_neighbors": self.n_neighbors,
            "neighbor_selection": "smallest mixed Euclidean distance; stable original training-row order resolves ties; no outcome labels",
            "self_neighbor_policy": "exclude the matching customer ID when an explained training customer is also present in the background",
            "numeric_distance": "training-median imputation and training-mean/std z-scores (ddof=0)",
            "categorical_distance": "0/1 mismatch, including the three deterministic cleaning flags",
            "interpretable_representation": "numeric z-scores; categorical 1 when matching the explained instance, else 0",
            "numeric_statistics": {name: {"median": float(self.medians[index]), "mean": float(self.means[index]),
                                          "scale": float(self.scales[index])}
                                   for index, name in enumerate(self.numeric_names)},
            "feature_names": list(self.names),
            "n_features": len(self.names),
            "kernel": "exp(-distance^2 / (2 * kernel_width^2))",
            "kernel_width": self.kernel_width,
            "kernel_width_rule": "sqrt(22) * 0.75, fixed before case results",
            "surrogate": "Ridge(alpha=1.0, fit_intercept=True, solver='cholesky')",
            "feature_selection": "none: all 22 features fitted and retained",
            "top_k_display": self.top_k,
            "top_k_display_order": "descending absolute contribution relative to the weighted fit-neighbor reference",
            "holdout_fraction": self.holdout_fraction,
            "seeds": list(self.seeds),
            "anchor_included_in_surrogate_fit": True,
            "anchor_target": "frozen model probability, not observed outcome",
            "heldout_neighbors": "disjoint observed training customers withheld from surrogate fitting; not predictive-model test data",
            "predictive_model_refit": False,
            "outcome_labels_used": False,
            "synthetic_customer_rows": 0,
            "test_partition_loaded_or_predicted": False,
            "fidelity_rule": {"minimum_holdout_weighted_r2_all_seeds": 0.70,
                              "maximum_instance_probability_absolute_error_all_seeds": 0.05},
            "stability_rule": {"minimum_mean_pairwise_top_k_jaccard": 0.60,
                               "minimum_mean_top_k_sign_agreement_to_primary": 0.80},
            "limitations": [
                "Observational local approximation, not a causal intervention or an action-effect estimate.",
                "Correlated service fields and deterministic flags can share proxy coefficients; coefficients are not independently identified causal effects.",
                "No independent raw-field or encoded-column perturbations are queried; coverage is restricted to observed training support.",
                "Local proxy predictions are not clipped to [0,1]; errors and out-of-range predictions remain visible.",
                "Contributions reconstruct the fitted local proxy relative to its weighted neighbor reference; they are not SHAP values.",
            ],
        }

    def _kernel(self, distances):
        return np.exp(-(np.asarray(distances) ** 2) / (2 * self.kernel_width ** 2))

    def _representation(self, instance):
        numeric = instance[self.numeric_names].to_numpy(dtype=np.float64)[0]
        numeric = np.where(np.isnan(numeric), self.medians, numeric)
        numeric_scaled = (numeric - self.means) / self.scales
        categorical = instance[self.categorical_names].to_numpy()[0]
        matches = (self.categorical_values == categorical).astype(np.float64)
        neighbors = np.column_stack([self.numeric_standardized, matches])
        anchor = np.concatenate([numeric_scaled, np.ones(len(self.categorical_names))])
        distances = np.linalg.norm(neighbors - anchor, axis=1)
        if not np.isfinite(anchor).all() or not np.isfinite(distances).all():
            raise ValueError("Explained instance lies outside safe numeric neighborhood representation")
        return anchor, neighbors, distances

    def explain(self, instance_one_row: pd.DataFrame, case_id=None) -> dict:
        if not isinstance(instance_one_row, pd.DataFrame) or len(instance_one_row) != 1:
            raise ValueError("explain requires exactly one observed customer row")
        instance = validate_frame(instance_one_row, self.config).reset_index(drop=True)
        anchor, all_neighbors, all_distances = self._representation(instance)
        eligible = np.argsort(all_distances, kind="stable")
        excluded_self = 0
        if case_id is not None and self.train_ids is not None:
            keep = self.train_ids[eligible] != str(case_id)
            excluded_self = int(np.sum(~keep))
            eligible = eligible[keep]
        selected = eligible[:self.n_neighbors]
        probability = float(self.runtime.predict_score(instance)[0])
        holdout_count = min(len(selected) - 2, max(2, int(round(len(selected) * self.holdout_fraction))))
        records = []
        contribution_vectors = []
        for seed in self.seeds:
            permutation = np.random.default_rng(seed).permutation(selected)
            holdout_positions = permutation[:holdout_count]
            fit_positions = permutation[holdout_count:]
            fit_data = np.vstack([anchor, all_neighbors[fit_positions]])
            fit_probability = np.concatenate([[probability], self.background_probability[fit_positions]])
            labels = np.column_stack([1.0 - fit_probability, fit_probability])
            fit_distances = np.concatenate([[0.0], all_distances[fit_positions]])
            weights = self._kernel(fit_distances)
            model = Ridge(alpha=1.0, fit_intercept=True, solver="cholesky")
            base = LimeBase(self._kernel, verbose=False, random_state=seed)
            intercept, explanation, fit_r2, local_prediction = base.explain_instance_with_data(
                fit_data, labels, fit_distances, label=1, num_features=len(self.names),
                feature_selection="none", model_regressor=model,
            )
            coefficients = np.zeros(len(self.names), dtype=np.float64)
            for feature, coefficient in explanation:
                coefficients[feature] = coefficient
            local_prediction = float(local_prediction[0])
            holdout_weights = self._kernel(all_distances[holdout_positions])
            holdout_predictions = model.predict(all_neighbors[holdout_positions])
            holdout = _weighted_metrics(self.background_probability[holdout_positions], holdout_predictions, holdout_weights)
            # Exclude the anchor from the reference to make the observational
            # comparison explicit; still reconstruct the official local_pred.
            reference = np.average(fit_data[1:], axis=0, weights=weights[1:])
            reference_prediction = float(intercept + np.dot(coefficients, reference))
            contributions = coefficients * (anchor - reference)
            reconstructed = reference_prediction + float(np.sum(contributions))
            error = abs(probability - local_prediction)
            reconstruction_error = abs(reconstructed - local_prediction)
            if reconstruction_error > 1e-10:
                raise RuntimeError("LIME proxy contribution reconstruction failed")
            contribution_vectors.append(contributions)
            ordered = sorted(range(len(self.names)), key=lambda index: (-abs(contributions[index]), index))
            terms = []
            for index in ordered:
                name = self.names[index]
                terms.append({
                    "feature": name,
                    "raw_value": _json_value(instance[name].iloc[0]),
                    "representation": "training_standard_deviation_units" if name in self.numeric_names else "matches_instance_category",
                    "coefficient": float(coefficients[index]),
                    "instance_representation": float(anchor[index]),
                    "weighted_neighbor_reference_representation": float(reference[index]),
                    "local_contribution": float(contributions[index]),
                    "direction": "increases_local_proxy" if contributions[index] > 0 else "decreases_local_proxy" if contributions[index] < 0 else "zero",
                })
            low_fidelity = holdout["weighted_r2"] is None or holdout["weighted_r2"] < 0.70 or error > 0.05
            records.append({
                "seed": seed,
                "fit_neighbor_rows": len(fit_positions),
                "fit_rows_including_anchor": len(fit_data),
                "heldout_neighbor_rows": len(holdout_positions),
                "fit_holdout_overlap_count": int(np.intersect1d(fit_positions, holdout_positions).size),
                "fit_positions_sha256": _digest_positions(fit_positions),
                "heldout_positions_sha256": _digest_positions(holdout_positions),
                "fit_weighted_r2": float(fit_r2),
                "fit_effective_sample_size_including_anchor": float(weights.sum() ** 2 / np.sum(weights ** 2)),
                "heldout": holdout,
                "model_probability": probability,
                "local_surrogate_probability": local_prediction,
                "instance_probability_absolute_error": error,
                "fidelity_status": "low_fidelity" if low_fidelity else "meets_declared_local_fidelity_rule",
                "intercept": float(intercept),
                "weighted_neighbor_reference_prediction": reference_prediction,
                "sum_all_local_contributions": float(contributions.sum()),
                "reconstructed_local_prediction": reconstructed,
                "contribution_reconstruction_absolute_error": reconstruction_error,
                "all_terms": terms,
                "top_terms": terms[:self.top_k],
                "remaining_terms_contribution": float(sum(term["local_contribution"] for term in terms[self.top_k:])),
            })
        top_sets = [{term["feature"] for term in run["top_terms"]} for run in records]
        pairwise = [len(a & b) / len(a | b) for a, b in combinations(top_sets, 2)]
        primary_indices = [self.names.index(term["feature"]) for term in records[0]["top_terms"]]
        selected_contributions = np.asarray(contribution_vectors)[:, primary_indices]
        signs = np.sign(np.where(np.abs(selected_contributions) < 1e-12, 0.0, selected_contributions))
        agreement = np.mean(signs[1:] == signs[0], axis=0) if len(signs) > 1 else np.ones(len(primary_indices))
        mean_jaccard = float(np.mean(pairwise)) if pairwise else 1.0
        sign_agreement = float(np.mean(agreement))
        stability = {
            "mean_pairwise_top_k_jaccard": mean_jaccard,
            "minimum_pairwise_top_k_jaccard": float(min(pairwise)) if pairwise else 1.0,
            "mean_top_k_sign_agreement_to_primary": sign_agreement,
            "primary_top_k_feature_sign_agreement": {self.names[index]: float(value) for index, value in zip(primary_indices, agreement)},
            "instance_surrogate_probability_min": float(min(record["local_surrogate_probability"] for record in records)),
            "instance_surrogate_probability_max": float(max(record["local_surrogate_probability"] for record in records)),
            "status": "unstable" if mean_jaccard < 0.60 or sign_agreement < 0.80 else "meets_declared_stability_rule",
        }
        finite_r2 = [record["heldout"]["weighted_r2"] for record in records if record["heldout"]["weighted_r2"] is not None]
        low_fidelity = any(record["fidelity_status"] == "low_fidelity" for record in records)
        warnings = []
        if low_fidelity:
            warnings.append("LOW FIDELITY: at least one fixed seed fails heldout weighted R2 >= 0.70 or instance error <= 0.05; do not present this proxy as an exact model explanation.")
        if stability["status"] == "unstable":
            warnings.append("UNSTABLE TERMS: local feature ranking/signs fail the declared cross-seed stability rule.")
        return {
            "method": METHOD,
            "case_id": str(case_id) if case_id is not None else None,
            "model_probability": probability,
            "outcome_label_used": False,
            "n_features": len(self.names),
            "neighbor_pool_rows": len(selected),
            "matching_customer_id_excluded_from_neighbor_pool": excluded_self,
            "neighbor_pool_positions_sha256": _digest_positions(selected),
            "neighbor_distances": {"min": float(np.min(all_distances[selected])), "median": float(np.median(all_distances[selected])),
                                   "max": float(np.max(all_distances[selected]))},
            "fidelity_status": "low_fidelity" if low_fidelity else "meets_declared_local_fidelity_rule",
            "minimum_heldout_weighted_r2": float(min(finite_r2)) if finite_r2 else None,
            "maximum_instance_probability_absolute_error": float(max(record["instance_probability_absolute_error"] for record in records)),
            "warnings": warnings,
            "primary_seed": self.seeds[0],
            "primary": records[0],
            "seed_runs": records,
            "stability": stability,
            "interpretation": "Local probability proxy contributions relative to its weighted observed-neighbor reference; not SHAP and not causal effects.",
        }

    def explain_many(self, frame: pd.DataFrame, case_ids=None) -> list[dict]:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("explain_many requires nonempty observed customer rows")
        if case_ids is None:
            case_ids = [None] * len(frame)
        if len(case_ids) != len(frame):
            raise ValueError("case_ids must align with the explained rows")
        return [self.explain(frame.iloc[index:index + 1], case_id=case_ids[index]) for index in range(len(frame))]
