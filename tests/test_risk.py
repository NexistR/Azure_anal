"""Probability scoring is independent of customer labels and display rounding."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.models.w7.risk import load_config, score_frame, summarize_scores, validate_probabilities, wilson_interval
from tests._fixtures import ROOT


class RiskTests(unittest.TestCase):
    def test_boundaries_and_display_rounding(self):
        p = np.array([0, np.nextafter(.1, 0), .1, np.nextafter(.1, 1),
                      np.nextafter(.3, 0), .3, np.nextafter(.3, 1), 1.])
        frame = pd.DataFrame({"p": p}, index=list(reversed(range(len(p)))))
        result = score_frame(frame)
        self.assertEqual(result.risk.tolist(), ["low", "low", "medium", "medium", "medium", "high", "high", "high"])
        self.assertEqual(result.index.tolist(), frame.index.tolist())
        np.testing.assert_array_equal(result.prediction, p >= .3)
        np.testing.assert_array_equal(result.score, p * 100)
        self.assertEqual(round(result.score.iloc[1], 1), 10.)
        self.assertEqual(round(result.score.iloc[4], 1), 30.)
        self.assertEqual(result.risk.iloc[[1, 4]].tolist(), ["low", "medium"])

    def test_invalid_and_empty_probabilities(self):
        self.assertEqual(validate_probabilities([]).shape, (0,))
        self.assertTrue(score_frame(pd.DataFrame({"p": pd.Series(dtype=float)})).empty)
        for bad in (None, .2, [True, .2], [".2"], [1 + 0j], [[.2]], [np.nan], [np.inf],
                    [-np.finfo(float).eps], [np.nextafter(1., np.inf)], np.array([.2], dtype=object)):
            with self.subTest(value=repr(bad)), self.assertRaises(ValueError):
                validate_probabilities(bad)
        for bad in (pd.DataFrame({"other": [.2]}), pd.DataFrame([[.2, .3]], columns=["p", "p"])):
            with self.assertRaises(ValueError):
                score_frame(bad)

    def test_copies_inputs_and_ignores_ids_and_labels(self):
        frame = pd.DataFrame({"customerID": ["synthetic-a", "synthetic-b"], "p": [.12, .8], "y": [0, 1]})
        before = frame.copy(deep=True)
        result = score_frame(frame)
        changed = score_frame(frame.assign(y=1-frame.y, customerID=["synthetic-z", "synthetic-y"]))
        pd.testing.assert_frame_equal(result[["score", "risk", "prediction"]], changed[["score", "risk", "prediction"]])
        pd.testing.assert_frame_equal(frame, before)

    def test_configuration_rejects_policy_changes(self):
        config = json.loads((ROOT / "configs/w7_risk.json").read_text(encoding="utf-8"))
        self.assertEqual(load_config().classification_threshold, .30)
        with tempfile.TemporaryDirectory(prefix="risk_config_", dir=ROOT / "tests") as directory:
            path = Path(directory) / "config.json"
            for key, bad in (("high_lower_inclusive", .31), ("score_multiplier", True), ("actions", {})):
                changed = {**config, key: bad}
                path.write_text(json.dumps(changed), encoding="utf-8")
                with self.subTest(field=key), self.assertRaises(ValueError):
                    load_config(path)

    def test_descriptive_diagnostics_and_empty_bins(self):
        frame = pd.DataFrame({"p": [0., .05, .10, .20, .30, .90, 1.], "y": [0, 0, 1, 0, 1, 1, 1]})
        result = summarize_scores(frame, "validation")
        self.assertEqual([(g["n"], g["positive"]) for g in result["risk_groups"]], [(2, 0), (2, 1), (3, 3)])
        self.assertAlmostEqual(result["brier_score"], 1.3525/7, places=14)
        self.assertAlmostEqual(result["ece_10_equal_width"], 1.95/7, places=14)
        self.assertIsNone(result["calibration_bins"][4]["observed_rate"])
        self.assertEqual(wilson_interval(0, 0), (None, None))
        np.testing.assert_allclose(wilson_interval(0, 1), [0, .7934506856227626], rtol=0, atol=1e-14)
        with self.assertRaises(ValueError):
            summarize_scores(frame, "test")


if __name__ == "__main__":
    unittest.main()
