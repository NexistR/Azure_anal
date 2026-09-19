"""W3 business-contract tests using synthetic customers and an optional W1 baseline.

Run from the project root with::

    python -m unittest discover -s tests -p "test_w3*.py" -v

The small fixtures are deliberately unlike the real population: this detects
sample-dependent clipping, full-population fitting, and accidental row removal.
The optional integration case checks the frozen source without writing to it.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.exceptions import NotFittedError

from src.data.clean import TelcoCleaner, load_config, read_raw
from src.data.preprocess import build_preprocessor, split_xy


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADD_ONS = (
    "OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport",
    "StreamingTV", "StreamingMovies",
)


def customer(identifier: str, **changes) -> dict:
    """A synthetic valid customer, independently specified from the config."""
    row = {
        "customerID": identifier, "gender": "Female", "SeniorCitizen": "0",
        "Partner": "No", "Dependents": "No", "tenure": "12",
        "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "DSL",
        "OnlineSecurity": "No", "OnlineBackup": "Yes", "DeviceProtection": "No",
        "TechSupport": "Yes", "StreamingTV": "No", "StreamingMovies": "No",
        "Contract": "Month-to-month", "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check", "MonthlyCharges": "20.5",
        "TotalCharges": "120.25", "Churn": "No",
    }
    row.update(changes)
    return row


def raw_fixture() -> pd.DataFrame:
    return pd.DataFrame([
        customer("synthetic-new", tenure="0", TotalCharges=" \t "),
        customer("synthetic-fiber", InternetService="Fiber optic", Churn="Yes",
                 SeniorCitizen="1", MonthlyCharges="40", TotalCharges="90"),
        customer("synthetic-no-internet", InternetService="No", MonthlyCharges="60",
                 TotalCharges="110", **{name: "No internet service" for name in ADD_ONS}),
        customer("synthetic-no-phone", PhoneService="No", MultipleLines="No phone service",
                 MonthlyCharges="80", TotalCharges="140", Churn="Yes"),
    ], index=[17, 8, 32, 5])


class CleaningContractTests(unittest.TestCase):
    def setUp(self):
        self.raw = raw_fixture()

    def test_c01_c02_blanks_become_tracked_unknowns_without_dropping_customers(self):
        for missing in ("", " ", "\t\n", None, np.nan):
            with self.subTest(missing=repr(missing)):
                raw = pd.DataFrame([customer("synthetic-empty", tenure="0", TotalCharges=missing)])
                cleaned = TelcoCleaner().fit_transform(raw)
                self.assertEqual(len(cleaned), 1)
                self.assertTrue(pd.isna(cleaned.at[0, "TotalCharges"]))
                self.assertEqual(cleaned.at[0, "total_charges_missing"], 1)
                self.assertEqual(cleaned.at[0, "tenure_zero"], 1)

    def test_c01_zero_charge_is_known_and_distinct_from_missing(self):
        raw = pd.DataFrame([customer("synthetic-zero", TotalCharges="0")])
        cleaned = TelcoCleaner().fit_transform(raw)
        self.assertEqual(cleaned.at[0, "TotalCharges"], 0.0)
        self.assertEqual(cleaned.at[0, "total_charges_missing"], 0)

    def test_c01_nonempty_unparseable_charges_raise_instead_of_becoming_missing(self):
        for value in ("unknown", "12 USD", "NaN", "null", "1,000.00"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "TotalCharges"):
                TelcoCleaner().fit_transform(pd.DataFrame([customer("synthetic-bad", TotalCharges=value)]))

    def test_c03_c04_structural_categories_are_preserved_and_networks_are_applicable(self):
        cleaned = TelcoCleaner().fit_transform(self.raw)
        self.assertEqual(cleaned["internet_applicable"].tolist(), [1, 1, 0, 1])
        for name in ADD_ONS:
            self.assertEqual(cleaned.at[32, name], "No internet service")
        self.assertEqual(cleaned.at[5, "MultipleLines"], "No phone service")
        self.assertEqual(cleaned["customerID"].tolist(), self.raw["customerID"].tolist())

    def test_c03_each_internet_service_rejects_both_directions_of_logical_conflict(self):
        for field in ADD_ONS:
            for row, value in ((17, "No internet service"), (32, "Yes"), (32, "No")):
                with self.subTest(field=field, row=row, value=value):
                    broken = self.raw.copy(deep=True)
                    broken.at[row, field] = value
                    with self.assertRaisesRegex(ValueError, field):
                        TelcoCleaner().fit_transform(broken)

    def test_c04_phone_service_rejects_both_directions_of_logical_conflict(self):
        for row, value in ((17, "No phone service"), (5, "Yes"), (5, "No")):
            with self.subTest(row=row, value=value):
                broken = self.raw.copy(deep=True)
                broken.at[row, "MultipleLines"] = value
                with self.assertRaisesRegex(ValueError, "MultipleLines"):
                    TelcoCleaner().fit_transform(broken)

    def test_c04_unknown_or_missing_categories_are_rejected(self):
        for field, value in (("InternetService", "Yes"), ("Contract", "Weekly"),
                             ("gender", "unknown"), ("OnlineSecurity", None),
                             ("Partner", ""), ("PaymentMethod", "Cash")):
            with self.subTest(field=field, value=value):
                broken = self.raw.copy(deep=True)
                broken.at[17, field] = value
                with self.assertRaisesRegex(ValueError, field):
                    TelcoCleaner().fit_transform(broken)

    def test_whitespace_normalization_is_explicit_and_numerical_types_are_stable(self):
        raw = pd.DataFrame([customer("  synthetic-trim  ", Contract=" Two year ",
                                    TotalCharges=" 125.75 ", tenure=" 12 ", Churn=" Yes ")])
        cleaned = TelcoCleaner().fit_transform(raw)
        self.assertEqual(cleaned.at[0, "customerID"], "synthetic-trim")
        self.assertEqual(cleaned.at[0, "Contract"], "Two year")
        self.assertEqual(cleaned.at[0, "TotalCharges"], 125.75)
        self.assertEqual(cleaned.at[0, "churn_label"], 1)
        for field in ("tenure", "SeniorCitizen", "churn_label", "total_charges_missing",
                      "tenure_zero", "internet_applicable"):
            self.assertTrue(pd.api.types.is_integer_dtype(cleaned[field]), field)
        for field in ("TotalCharges", "MonthlyCharges"):
            self.assertTrue(pd.api.types.is_float_dtype(cleaned[field]), field)

    def test_c05_ids_labels_order_and_custom_index_survive_cleaning(self):
        cleaned = TelcoCleaner().fit_transform(self.raw)
        assert_series_equal(cleaned["customerID"], self.raw["customerID"])
        assert_series_equal(cleaned["Churn"], self.raw["Churn"])
        self.assertEqual(cleaned["churn_label"].tolist(), [0, 1, 0, 1])
        self.assertEqual(cleaned.index.tolist(), [17, 8, 32, 5])

    def test_c05_empty_or_nonstring_customer_ids_raise(self):
        for value in ("", " \t", None, np.nan, 123):
            with self.subTest(value=repr(value)):
                raw = pd.DataFrame([customer(value)])
                with self.assertRaisesRegex(ValueError, "customerID"):
                    TelcoCleaner().fit_transform(raw)

    def test_c05_duplicate_ids_are_detected_after_whitespace_normalization(self):
        raw = pd.DataFrame([customer("synthetic-dupe"), customer(" synthetic-dupe ")])
        with self.assertRaisesRegex(ValueError, "customerID.*unique"):
            TelcoCleaner().fit_transform(raw)

    def test_c05_missing_unknown_or_numeric_labels_raise(self):
        for value in (None, "", "yes", "Unknown", "1", 1):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(ValueError, "Churn"):
                TelcoCleaner().fit_transform(pd.DataFrame([customer("synthetic-label", Churn=value)]))

    def test_c06_illegal_numerical_values_raise(self):
        cases = {
            "MonthlyCharges": (None, np.nan, "", "0", "-0.1", "inf", "-inf", True),
            "TotalCharges": ("-1", "inf", "-inf", True, 1 + 2j),
            "tenure": (None, "-1", "1.5", "inf", True, str(2**63)),
            "SeniorCitizen": (None, "2", "-1", "0.5", True),
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)):
                    raw = pd.DataFrame([customer("synthetic-number", **{field: value})])
                    with self.assertRaisesRegex(ValueError, field):
                        TelcoCleaner().fit_transform(raw)

    def test_c06_legal_values_beyond_observed_population_are_not_clipped(self):
        raw = pd.DataFrame([customer("synthetic-extreme", tenure="240",
                                    MonthlyCharges="5000", TotalCharges="1200000")])
        cleaner = TelcoCleaner().fit(self.raw)
        cleaned = cleaner.transform(raw)
        self.assertEqual(cleaned.at[0, "tenure"], 240)
        self.assertEqual(cleaned.at[0, "MonthlyCharges"], 5000)
        self.assertEqual(cleaned.at[0, "TotalCharges"], 1200000)

    def test_c07_historical_total_is_not_replaced_with_current_price_product(self):
        raw = pd.DataFrame([customer("synthetic-discount", tenure="12",
                                    MonthlyCharges="80", TotalCharges="0.25")])
        cleaned = TelcoCleaner().fit_transform(raw)
        self.assertEqual(cleaned.at[0, "TotalCharges"], 0.25)
        self.assertNotEqual(cleaned.at[0, "TotalCharges"], 12 * 80)

    def test_schema_missing_unknown_duplicate_and_partial_derived_columns_raise(self):
        variants = {
            "missing": self.raw.drop(columns="TotalCharges"),
            "extra": self.raw.assign(region="invented"),
            "partial derived": self.raw.assign(churn_label=[0, 1, 0, 1]),
            "duplicate": pd.concat([self.raw, self.raw[["Churn"]]], axis=1),
            "empty": self.raw.iloc[:0],
        }
        for name, frame in variants.items():
            with self.subTest(schema=name), self.assertRaises(ValueError):
                TelcoCleaner().fit_transform(frame)

    def test_c08_c09_output_has_only_original_columns_and_four_traceable_flags(self):
        cleaned = TelcoCleaner().fit_transform(self.raw)
        expected = list(self.raw.columns) + [
            "churn_label", "total_charges_missing", "tenure_zero", "internet_applicable"
        ]
        self.assertEqual(cleaned.columns.tolist(), expected)

    def test_c10_fit_transform_does_not_change_input_and_cleaning_is_idempotent(self):
        before = self.raw.copy(deep=True)
        cleaner = TelcoCleaner()
        first = cleaner.fit_transform(self.raw)
        second = cleaner.transform(first)
        third = cleaner.transform(self.raw)
        assert_frame_equal(self.raw, before)
        assert_frame_equal(first, second)
        assert_frame_equal(first, third)
        self.assertIsNot(first, second)

    def test_existing_derived_values_must_agree_with_sources(self):
        cleaner = TelcoCleaner().fit(self.raw)
        cleaned = cleaner.transform(self.raw)
        for field in ("churn_label", "total_charges_missing", "tenure_zero", "internet_applicable"):
            with self.subTest(field=field):
                broken = cleaned.copy(deep=True)
                broken.at[17, field] = 1 - broken.at[17, field]
                with self.assertRaisesRegex(ValueError, field):
                    cleaner.transform(broken)

    def test_fit_freezes_private_configuration_and_json_configuration_is_supported(self):
        config = load_config()
        cleaner = TelcoCleaner(config).fit(self.raw)
        config["label_mapping"]["Yes"] = 0
        self.assertEqual(cleaner.transform(self.raw)["churn_label"].sum(), 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(load_config()), encoding="utf-8")
            assert_frame_equal(TelcoCleaner(path).fit_transform(self.raw), cleaner.transform(self.raw))

    def test_configuration_cannot_introduce_label_features_or_reverse_labels(self):
        config = load_config()
        config["features"]["categorical"].append("Churn")
        with self.assertRaises(ValueError):
            build_preprocessor(config)
        config = load_config()
        config["label_mapping"] = {"No": 1, "Yes": 0}
        with self.assertRaises(ValueError):
            TelcoCleaner(config).fit(self.raw)

    def test_config_rejects_nonfinite_or_nonnumeric_range_boundaries(self):
        for bound in ("minimum", "maximum"):
            for value in (float("nan"), float("inf"), float("-inf"), "0", True):
                with self.subTest(bound=bound, value=repr(value)):
                    config = load_config()
                    config["numeric_rules"]["MonthlyCharges"][bound] = value
                    with self.assertRaisesRegex(ValueError, "MonthlyCharges"):
                        TelcoCleaner(config).fit(self.raw)

    def test_config_rejects_truthy_strings_and_numbers_as_boolean_rules(self):
        for flag in ("integer", "minimum_inclusive"):
            for value in ("false", "true", 0, 1, None):
                with self.subTest(flag=flag, value=repr(value)):
                    config = load_config()
                    config["numeric_rules"]["MonthlyCharges"][flag] = value
                    with self.assertRaisesRegex(ValueError, flag):
                        build_preprocessor(config)

    def test_config_rejects_reversed_empty_and_unrepresentable_integer_ranges(self):
        for field, lower, upper, inclusive in (
            ("MonthlyCharges", 100, 10, True),
            ("MonthlyCharges", 10, 10, False),
            ("tenure", 1.1, 1.9, True),
            ("tenure", 2**63, None, True),
            ("tenure", None, -(2**63)-1, True),
        ):
            with self.subTest(field=field, lower=lower, upper=upper, inclusive=inclusive):
                config = load_config()
                config["numeric_rules"][field].update(
                    minimum=lower, maximum=upper, minimum_inclusive=inclusive)
                with self.assertRaisesRegex(ValueError, field):
                    TelcoCleaner(config).fit(self.raw)

    def test_config_cannot_register_null_empty_or_untrimmed_categories(self):
        for value in (None, "", " ", "\t", " Monthly ", float("nan"), 1):
            with self.subTest(value=repr(value)):
                config = load_config()
                config["categories"]["Contract"].append(value)
                with self.assertRaisesRegex(ValueError, "Contract"):
                    build_preprocessor(config)
        config = load_config()
        config["categories"]["SeniorCitizen"] = [False, True]
        with self.assertRaisesRegex(ValueError, "SeniorCitizen"):
            build_preprocessor(config)

    def test_large_integer_strings_are_exact_even_with_float_elsewhere_in_column(self):
        raw = pd.DataFrame([
            customer("synthetic-large-exact", tenure="9007199254740993"),
            customer("synthetic-int64-max", tenure=str(2**63-1)),
            customer("synthetic-float-integer", tenure=12.0),
        ])
        cleaner = TelcoCleaner().fit(raw)
        cleaned = cleaner.transform(raw)
        self.assertEqual(cleaned["tenure"].tolist(), [9007199254740993, 2**63-1, 12])
        assert_frame_equal(cleaner.transform(cleaned), cleaned)

    def test_large_fractional_and_out_of_int64_strings_are_rejected(self):
        for value in ("9007199254740992.5", "9223372036854775806.5", str(2**63), str(-(2**63)-1)):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "tenure"):
                TelcoCleaner().fit_transform(pd.DataFrame([customer("synthetic-large-invalid", tenure=value)]))

    def test_integer_representation_limits_are_distinct_from_configured_business_bounds(self):
        config = load_config()
        config["numeric_rules"]["tenure"]["minimum"] = None
        raw = pd.DataFrame([
            customer("synthetic-int64-min", tenure=str(-(2**63))),
            customer("synthetic-int64-max", tenure=str(2**63-1)),
        ])
        cleaned = TelcoCleaner(config).fit_transform(raw)
        self.assertEqual(cleaned["tenure"].tolist(), [-(2**63), 2**63-1])
        with self.assertRaisesRegex(ValueError, "tenure"):
            TelcoCleaner().fit_transform(raw)

    def test_transform_before_fit_raises_and_saved_cleaner_is_reusable(self):
        with self.assertRaises(NotFittedError):
            TelcoCleaner().transform(self.raw)
        cleaner = TelcoCleaner().fit(self.raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cleaner.joblib"
            joblib.dump(cleaner, path)
            loaded = joblib.load(path)
            assert_frame_equal(loaded.transform(self.raw), cleaner.transform(self.raw))

    def test_read_raw_preserves_literal_na_ids_blank_fields_and_source_bytes(self):
        raw = pd.DataFrame([customer("NA", TotalCharges=" "), customer("synthetic-csv")])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            raw.to_csv(path, index=False, encoding="utf-8-sig")
            before = path.read_bytes()
            parsed = read_raw(path)
            self.assertEqual(parsed.at[0, "customerID"], "NA")
            self.assertEqual(parsed.at[0, "TotalCharges"], " ")
            TelcoCleaner().fit_transform(parsed)
            self.assertEqual(path.read_bytes(), before)


class PreprocessingBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.cleaned = TelcoCleaner().fit_transform(raw_fixture())
        self.X, self.y, self.ids = split_xy(self.cleaned)

    def test_c05_split_excludes_id_and_both_labels_and_returns_independent_objects(self):
        before = self.cleaned.copy(deep=True)
        self.assertEqual(self.X.shape, (4, 22))
        for forbidden in ("customerID", "Churn", "churn_label"):
            self.assertNotIn(forbidden, self.X)
        assert_series_equal(self.y, self.cleaned["churn_label"])
        assert_series_equal(self.ids, self.cleaned["customerID"])
        self.X.at[17, "MonthlyCharges"] = 999
        self.y.at[17] = 1
        self.ids.at[17] = "changed-only-in-copy"
        assert_frame_equal(self.cleaned, before)

    def test_split_rejects_extra_label_derived_fields_and_raw_input(self):
        for frame in (raw_fixture(), self.cleaned.assign(Churn_encoded=self.y),
                      self.cleaned.assign(cancelled_at="2026-01-01")):
            with self.subTest(columns=frame.columns.tolist()), self.assertRaises(ValueError):
                split_xy(frame)

    def test_c05_preprocessor_rejects_leakage_fields_and_missing_predictors(self):
        pipeline = build_preprocessor().fit(self.X)
        for field in ("customerID", "Churn", "churn_label", "Churn_encoded", "cancel_reason"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                pipeline.transform(self.X.assign(**{field: "leak"}))
        with self.assertRaises(ValueError):
            pipeline.transform(self.X.drop(columns="Contract"))

    def test_c10_training_median_and_scaling_ignore_validation_extremes(self):
        train_raw = pd.DataFrame([
            customer("synthetic-train-0", tenure="0", MonthlyCharges="10", TotalCharges=" "),
            customer("synthetic-train-1", tenure="10", MonthlyCharges="20", TotalCharges="100"),
            customer("synthetic-train-2", tenure="20", MonthlyCharges="30", TotalCharges="300"),
        ])
        validation_raw = pd.DataFrame([
            customer("synthetic-validation-high", tenure="1000", MonthlyCharges="9000", TotalCharges="999999"),
            customer("synthetic-validation-na", tenure="1", MonthlyCharges="40", TotalCharges=" "),
        ])
        train, _, _ = split_xy(TelcoCleaner().fit_transform(train_raw))
        validation, _, _ = split_xy(TelcoCleaner().fit_transform(validation_raw))
        pipeline = build_preprocessor().fit(train)
        numeric = pipeline.named_steps["columns"].named_transformers_["numeric"]
        imputer = numeric.named_steps["imputer"]
        scaler = numeric.named_steps["scaler"]
        np.testing.assert_allclose(imputer.statistics_, [10, 20, 200])
        np.testing.assert_allclose(scaler.mean_, [10, 20, 200])
        np.testing.assert_allclose(scaler.var_, [200 / 3, 200 / 3, 20000 / 3])
        before = (imputer.statistics_.copy(), scaler.mean_.copy(), scaler.var_.copy())
        result = pipeline.transform(validation)
        for previous, current in zip(before, (imputer.statistics_, scaler.mean_, scaler.var_)):
            np.testing.assert_array_equal(previous, current)
        names = pipeline.get_feature_names_out().tolist()
        total_column = names.index("numeric__TotalCharges")
        self.assertAlmostEqual(result[1, total_column], 0.0)
        self.assertGreater(result[0, total_column], 100)
        self.assertTrue(np.isfinite(result).all())

    def test_legal_category_absent_from_training_keeps_stable_named_one_hot_columns(self):
        train = self.X.loc[[17, 8]].copy()
        validation = self.X.loc[[32]].copy()
        validation["Contract"] = "Two year"
        pipeline = build_preprocessor().fit(train)
        train_values, validation_values = pipeline.transform(train), pipeline.transform(validation)
        names = pipeline.get_feature_names_out().tolist()
        self.assertEqual(train_values.shape[1], validation_values.shape[1])
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), train_values.shape[1])
        for name in ("categorical__InternetService_No", "categorical__OnlineSecurity_No internet service",
                     "categorical__Contract_Two year"):
            index = names.index(name)
            self.assertEqual(train_values[:, index].sum(), 0)
            self.assertEqual(validation_values[0, index], 1)

    def test_preprocessor_rejects_unknown_category_and_inconsistent_flags(self):
        pipeline = build_preprocessor().fit(self.X)
        cases = (("Contract", "Daily"), ("TotalCharges", "broken"),
                 ("internet_applicable", 0), ("total_charges_missing", 0),
                 ("tenure_zero", 0), ("MonthlyCharges", np.inf),
                 ("OnlineSecurity", "No internet service"))
        for field, value in cases:
            with self.subTest(field=field):
                broken = self.X.copy(deep=True)
                if field == "TotalCharges":
                    broken[field] = broken[field].astype(object)
                broken.at[17, field] = value
                with self.assertRaisesRegex(ValueError, field):
                    pipeline.transform(broken)

    def test_all_training_totals_missing_preserves_column_and_explicit_missingness(self):
        raw = pd.DataFrame([
            customer("synthetic-all-na-1", tenure="0", TotalCharges=" "),
            customer("synthetic-all-na-2", tenure="0", TotalCharges="", MonthlyCharges="30"),
        ])
        cleaned = TelcoCleaner().fit_transform(raw)
        train, _, _ = split_xy(cleaned)
        pipeline = build_preprocessor().fit(train)
        values = pipeline.transform(train)
        names = pipeline.get_feature_names_out().tolist()
        self.assertTrue(np.isfinite(values).all())
        np.testing.assert_array_equal(values[:, names.index("numeric__TotalCharges")], [0, 0])
        np.testing.assert_array_equal(values[:, names.index("binary__total_charges_missing")], [1, 1])
        self.assertTrue(cleaned["TotalCharges"].isna().all())
        observed, _, _ = split_xy(TelcoCleaner().fit_transform(pd.DataFrame([customer("synthetic-later")])))
        later_values = pipeline.transform(observed)
        self.assertEqual(later_values.shape[1], values.shape[1])
        self.assertTrue(np.isfinite(later_values).all())
        self.assertEqual(later_values[0, names.index("binary__total_charges_missing")], 0)

    def test_preprocessing_preserves_feature_input_and_binary_semantics(self):
        before = self.X.copy(deep=True)
        pipeline = build_preprocessor()
        values = pipeline.fit_transform(self.X)
        assert_frame_equal(self.X, before)
        self.assertTrue(np.isfinite(values).all())
        self.assertEqual(values.shape[0], len(self.X))
        names = pipeline.get_feature_names_out().tolist()
        for field in ("total_charges_missing", "tenure_zero", "internet_applicable"):
            np.testing.assert_array_equal(values[:, names.index(f"binary__{field}")], self.X[field])
        np.testing.assert_array_equal(values, pipeline.transform(self.X))

    def test_column_reordering_is_safe_and_duplicate_columns_are_rejected(self):
        pipeline = build_preprocessor().fit(self.X)
        np.testing.assert_array_equal(pipeline.transform(self.X), pipeline.transform(self.X.iloc[:, ::-1]))
        with self.assertRaises(ValueError):
            pipeline.transform(pd.concat([self.X, self.X[["Contract"]]], axis=1))

    def test_saved_preprocessor_has_identical_values_and_feature_names(self):
        pipeline = build_preprocessor().fit(self.X)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preprocessor.joblib"
            joblib.dump(pipeline, path)
            loaded = joblib.load(path)
            np.testing.assert_array_equal(loaded.transform(self.X), pipeline.transform(self.X))
            np.testing.assert_array_equal(loaded.get_feature_names_out(), pipeline.get_feature_names_out())


class FrozenSourceIntegrationTests(unittest.TestCase):
    def test_frozen_w1_source_matches_w2_baseline_and_is_unchanged(self):
        path = PROJECT_ROOT / "data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv"
        if not path.is_file():
            self.skipTest("Optional local raw CSV is absent; synthetic contract tests still run")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, "88be4b93fbe0cc83421af1c503794c97c342eca914c1576db7c276e61d61358a")
        raw = read_raw(path)
        cleaned = TelcoCleaner().fit_transform(raw)
        self.assertEqual(raw.shape, (7043, 21))
        self.assertEqual(cleaned.shape, (7043, 25))
        self.assertEqual(cleaned["customerID"].nunique(), 7043)
        self.assertEqual(set(cleaned["customerID"]), set(raw["customerID"]))
        self.assertEqual(cleaned["Churn"].value_counts().to_dict(), {"No": 5174, "Yes": 1869})
        self.assertEqual(cleaned["churn_label"].sum(), 1869)
        self.assertEqual(cleaned["TotalCharges"].isna().sum(), 11)
        self.assertEqual(cleaned["TotalCharges"].notna().sum(), 7032)
        self.assertEqual(cleaned["tenure_zero"].sum(), 11)
        self.assertEqual(cleaned["internet_applicable"].sum(), 5517)
        self.assertEqual(cleaned["total_charges_missing"].tolist(), cleaned["tenure_zero"].tolist())
        for field in ADD_ONS:
            self.assertEqual(cleaned[field].eq("No internet service").sum(), 1526)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
