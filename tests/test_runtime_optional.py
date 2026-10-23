"""Opt-in inference integration, using only handwritten synthetic inputs.

Set CHURN_RUNTIME_MODEL to a trusted frozen ZIP to enable these tests. Merely
having a local ignored model file does not opt in. No training is performed.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import numpy as np
import pandas as pd

from src.models.w7.risk import score_frame
from tests._fixtures import ROOT, raw_frame, replace_value


@unittest.skipUnless(os.environ.get("CHURN_RUNTIME_MODEL"), "Set CHURN_RUNTIME_MODEL to enable frozen-model integration")
class OptionalRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.models.w7.runtime import FrozenChurnRuntime

        cls.runtime_class = FrozenChurnRuntime
        cls.model = Path(os.environ["CHURN_RUNTIME_MODEL"]).expanduser().resolve()
        cls.initial_hash = hashlib.sha256(cls.model.read_bytes()).hexdigest()
        cls.runtime = FrozenChurnRuntime.load(cls.model, n_threads=2, batch_size=4096)

    @classmethod
    def tearDownClass(cls):
        if hashlib.sha256(cls.model.read_bytes()).hexdigest() != cls.initial_hash:
            raise AssertionError("Inference changed the frozen model file")

    def run_cli(self, script, *args, cwd=None):
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / script), *map(str, args)],
                              cwd=cwd or ROOT, env=environment, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=90)

    def test_configuration_and_corrupt_artifact(self):
        self.assertEqual(self.runtime.threshold, .30)
        with self.assertRaises(AttributeError):
            self.runtime.threshold = .5
        for key in ("batch_size", "n_threads"):
            for bad in (True, 0, -1, 1.5):
                with self.subTest(key=key, value=bad), self.assertRaises(ValueError):
                    self.runtime_class.load(self.model, **{key: bad})
        with tempfile.TemporaryDirectory(prefix="runtime_zip_", dir=ROOT / "tests") as directory:
            path = Path(directory) / "corrupt.zip"
            path.write_bytes(b"not a zip archive")
            with self.assertRaises(ValueError):
                self.runtime_class.load(path)
            with zipfile.ZipFile(self.model) as original, zipfile.ZipFile(path, "w") as altered:
                for name in original.namelist():
                    content = original.read(name)
                    altered.writestr(name, content + b" " if name == "metadata.json" else content)
            with self.assertRaises(ValueError):
                self.runtime_class.load(path)

    def test_order_chunks_and_nonmutation(self):
        frame = raw_frame(65)
        before = frame.copy(deep=True)
        expected = self.runtime.predict_proba(frame)
        self.assertEqual(expected.shape, (65, 2))
        self.assertEqual(expected.dtype, np.dtype("float32"))
        self.assertTrue(np.isfinite(expected).all())
        np.testing.assert_allclose(expected.sum(axis=1), 1, rtol=0, atol=1e-7)
        np.testing.assert_array_equal(self.runtime.predict(frame), (expected[:, 1] >= .3).astype(np.int64))
        for size in (1, 32):
            other = self.runtime_class.load(self.model, batch_size=size, n_threads=2)
            np.testing.assert_array_equal(other.predict_proba(frame), expected)
        np.testing.assert_array_equal(self.runtime.predict_proba(frame.iloc[::-1, ::-1]), expected[::-1])
        pd.testing.assert_frame_equal(frame, before)

    def test_real_missing_semantics_extremes_and_late_invalid_row(self):
        frame = raw_frame(1)
        frame.loc[0, ["TotalCharges", "total_charges_missing", "tenure", "tenure_zero"]] = [np.nan, 1, 0, 1]
        self.assertTrue(np.isfinite(self.runtime.predict_proba(frame)).all())
        extreme = replace_value(raw_frame(1), "TotalCharges", 1e308)
        with np.errstate(over="ignore", invalid="ignore"):
            self.assertTrue(np.isfinite(self.runtime.predict_proba(extreme)).all())
        bad = replace_value(raw_frame(4097), "Contract", "unknown", row=4096)
        with self.assertRaises(ValueError):
            self.runtime.predict_proba(bad)

    def test_prediction_and_scoring_cli_roundtrip_from_different_cwd(self):
        with tempfile.TemporaryDirectory(prefix="cli_roundtrip_", dir=ROOT / "tests") as directory:
            folder = Path(directory)
            source, output, scored = [folder / name for name in ("features.csv", "predictions.csv", "scores.csv")]
            frame = raw_frame(65)
            ids = [f"synthetic-{i:04}" for i in range(len(frame))]
            frame.assign(customerID=ids).to_csv(source, index=False)
            call = self.run_cli("predict.py", "--input", source, "--output", output,
                                "--model", self.model, "--batch-size", 32, cwd=folder)
            self.assertEqual(call.returncode, 0, call.stdout + call.stderr)
            actual = pd.read_csv(output, float_precision="round_trip", dtype={"customerID": str})
            self.assertEqual(actual.customerID.tolist(), ids)
            self.assertEqual(actual.row_index.tolist(), list(range(65)))
            np.testing.assert_array_equal(actual.churn_probability.to_numpy(dtype=np.float32), self.runtime.predict_score(frame))
            call = self.run_cli("score_risk.py", "--input", output, "--output", scored, "--batch-size", 2, cwd=folder)
            self.assertEqual(call.returncode, 0, call.stdout + call.stderr)
            actual_scores = pd.read_csv(scored, float_precision="round_trip")
            expected = score_frame(actual, p_col="churn_probability")
            self.assertEqual(actual_scores.risk.tolist(), expected.risk.tolist())
            np.testing.assert_array_equal(actual_scores.score, expected.score)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["features.csv", "predictions.csv", "scores.csv"])

    def test_prediction_cli_failure_is_atomic_and_rejects_headers(self):
        with tempfile.TemporaryDirectory(prefix="cli_failure_", dir=ROOT / "tests") as directory:
            folder = Path(directory)
            source, output = folder / "features.csv", folder / "out.csv"
            bad = replace_value(raw_frame(65), "Contract", "unknown", row=64)
            bad.to_csv(source, index=False)
            call = self.run_cli("predict.py", "--input", source, "--output", output, "--model", self.model, "--batch-size", 32)
            self.assertNotEqual(call.returncode, 0)
            self.assertEqual([p.name for p in folder.iterdir()], [source.name])
            for kind in ("label", "duplicate"):
                raw_frame(1).assign(Churn="Yes").to_csv(source, index=False)
                if kind == "duplicate":
                    source.write_text("tenure,tenure\n1,1\n", encoding="utf-8")
                with self.subTest(kind=kind):
                    call = self.run_cli("predict.py", "--input", source, "--output", output, "--model", self.model)
                    self.assertNotEqual(call.returncode, 0)
                    self.assertFalse(output.exists())
            raw_frame(1).to_csv(source, index=False)
            output.write_bytes(b"preserve this existing output")
            call = self.run_cli("predict.py", "--input", source, "--output", output, "--model", self.model)
            self.assertNotEqual(call.returncode, 0)
            self.assertEqual(output.read_bytes(), b"preserve this existing output")

    def test_csv_exact_integer_tokens_before_float_inference(self):
        with tempfile.TemporaryDirectory(prefix="cli_integer_", dir=ROOT / "tests") as directory:
            folder = Path(directory)
            source = folder / "features.csv"
            for token, valid in (("9007199254740993", True), ("9007199254740992.5", False)):
                frame = raw_frame(2)
                frame["tenure"] = [token, "1.0"]
                frame.to_csv(source, index=False)
                probabilities = []
                for size in (1, 2):
                    output = folder / f"output-{size}.csv"
                    with self.subTest(token=token, batch_size=size):
                        call = self.run_cli("predict.py", "--input", source, "--output", output,
                                            "--model", self.model, "--batch-size", size)
                        if valid:
                            self.assertEqual(call.returncode, 0, call.stdout + call.stderr)
                            probabilities.append(pd.read_csv(output).churn_probability.to_numpy())
                            output.unlink()
                        else:
                            self.assertNotEqual(call.returncode, 0)
                            self.assertFalse(output.exists())
                if valid:
                    np.testing.assert_array_equal(probabilities[0], probabilities[1])
                self.assertEqual([p.name for p in folder.iterdir()], [source.name])

    def test_scoring_cli_probability_endpoints_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix="cli_score_", dir=ROOT / "tests") as directory:
            folder = Path(directory)
            source, output = folder / "probabilities.csv", folder / "scores.csv"
            p = np.array([0, np.nextafter(.1, 0), .1, np.nextafter(.3, 0), .3, 1.])
            pd.DataFrame({"churn_probability": p}).to_csv(source, index=False, float_format="%.17g")
            call = self.run_cli("score_risk.py", "--input", source, "--output", output, "--batch-size", 2)
            self.assertEqual(call.returncode, 0, call.stdout + call.stderr)
            self.assertEqual(pd.read_csv(output).risk.tolist(), ["low", "low", "medium", "medium", "high", "high"])
            before = output.read_bytes()
            call = self.run_cli("score_risk.py", "--input", source, "--output", output)
            self.assertNotEqual(call.returncode, 0)
            self.assertEqual(output.read_bytes(), before)
            output.unlink()
            pd.DataFrame({"churn_probability": [0., .1, .3, 1.1]}).to_csv(source, index=False)
            call = self.run_cli("score_risk.py", "--input", source, "--output", output, "--batch-size", 2)
            self.assertNotEqual(call.returncode, 0)
            self.assertEqual([p.name for p in folder.iterdir()], [source.name])


if __name__ == "__main__":
    unittest.main()
