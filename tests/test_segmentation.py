"""Value rules and frozen-core assignment, without fitting any estimator."""
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np
import pandas as pd

from src.segmentation.w8 import (add_value_risk, assign_dbscan, cluster_metrics,
                                 monthly_concentration, static_features, summarize_quadrants)
from tests._fixtures import raw_frame, replace_value, value_frame


class SegmentationRuleTests(unittest.TestCase):
    def test_static_features_have_known_meaning_and_no_labels(self):
        frame = raw_frame(2)
        frame["PaymentMethod"] = "Bank transfer (automatic)"
        before = frame.copy(deep=True)
        result = static_features(frame)
        self.assertEqual(result.shape, (2, 9))
        np.testing.assert_array_equal(result.internet_addon_count, [2, 2])
        np.testing.assert_array_equal(result.automatic_payment, [1, 1])
        np.testing.assert_allclose(result.tenure_log1p, np.log1p([1, 2]), rtol=0, atol=0)
        self.assertFalse({"p", "y", "customerID", "TotalCharges"} & set(result))
        with self.assertRaises(ValueError):
            static_features(frame.assign(y=0))
        pd.testing.assert_frame_equal(frame, before)

    def test_value_and_risk_endpoints_label_invariance_and_order(self):
        frame = value_frame()
        before = frame.copy(deep=True)
        result = add_value_risk(frame, 50.)
        self.assertEqual(result.risk_value_quadrant.tolist(), ["HV_HR", "HV_LR", "LV_HR", "LV_LR"])
        self.assertEqual(result.index.tolist(), frame.index.tolist())
        np.testing.assert_array_equal(result.priority_weight, frame.p * frame.MonthlyCharges)
        flipped = add_value_risk(frame.assign(y=1-frame.y), 50.)
        columns = ["high_value", "high_risk", "risk_value_quadrant", "priority_weight", "priority_rank"]
        pd.testing.assert_frame_equal(result[columns], flipped[columns])
        pd.testing.assert_frame_equal(frame, before)
        ties = frame.assign(p=.5, MonthlyCharges=50.)
        self.assertEqual(add_value_risk(ties, 50.).priority_rank.tolist(), [4, 3, 2, 1])

    def test_reject_invalid_fees_probabilities_ids_and_thresholds(self):
        frame = value_frame()
        for threshold in (True, -1., float("nan"), float("inf"), "50", 50+0j):
            with self.subTest(threshold=repr(threshold)), self.assertRaises(ValueError):
                add_value_risk(frame, threshold)
        for field, values in {"MonthlyCharges": [True, "50", 50+0j, -1., np.nan, np.inf],
                              "p": [True, "0.3", -1., 1.1, np.nan],
                              "customerID": ["", "  ", None, "synthetic-c"]}.items():
            for value in values:
                with self.subTest(field=field, value=repr(value)), self.assertRaises(ValueError):
                    add_value_risk(replace_value(frame, field, value), 50.)
        with self.assertRaises(ValueError):
            add_value_risk(frame.set_axis([0, 0, 1, 2]), 50.)
        with self.assertRaises(ValueError):
            add_value_risk(frame, 50., risk_threshold=.31)

    def test_quadrant_totals_use_distinct_denominators(self):
        frame = add_value_risk(value_frame(), 50.)
        summary = summarize_quadrants(frame)
        self.assertEqual(summary["count"].sum(), 4)
        self.assertEqual(summary.observed_churn_count.sum(), 2)
        self.assertAlmostEqual(summary.monthly_charge_sum.sum(), 198.)
        self.assertAlmostEqual(summary.customer_share.sum(), 1.)
        self.assertAlmostEqual(summary.monthly_charge_share.sum(), 1.)
        high = summary.loc[summary.quadrant.eq("HV_HR")].iloc[0]
        self.assertEqual(high.customer_share, .25)
        self.assertAlmostEqual(high.monthly_charge_share, 50/198)

    def test_frozen_core_assignment_ties_ambiguity_and_noise(self):
        # Deliberately supply equal-distance neighbors in reverse original-row
        # order. This tests assignment policy, not sklearn's neighbor algorithm.
        index = mock.Mock()
        index.kneighbors.return_value = (np.array([[1.], [.2], [2.]]), np.array([[0], [2], [2]]))
        index.radius_neighbors.return_value = (
            [np.array([1., 1.]), np.array([.2]), np.array([])],
            [np.array([0, 1]), np.array([2]), np.array([], dtype=int)],
        )
        bundle = {"core_neighbor_index": index, "dbscan": SimpleNamespace(eps=1.),
                  "core_train_indices": np.array([9, 2, 7]), "core_train_labels": np.array([0, 1, 1])}
        labels, ambiguous, distance, core = assign_dbscan(np.zeros((3, 2)), bundle)
        np.testing.assert_array_equal(labels, [1, 1, -1])
        np.testing.assert_array_equal(ambiguous, [True, False, False])
        np.testing.assert_array_equal(core, [2, 7, -1])
        np.testing.assert_array_equal(distance, [1., .2, 2.])
        self.assertEqual(index.radius_neighbors.call_args.kwargs,
                         {"radius": 1., "return_distance": True, "sort_results": True})

    def test_no_core_and_conditional_silhouette(self):
        labels, ambiguous, distance, core = assign_dbscan(np.zeros((2, 3)), {"core_neighbor_index": None})
        np.testing.assert_array_equal(labels, [-1, -1])
        np.testing.assert_array_equal(core, [-1, -1])
        self.assertFalse(ambiguous.any())
        self.assertTrue(np.isnan(distance).all())
        one_cluster = cluster_metrics(np.array([[0.], [1.], [9.]]), np.array([0, 0, -1]), np.arange(3))
        self.assertEqual(one_cluster["silhouette_sample_n"], 2)
        self.assertEqual(one_cluster["noise_count"], 1)
        self.assertIsNone(one_cluster["silhouette"])
        self.assertIsNone(one_cluster["dbi"])

    def test_concentration_keeps_entire_equal_fee_group(self):
        frame = pd.DataFrame({"MonthlyCharges": [40., 30., 30., 1.], "split": ["validation"] * 4})
        curve, summary = monthly_concentration(frame)
        self.assertEqual(curve.group_customers.tolist(), [1, 2, 1])
        self.assertEqual(summary[0]["cumulative_customers"], 3)
        self.assertAlmostEqual(summary[0]["cumulative_monthly_charge_share"], 100/101)
        self.assertLess(summary[0]["previous_cumulative_share"], .60)


if __name__ == "__main__":
    unittest.main()
