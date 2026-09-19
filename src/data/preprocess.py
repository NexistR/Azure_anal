"""Training-only imputation, scaling and explicit category encoding for W3.

Only the numerical interface is demonstrated this week; no churn estimator is
trained here. IDs and both label representations stay outside the feature matrix.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from .clean import TelcoCleaner, _fail_rows, _parse_numeric, _resolve_config


def feature_columns(config=None) -> list[str]:
    """Return the exact, ordered whitelist of 22 safe input fields."""
    features = _resolve_config(config)["features"]
    return features["numeric"] + features["categorical"] + features["binary"]


def split_xy(cleaned: pd.DataFrame, config=None) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Validate a cleaned table and return independent X, churn label and ID copies."""
    resolved = _resolve_config(config)
    if not isinstance(cleaned, pd.DataFrame):
        raise ValueError("split_xy requires a cleaned pandas DataFrame")
    expected = resolved["raw_columns"] + resolved["derived_columns"]
    if cleaned.columns.duplicated().any() or set(cleaned.columns) != set(expected):
        raise ValueError("split_xy requires exactly the 25 cleaned fields; no extra label/ID-derived fields")
    checked = TelcoCleaner(resolved).fit_transform(cleaned)
    return (
        checked.loc[:, feature_columns(resolved)].copy(deep=True),
        checked["churn_label"].copy(deep=True),
        checked["customerID"].copy(deep=True),
    )


class FeatureContract(TransformerMixin, BaseEstimator):
    """Reject extra fields, unknown categories and inconsistent cleaning flags.

    ColumnTransformer's normal remainder='drop' would silently hide an accidental
    label column. Validating the whitelist first makes that mistake an error.
    """

    def __init__(self, config=None):
        self.config = config

    def _validate_frame(self, X: pd.DataFrame, config: dict) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise ValueError("Preprocessor requires a pandas DataFrame with feature names")
        if not all(isinstance(name, str) for name in X.columns):
            raise ValueError("Feature column names must all be strings")
        if X.columns.duplicated().any():
            raise ValueError("Feature schema has duplicate column names")
        expected = feature_columns(config)
        actual = set(X.columns)
        if actual != set(expected):
            raise ValueError(
                "Feature whitelist violation; "
                f"missing={sorted(set(expected) - actual)}, extra={sorted(actual - set(expected))}. "
                "customerID, Churn, churn_label and all unregistered fields are forbidden."
            )
        if X.empty:
            raise ValueError("Preprocessor needs at least one row")
        result = X.loc[:, expected].copy(deep=True)
        for name in config["numeric_rules"]:
            result[name] = _parse_numeric(result[name], name, config)
        for name in config["features"]["categorical"]:
            allowed = config["categories"][name]
            _fail_rows(name, f"unknown/missing category; allowed={allowed}", ~result[name].isin(allowed))
        for name in config["features"]["binary"]:
            _fail_rows(name, "cleaning flag must be numeric 0 or 1", ~result[name].isin([0, 1]))
            result[name] = result[name].astype("int64")
        structural = config["structural_categories"]
        no_internet = result["InternetService"].eq(structural["no_internet"])
        for name in config["internet_service_columns"]:
            _fail_rows(name, "contradicts InternetService applicability", no_internet.ne(result[name].eq(structural["internet_not_applicable"])))
        no_phone = result["PhoneService"].eq(structural["no_phone"])
        _fail_rows("MultipleLines", "contradicts PhoneService applicability", no_phone.ne(result["MultipleLines"].eq(structural["phone_not_applicable"])))
        checks = {
            "total_charges_missing": result["TotalCharges"].isna().astype("int64"),
            "tenure_zero": result["tenure"].eq(0).astype("int64"),
            "internet_applicable": (~no_internet).astype("int64"),
        }
        for name, computed in checks.items():
            _fail_rows(name, "derived flag must agree with its source field", result[name].ne(computed))
        return result

    def fit(self, X: pd.DataFrame, y=None):
        config = _resolve_config(self.config)
        checked = self._validate_frame(X, config)
        self.config_ = config
        self.feature_names_in_ = np.asarray(checked.columns, dtype=object)
        self.n_features_in_ = checked.shape[1]
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, "config_")
        return self._validate_frame(X, self.config_)

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        check_is_fitted(self, "config_")
        if input_features is not None and list(input_features) != list(self.feature_names_in_):
            raise ValueError("input_features must match the registered feature order")
        return self.feature_names_in_.copy()


class FiniteArrayGuard(TransformerMixin, BaseEstimator):
    """Fail if numerical transformation produces NA/inf or changes its width."""

    @staticmethod
    def _validate_array(X) -> np.ndarray:
        try:
            result = np.asarray(X, dtype=np.float64)
        except (TypeError, ValueError) as error:
            raise ValueError("Preprocessing output must be a numeric matrix") from error
        if result.ndim != 2 or not np.isfinite(result).all():
            raise ValueError("Preprocessing output must be a 2D matrix without NA or infinity")
        return result

    def fit(self, X, y=None):
        checked = self._validate_array(X)
        self.n_features_in_ = checked.shape[1]
        return self

    def transform(self, X) -> np.ndarray:
        check_is_fitted(self, "n_features_in_")
        checked = self._validate_array(X)
        if checked.shape[1] != self.n_features_in_:
            raise ValueError("Preprocessing output width changed after fit")
        return checked

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        check_is_fitted(self, "n_features_in_")
        if input_features is None:
            return np.asarray([f"x{i}" for i in range(self.n_features_in_)], dtype=object)
        if len(input_features) != self.n_features_in_:
            raise ValueError("Feature name count differs from preprocessing output width")
        return np.asarray(input_features, dtype=object)


def build_preprocessor(config=None) -> Pipeline:
    """Build an unfitted, serializable and named sklearn preprocessing Pipeline.

    Fit only on X_train. Explicit categories make output width independent of
    which legal categories occur in a split. SeniorCitizen is categorical [0, 1].
    Missingness/zero-tenure/applicability flags remain binary and unscaled.

    An entirely missing training numeric column remains present because
    keep_empty_features=True. sklearn uses numerical 0 for that exceptional
    computational fallback; the cleaned monetary values remain unknown and the
    missingness flag remains 1. This does not assert a real zero-charge amount.
    """
    resolved = _resolve_config(config)
    features = resolved["features"]
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scaler", StandardScaler()),
    ])
    categorical = Pipeline([
        ("encoder", OneHotEncoder(
            categories=[resolved["categories"][name] for name in features["categorical"]],
            handle_unknown="error",
            sparse_output=False,
            dtype=np.float64,
        )),
    ])
    columns = ColumnTransformer(
        transformers=[
            ("numeric", numeric, features["numeric"]),
            ("categorical", categorical, features["categorical"]),
            ("binary", "passthrough", features["binary"]),
        ],
        remainder="drop",
        sparse_threshold=0,
        verbose_feature_names_out=True,
    )
    return Pipeline([
        ("validate", FeatureContract(resolved)),
        ("columns", columns),
        ("finite", FiniteArrayGuard()),
    ])
