"""Import and version smoke test for the Azure churn/CLV environment."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import platform
import sys


CORE_PACKAGES = {
    "numpy": "numpy",
    "pandas": "pandas",
    "scipy": "scipy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "plotly": "plotly",
    "scikit-learn": "sklearn",
    "imbalanced-learn": "imblearn",
    "jupyterlab": "jupyterlab",
    "sqlalchemy": "sqlalchemy",
    "openpyxl": "openpyxl",
}

ADVANCED_PACKAGES = {
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
    "optuna": "optuna",
    "shap": "shap",
    "lime": "lime",
    "statsmodels": "statsmodels",
    "dowhy": "dowhy",
    "lifetimes": "lifetimes",
}

OPTIONAL_PACKAGES = {
    "pyspark": "pyspark",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--advanced", action="store_true", help="also check the advanced stack"
    )
    parser.add_argument(
        "--optional", action="store_true", help="also check optional PySpark"
    )
    args = parser.parse_args()

    packages = dict(CORE_PACKAGES)
    if args.advanced:
        packages.update(ADVANCED_PACKAGES)
    if args.optional:
        packages.update(OPTIONAL_PACKAGES)

    print(f"Python: {sys.version.split()[0]}")
    print(f"Platform: {platform.platform()}")
    failed = []
    for distribution, module_name in packages.items():
        try:
            importlib.import_module(module_name)
            version = importlib.metadata.version(distribution)
            print(f"OK   {distribution}=={version}")
        except Exception as exc:  # import-time binary/dependency errors matter here
            failed.append(distribution)
            print(f"FAIL {distribution}: {type(exc).__name__}: {exc}")
    if failed:
        print("Failed packages: " + ", ".join(failed))
        return 1
    print("All requested Python package groups imported successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
