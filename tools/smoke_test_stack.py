"""Run small functional tests for the configured analytics stack."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]


def test_core() -> None:
    import matplotlib.pyplot as plt
    import plotly.express as px

    X, y = make_classification(n_samples=240, n_features=8, random_state=42)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=42
    )
    model = LogisticRegression(max_iter=1000).fit(X_train, y_train)
    score = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    assert 0.5 <= score <= 1.0

    with tempfile.TemporaryDirectory() as temp_dir:
        figure_path = Path(temp_dir) / "smoke.png"
        plt.figure()
        plt.plot([0, 1], [0, 1])
        plt.savefig(figure_path)
        plt.close()
        assert figure_path.stat().st_size > 0
        assert "plotly" in px.scatter(x=[1, 2], y=[2, 3]).to_html().lower()
    print(f"OK core: logistic ROC-AUC={score:.3f}, Matplotlib and Plotly rendered")


def test_advanced() -> None:
    import shap
    from catboost import CatBoostClassifier
    from dowhy import CausalModel
    from lifetimes import BetaGeoFitter, GammaGammaFitter
    from lightgbm import LGBMClassifier
    from lime.lime_tabular import LimeTabularExplainer
    import optuna
    from xgboost import XGBClassifier

    X, y = make_classification(n_samples=180, n_features=6, random_state=7)
    models = [
        XGBClassifier(n_estimators=8, max_depth=2, random_state=7),
        LGBMClassifier(n_estimators=8, max_depth=2, random_state=7, verbosity=-1),
        CatBoostClassifier(
            iterations=8,
            depth=2,
            verbose=False,
            random_seed=7,
            allow_writing_files=False,
        ),
    ]
    for model in models:
        model.fit(X, y)
        assert model.predict_proba(X[:3]).shape == (3, 2)

    explainer = shap.TreeExplainer(models[0])
    assert len(explainer.shap_values(X[:2])) == 2
    LimeTabularExplainer(X).explain_instance(
        X[0], models[0].predict_proba, num_features=2
    )

    study = optuna.create_study(direction="minimize")
    study.optimize(lambda trial: (trial.suggest_float("x", -1, 1) - 0.2) ** 2, n_trials=2)

    transactions = pd.DataFrame(
        {
            "frequency": [1.0, 2.0, 3.0, 4.0, 2.0],
            "recency": [2.0, 4.0, 5.0, 8.0, 3.0],
            "T": [10.0, 10.0, 10.0, 10.0, 10.0],
            "monetary": [20.0, 28.0, 35.0, 41.0, 25.0],
        }
    )
    bgf = BetaGeoFitter(penalizer_coef=0.01).fit(
        transactions["frequency"], transactions["recency"], transactions["T"]
    )
    ggf = GammaGammaFitter(penalizer_coef=0.01).fit(
        transactions["frequency"], transactions["monetary"]
    )
    assert np.isfinite(bgf.conditional_expected_number_of_purchases_up_to_time(
        3, transactions["frequency"], transactions["recency"], transactions["T"]
    )).all()
    assert np.isfinite(ggf.conditional_expected_average_profit(
        transactions["frequency"], transactions["monetary"]
    )).all()

    rng = np.random.default_rng(11)
    treatment = rng.integers(0, 2, 200)
    outcome = 2.0 * treatment + rng.normal(size=200)
    causal_data = pd.DataFrame({"treatment": treatment, "outcome": outcome})
    causal_model = CausalModel(
        data=causal_data,
        treatment="treatment",
        outcome="outcome",
        graph="digraph { treatment -> outcome; }",
    )
    estimand = causal_model.identify_effect(proceed_when_unidentifiable=True)
    estimate = causal_model.estimate_effect(
        estimand, method_name="backdoor.linear_regression"
    )
    assert np.isfinite(float(estimate.value))
    print("OK advanced: boosting, SHAP, LIME, Optuna, CLV, and DoWhy")


def test_spark() -> None:
    java_home = ROOT / ".tools" / "jdk-17"
    os.environ.setdefault("JAVA_HOME", str(java_home))
    os.environ.setdefault("PYSPARK_PYTHON", str(ROOT / ".venv" / "Scripts" / "python.exe"))
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.master("local[1]")
        .appName("pj-mic-smoke")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        assert spark.range(10).count() == 10
        print(f"OK optional: Spark {spark.version} local session")
    finally:
        spark.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advanced", action="store_true")
    parser.add_argument("--spark", action="store_true")
    args = parser.parse_args()
    test_core()
    if args.advanced:
        test_advanced()
    if args.spark:
        test_spark()
    print("All requested smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
