"""The input contract must reject corruption before feature engineering."""
import unittest

import numpy as np
import pandas as pd

from src.models.w7.contract import validate_frame
from tests._fixtures import cleaning_config, raw_frame, replace_value


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.config = cleaning_config()

    def test_order_and_input_immutability(self):
        frame = raw_frame().iloc[[2, 0, 1], ::-1]
        before = frame.copy(deep=True)
        actual = validate_frame(frame, self.config)
        groups = self.config["features"]
        self.assertEqual(actual.columns.tolist(), groups["numeric"] + groups["categorical"] + groups["binary"])
        self.assertEqual(actual.index.tolist(), [2, 0, 1])
        np.testing.assert_array_equal(actual.tenure, [3, 1, 2])
        pd.testing.assert_frame_equal(frame, before)

    def test_missing_extra_duplicate_columns_and_empty_rows(self):
        valid = raw_frame()
        bad = [valid.drop(columns="tenure"), valid.assign(customerID="synthetic"),
               valid.assign(Churn="Yes"), valid.assign(churn_label=1), valid.iloc[:0],
               pd.concat([valid, valid[["tenure"]]], axis=1), valid.rename(columns={"tenure": 7})]
        for frame in bad:
            with self.subTest(columns=frame.columns.tolist(), rows=len(frame)):
                with self.assertRaises(ValueError):
                    validate_frame(frame, self.config)

    def test_exact_integer_tokens_and_int64_limits(self):
        for token in ("9007199254740993", "9007199254740993.0", str(np.iinfo(np.int64).max)):
            with self.subTest(token=token):
                actual = validate_frame(replace_value(raw_frame(1), "tenure", token), self.config)
                expected = 9007199254740993 if token.startswith("9007199254740993") else np.iinfo(np.int64).max
                self.assertEqual(actual.tenure.iloc[0], expected)
        for token in ("9007199254740992.5", str(int(np.iinfo(np.int64).max) + 1), "1.5"):
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    validate_frame(replace_value(raw_frame(1), "tenure", token), self.config)
        with self.assertRaises(ValueError):
            validate_frame(replace_value(raw_frame(1), "SeniorCitizen", "0.5"), self.config)

    def test_invalid_numeric_types_missing_and_ranges(self):
        invalid = {
            "tenure": [True, 1 + 0j, np.nan, np.inf, -1, "NaN"],
            "MonthlyCharges": [True, 2 + 0j, np.nan, np.inf, -np.inf, 0, -1, ""],
            "TotalCharges": [True, 1 + 0j, np.inf, -1],
            "SeniorCitizen": [True, np.nan, 2, -1, .5],
        }
        for column, values in invalid.items():
            for value in values:
                with self.subTest(column=column, value=repr(value)):
                    with self.assertRaises(ValueError):
                        validate_frame(replace_value(raw_frame(1), column, value), self.config)
        # A finite float64 extreme is legal at validation time, even if a later
        # float32 encoding overflows. Do not invent a sample-maximum cutoff.
        extreme = replace_value(raw_frame(1), "TotalCharges", 1e308)
        self.assertEqual(validate_frame(extreme, self.config).TotalCharges.iloc[0], 1e308)

    def test_missing_total_and_derived_flags(self):
        valid = raw_frame(1)
        valid.loc[0, ["TotalCharges", "total_charges_missing", "tenure", "tenure_zero"]] = [np.nan, 1, 0, 1]
        actual = validate_frame(valid, self.config)
        self.assertTrue(pd.isna(actual.TotalCharges.iloc[0]))
        for field in ("total_charges_missing", "tenure_zero", "internet_applicable"):
            wrong = valid.copy()
            wrong[field] = 1 - wrong[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_frame(wrong, self.config)
        with self.assertRaises(ValueError):
            validate_frame(replace_value(valid, "tenure_zero", "1"), self.config)

    def test_service_applicability_and_unknown_categories(self):
        frame = raw_frame(1)
        frame.loc[0, ["InternetService", "internet_applicable"]] = ["No", 0]
        for field in self.config["internet_service_columns"]:
            frame[field] = "No internet service"
        frame["PhoneService"], frame["MultipleLines"] = "No", "No phone service"
        validate_frame(frame, self.config)
        changes = {"OnlineSecurity": "No", "MultipleLines": "No", "Contract": "unknown", "gender": None}
        for column, value in changes.items():
            with self.subTest(column=column), self.assertRaises(ValueError):
                validate_frame(replace_value(frame, column, value), self.config)


if __name__ == "__main__":
    unittest.main()
