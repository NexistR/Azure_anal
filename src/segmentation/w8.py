"""Training-only static segmentation and transparent W8 fee/risk rules.

These APIs receive only raw22 features for fitting. Scores, labels and IDs never
enter feature construction, scaling, clustering or parameter selection.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from numbers import Real
from pathlib import Path
import time

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.models.w7.contract import validate_frame
from src.models.w7.risk import validate_probabilities

ROOT = Path(__file__).resolve().parents[2]
RAW_COLUMNS = ["tenure", "MonthlyCharges", "TotalCharges", "gender", "SeniorCitizen", "Partner", "Dependents",
               "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup", "DeviceProtection",
               "TechSupport", "StreamingTV", "StreamingMovies", "Contract", "PaperlessBilling", "PaymentMethod",
               "total_charges_missing", "tenure_zero", "internet_applicable"]
ADDONS = ["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"]
QUADRANTS = {"HV_HR": "高月费×高风险", "HV_LR": "高月费×非高风险", "LV_HR": "低月费×高风险", "LV_LR": "低月费×非高风险"}


def load_config(path=None):
    cfg = json.loads(Path(path or ROOT / "configs/w8_segmentation.json").read_text(encoding="utf-8"))
    if cfg["risk_threshold"] != .30 or cfg["value_field"] != "MonthlyCharges" or cfg["value_quantile"] != .5:
        raise ValueError("W8 frozen risk and value rules must not change")
    return cfg


def static_features(raw: pd.DataFrame) -> pd.DataFrame:
    cleaning = json.loads((ROOT / "configs/w3_cleaning.json").read_text(encoding="utf-8"))
    frame = validate_frame(raw, cleaning)
    return pd.DataFrame({
        "tenure_log1p": np.log1p(frame["tenure"].to_numpy(dtype=float)),
        "monthly_charges_log1p": np.log1p(frame["MonthlyCharges"].to_numpy(dtype=float)),
        "internet_addon_count": frame[ADDONS].eq("Yes").sum(axis=1).to_numpy(dtype=float),
        "phone_service": frame["PhoneService"].eq("Yes").to_numpy(dtype=float),
        "multiple_lines": frame["MultipleLines"].eq("Yes").to_numpy(dtype=float),
        "automatic_payment": frame["PaymentMethod"].isin(["Bank transfer (automatic)", "Credit card (automatic)"]).to_numpy(dtype=float),
        "paperless_billing": frame["PaperlessBilling"].eq("Yes").to_numpy(dtype=float),
        "Contract": frame["Contract"].to_numpy(), "InternetService": frame["InternetService"].to_numpy(),
    }, index=raw.index)


def make_preprocessor(cfg):
    return ColumnTransformer([
        ("numeric", StandardScaler(), cfg["numeric_features"]),
        ("binary", "passthrough", cfg["binary_features"]),
        ("categorical", OneHotEncoder(categories=cfg["categories"], handle_unknown="error", sparse_output=False, dtype=np.float64), cfg["categorical_features"]),
    ], remainder="drop", sparse_threshold=0,
        transformer_weights={"categorical": cfg["categorical_block_scale"]})


def cluster_metrics(matrix, labels, sample_indices):
    labels = np.asarray(labels, dtype=np.int64)
    covered = labels >= 0
    unique, counts = np.unique(labels[covered], return_counts=True)
    sample = np.asarray(sample_indices, dtype=np.int64)
    sample = sample[covered[sample]]
    sample_unique = np.unique(labels[sample])
    silhouette = None
    if 2 <= len(sample_unique) < len(sample):
        silhouette = float(silhouette_score(matrix[sample], labels[sample], metric="euclidean"))
    dbi = None
    if 2 <= len(unique) < int(covered.sum()):
        dbi = float(davies_bouldin_score(matrix[covered], labels[covered]))
    return {"train_clusters": len(unique), "noise_count": int((~covered).sum()), "coverage": float(covered.mean()),
            "silhouette": silhouette, "dbi": dbi, "min_cluster_size": int(counts.min()) if len(counts) else 0,
            "max_cluster_size": int(counts.max()) if len(counts) else 0,
            "silhouette_sample_n": len(sample), "silhouette_sample_clusters": len(sample_unique),
            "silhouette_population": "fixed sample restricted to nonnoise rows; conditional for DBSCAN",
            "dbi_population": "all nonnoise rows; conditional for DBSCAN",
            "silhouette_sample_indices_sha256": hashlib.sha256(sample.tobytes()).hexdigest()}


def fit_segmentation(train_raw, cfg):
    """Fit only raw training features; no labels/probabilities/IDs are accepted."""
    features = static_features(train_raw)
    if len(features) != cfg["training_rows"]:
        raise ValueError("Unexpected training row count")
    fit_log = []

    def fitted(estimator, matrix, category, candidate, **kwargs):
        start = time.perf_counter()
        estimator.fit(matrix, **kwargs)
        fit_log.append({"category": category, "candidate_id": candidate, "rows": len(matrix),
                        "columns": matrix.shape[1], "elapsed_seconds": time.perf_counter()-start,
                        "input_partition": "train", "labels_or_risk_passed": False,
                        "parameters": estimator.get_params(deep=False) if category in {"kmeans", "dbscan"} else {}})
        return estimator

    preprocessor = make_preprocessor(cfg)
    start = time.perf_counter()
    matrix = preprocessor.fit_transform(features)
    fit_log.append({"category": "preprocessor", "candidate_id": "static13", "rows": len(matrix), "columns": matrix.shape[1],
                    "elapsed_seconds": time.perf_counter()-start, "input_partition": "train", "labels_or_risk_passed": False})
    assert matrix.shape == (len(train_raw), cfg["encoded_dimensions"]) and np.isfinite(matrix).all()
    rng = np.random.default_rng(cfg["seed"])
    sample = np.sort(rng.choice(len(matrix), size=min(cfg["silhouette_sample_size"], len(matrix)), replace=False)).astype(np.int64)
    candidates, models = [], {}
    kcfg = cfg["kmeans"]
    for k in kcfg["k_values"]:
        candidate_id = f"kmeans_k{k}"
        model = fitted(KMeans(n_clusters=k, n_init=kcfg["n_init"], max_iter=kcfg["max_iter"], tol=kcfg["tol"],
                              algorithm=kcfg["algorithm"], random_state=cfg["seed"]), matrix, "kmeans", candidate_id)
        metrics = cluster_metrics(matrix, model.labels_, sample)
        row = {"algorithm": "KMeans", "candidate_id": candidate_id, "k": k, "eps": None, "min_samples": None,
               "eps_quantile": None, "selected": False, "eligible": metrics["silhouette"] is not None,
               "selection_score": metrics["silhouette"], "inertia": float(model.inertia_), **metrics}
        candidates.append(row)
        models[candidate_id] = model
    krows = [r for r in candidates if r["algorithm"] == "KMeans" and r["eligible"]]
    chosen_k = min(krows, key=lambda r: (-r["silhouette"], r["dbi"], r["k"]))
    chosen_k["selected"] = True
    kmodel = models[chosen_k["candidate_id"]]
    seed_labels = {cfg["seed"]: kmodel.labels_}
    for seed in kcfg["stability_seeds"]:
        if seed == cfg["seed"]:
            continue
        model = fitted(KMeans(n_clusters=chosen_k["k"], n_init=kcfg["n_init"], max_iter=kcfg["max_iter"],
                              tol=kcfg["tol"], algorithm=kcfg["algorithm"], random_state=seed), matrix,
                       "kmeans", f"selected_k{chosen_k['k']}_seed{seed}")
        seed_labels[seed] = model.labels_
    ari = [{"seed_a": a, "seed_b": b, "ari": float(adjusted_rand_score(seed_labels[a], seed_labels[b]))}
           for a, b in itertools.combinations(kcfg["stability_seeds"], 2)]
    dcfg = cfg["dbscan"]
    knn_diagnostics = []
    for min_samples in dcfg["min_samples_values"]:
        nn = fitted(NearestNeighbors(n_neighbors=min_samples, algorithm="brute", metric="euclidean", n_jobs=cfg["threads"]),
                    matrix, "neighbor_distance", f"knn_m{min_samples}")
        # Querying X explicitly includes self at distance zero, consistent with DBSCAN min_samples.
        distances = nn.kneighbors(matrix, return_distance=True)[0][:, min_samples-1]
        for quantile in dcfg["knn_distance_quantiles"]:
            eps = float(np.quantile(distances, quantile, method="linear"))
            candidate_id = f"dbscan_m{min_samples}_q{int(round(quantile*100)):03d}"
            if eps <= 0:
                raise ValueError("Prespecified DBSCAN radius is zero; retain failed run rather than invent a radius")
            model = fitted(DBSCAN(eps=eps, min_samples=min_samples, metric="euclidean", algorithm="brute", n_jobs=cfg["threads"]),
                           matrix, "dbscan", candidate_id)
            metrics = cluster_metrics(matrix, model.labels_, sample)
            eligible = (2 <= metrics["train_clusters"] <= dcfg["maximum_clusters"]
                        and metrics["coverage"] >= dcfg["minimum_coverage"]
                        and metrics["min_cluster_size"] >= dcfg["minimum_cluster_size"]
                        and metrics["silhouette"] is not None)
            row = {"algorithm": "DBSCAN", "candidate_id": candidate_id, "k": None, "eps": eps,
                   "min_samples": min_samples, "eps_quantile": quantile, "selected": False, "eligible": eligible,
                   "selection_score": metrics["coverage"]*metrics["silhouette"] if metrics["silhouette"] is not None else None,
                   "inertia": None, **metrics}
            candidates.append(row)
            models[candidate_id] = model
            knn_diagnostics.append({"candidate_id": candidate_id, "min_samples": min_samples, "quantile": quantile,
                                    "eps": eps, "self_included": True, "rows": len(matrix)})
    drows = [r for r in candidates if r["algorithm"] == "DBSCAN" and r["eligible"]]
    chosen_d = (min(drows, key=lambda r: (-r["selection_score"], -r["coverage"], r["dbi"], r["eps"], r["min_samples"]))
                if drows else next(r for r in candidates if r["candidate_id"] == dcfg["fallback_candidate_id"]))
    chosen_d["selected"] = True
    dmodel = models[chosen_d["candidate_id"]]
    core_indices = dmodel.core_sample_indices_.astype(np.int64)
    core_nn = None
    if len(core_indices):
        core_nn = fitted(NearestNeighbors(n_neighbors=1, algorithm="brute", metric="euclidean", n_jobs=cfg["threads"]),
                         matrix[core_indices], "core_assignment_index", "selected_dbscan_cores")
    pca = fitted(PCA(n_components=2, svd_solver="full"), matrix, "display_pca", "train_display_only")
    weak_reasons = []
    if chosen_k["silhouette"] < .25:
        weak_reasons.append("selected KMeans train silhouette below prespecified 0.25")
    if min(r["ari"] for r in ari) < .8:
        weak_reasons.append("minimum seed-pair ARI below prespecified 0.80")
    selection = {"primary_algorithm": "KMeans", "kmeans": dict(chosen_k), "dbscan": dict(chosen_d),
                 "dbscan_selection_status": "eligible_candidate" if drows else "no_eligible_candidate_prespecified_fallback",
                 "rules": cfg["selection_rules"], "weak_structure": bool(weak_reasons), "weak_structure_reasons": weak_reasons,
                 "selected_from_train_only": True, "validation_materialized_at_selection": False,
                 "kmeans_stability": {"seeds": kcfg["stability_seeds"], "pairs": ari,
                                      "minimum_ari": min(r["ari"] for r in ari), "mean_ari": float(np.mean([r["ari"] for r in ari]))},
                 "knn_diagnostics": knn_diagnostics,
                 "silhouette_sample_indices": sample.tolist(), "silhouette_sample_indices_sha256": hashlib.sha256(sample.tobytes()).hexdigest(),
                 "pca_explained_variance_ratio": pca.explained_variance_ratio_.tolist()}
    bundle = {"config": cfg, "preprocessor": preprocessor, "kmeans": kmodel, "dbscan": dmodel,
              "pca": pca, "core_neighbor_index": core_nn, "core_train_indices": core_indices,
              "core_train_labels": dmodel.labels_[core_indices], "feature_names": preprocessor.get_feature_names_out().tolist(),
              "seed_labels": seed_labels}
    return bundle, matrix, selection, candidates, fit_log


def assign_dbscan(matrix, bundle):
    """Training-core extension; ambiguity is reachability of >=2 fitted clusters."""
    n = len(matrix)
    labels, ambiguous = np.full(n, -1, dtype=np.int64), np.zeros(n, dtype=bool)
    nearest_distance = np.full(n, np.nan)
    selected_core_index = np.full(n, -1, dtype=np.int64)
    index = bundle["core_neighbor_index"]
    if index is None:
        return labels, ambiguous, nearest_distance, selected_core_index
    nearest_distance[:] = index.kneighbors(matrix, n_neighbors=1, return_distance=True)[0][:, 0]
    distances, neighbors = index.radius_neighbors(matrix, radius=float(bundle["dbscan"].eps), return_distance=True, sort_results=True)
    for row, (distance, neighbor) in enumerate(zip(distances, neighbors)):
        if not len(neighbor):
            continue
        order = np.lexsort((bundle["core_train_indices"][neighbor], distance))
        core = neighbor[order[0]]
        labels[row] = int(bundle["core_train_labels"][core])
        selected_core_index[row] = int(bundle["core_train_indices"][core])
        ambiguous[row] = len(np.unique(bundle["core_train_labels"][neighbor])) >= 2
    return labels, ambiguous, nearest_distance, selected_core_index


def _fee_values(values):
    original = np.asarray(values)
    if original.ndim != 1 or original.dtype.kind in "bcUSMm" or not len(original):
        raise ValueError("Monthly fees must be a nonempty one-dimensional real numeric vector")
    if original.dtype.kind == "O" and any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) for value in original):
        raise ValueError("Monthly fees must be real numbers, not bool, complex or text")
    # Inspect before conversion so a mixed [True, 0.2] list cannot silently become floats.
    if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) for value in np.asarray(values, dtype=object)):
        raise ValueError("Monthly fees must be real numbers, not bool, complex or text")
    result = original.astype(np.float64)
    if not np.isfinite(result).all() or (result < 0).any():
        raise ValueError("Monthly fees must be finite and nonnegative")
    return result


def fit_value_rules(train_raw, cfg):
    values = _fee_values(train_raw["MonthlyCharges"])
    if len(values) != cfg["training_rows"]:
        raise ValueError("Invalid training monthly fees")
    return {"value_field": "MonthlyCharges", "high_value_threshold": float(np.quantile(values, .5, method="linear")),
            "high_value_comparison": ">=", "risk_threshold": .30, "risk_comparison": ">=",
            "threshold_fit_partition": "train", "threshold_fit_rows": len(values),
            "quantile_method": "linear", "sensitivity_thresholds": [{"quantile": q, "value_threshold": float(np.quantile(values, q, method="linear"))}
                for q in cfg["value_sensitivity_quantiles"]], "interpretation": cfg["interpretation"]}


def add_value_risk(frame, value_threshold, risk_threshold=.30):
    if risk_threshold != .30:
        raise ValueError("Frozen classification threshold must remain 0.30")
    if (isinstance(value_threshold, (bool, np.bool_)) or not isinstance(value_threshold, Real)
            or not np.isfinite(value_threshold) or value_threshold < 0):
        raise ValueError("Value threshold must be a finite nonnegative real scalar")
    if not isinstance(frame, pd.DataFrame) or not frame.index.is_unique:
        raise ValueError("Customer frame must have a unique index")
    if (not frame.customerID.is_unique or frame.customerID.isna().any()
            or not frame.customerID.map(lambda value: isinstance(value, str) and bool(value.strip())).all()):
        raise ValueError("Customer IDs must be unique, nonempty strings")
    result = frame.copy()
    p, value = validate_probabilities(result["p"]), _fee_values(result["MonthlyCharges"])
    result["high_value"] = value >= value_threshold
    result["high_risk"] = p >= risk_threshold
    result["risk_value_quadrant"] = np.char.add(np.where(result.high_value, "HV_", "LV_"), np.where(result.high_risk, "HR", "LR"))
    result["quadrant_label"] = result["risk_value_quadrant"].map(QUADRANTS)
    result["priority_weight"] = p*value
    order = result.sort_values(["priority_weight", "customerID"], ascending=[False, True], kind="mergesort").index
    ranks = pd.Series(np.arange(1, len(result)+1), index=order)
    result["priority_rank"] = ranks.reindex(result.index).astype(np.int64)
    return result


def summarize_quadrants(frame):
    output = []
    for split, part in frame.groupby("split", sort=False):
        fees, weights = float(part.MonthlyCharges.sum()), float(part.priority_weight.sum())
        for quadrant, label in QUADRANTS.items():
            sub = part.loc[part.risk_value_quadrant.eq(quadrant)]
            output.append({"split": split, "quadrant": quadrant, "quadrant_label": label, "count": len(sub),
                           "customer_share": len(sub)/len(part), "monthly_charge_sum": float(sub.MonthlyCharges.sum()),
                           "monthly_charge_share": float(sub.MonthlyCharges.sum())/fees,
                           "mean_p": float(sub.p.mean()) if len(sub) else None,
                           "observed_churn_rate": float(sub.y.mean()) if len(sub) else None,
                           "observed_churn_count": int(sub.y.sum()), "priority_weight_sum": float(sub.priority_weight.sum()),
                           "priority_weight_share": float(sub.priority_weight.sum())/weights if weights else None,
                           "monthly_charge_mean": float(sub.MonthlyCharges.mean()) if len(sub) else None,
                           "tenure_mean": float(sub.tenure.mean()) if len(sub) else None})
    return pd.DataFrame(output)


def summarize_clusters(frame):
    output = []
    for split, part in frame.groupby("split", sort=False):
        for algorithm, column in (("KMeans", "kmeans_cluster"), ("DBSCAN", "dbscan_cluster")):
            for cluster, sub in part.groupby(column, sort=True):
                row = {"split": split, "algorithm": algorithm, "cluster": int(cluster), "is_noise": int(cluster) == -1,
                       "count": len(sub), "share": len(sub)/len(part), "mean_p": float(sub.p.mean()),
                       "observed_churn_rate": float(sub.y.mean()), "monthly_charge_mean": float(sub.MonthlyCharges.mean()),
                       "monthly_charge_sum": float(sub.MonthlyCharges.sum()), "monthly_charge_share": float(sub.MonthlyCharges.sum()/part.MonthlyCharges.sum()),
                       "tenure_mean": float(sub.tenure.mean()), "high_risk_share": float(sub.high_risk.mean()),
                       "high_value_share": float(sub.high_value.mean()), "priority_weight_sum": float(sub.priority_weight.sum()),
                       "internet_addon_count_mean": float(sub.internet_addon_count.mean()),
                       "month_to_month_share": float(sub.Contract.eq("Month-to-month").mean()),
                       "fiber_share": float(sub.InternetService.eq("Fiber optic").mean())}
                for name in ("phone_service", "multiple_lines", "automatic_payment", "paperless_billing"):
                    row[name+"_share"] = float(sub[name].mean())
                output.append(row)
    return pd.DataFrame(output)


def monthly_concentration(frame, target=.60):
    output, summary = [], []
    for split, part in frame.groupby("split", sort=False):
        groups = part.groupby("MonthlyCharges", sort=True).size().sort_index(ascending=False)
        cumulative_customers, cumulative_charge, total = 0, 0.0, float(part.MonthlyCharges.sum())
        first = None
        for rank, (fee, count) in enumerate(groups.items(), start=1):
            previous_share = cumulative_charge/total
            cumulative_customers += int(count)
            cumulative_charge += float(fee)*int(count)
            share = cumulative_charge/total
            row = {"split": split, "rank_group": rank, "monthly_charge_boundary": float(fee), "group_customers": int(count),
                   "cumulative_customers": cumulative_customers, "cumulative_customer_share": cumulative_customers/len(part),
                   "cumulative_monthly_charge": cumulative_charge, "cumulative_monthly_charge_share": share,
                   "crosses_target_060": previous_share < target <= share}
            output.append(row)
            if first is None and share >= target:
                first = row.copy()
                first.update(total_customers=len(part), total_monthly_charge=total, target=target,
                             previous_cumulative_share=previous_share,
                             method="Smallest descending-fee prefix covering target without splitting equal-fee groups; not profit/CLV")
        if first is None:
            raise ValueError("No positive monthly-fee total to concentrate")
        summary.append(first)
    return pd.DataFrame(output), summary
