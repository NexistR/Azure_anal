"""Load a frozen UBJ + preprocessing bundle and predict in bounded chunks.

No fitting, threshold selection, tree editing or quantization takes place here.
The bundle contains XGBoost's own model serialization and fitted preprocessing
statistics, with member hashes to detect incomplete/corrupt exports.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import xgboost as xgb

from .preprocessing import FrozenFeatureEncoder

FORMAT = "telco-frozen-runtime-v1"


def _positive_int(name, value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


class FrozenChurnRuntime:
    """Reuse one loaded instance; all per-request arrays stay local.

    predict_score/proba still allocate their final O(n) output. For a bounded
    whole-file working set, stream input chunks (see predict_week7_runtime.py).
    """

    def __init__(self, metadata, booster, *, n_threads=2, batch_size=4096):
        self.n_threads = _positive_int("n_threads", n_threads)
        self.batch_size = _positive_int("batch_size", batch_size)
        self.metadata = metadata
        self.encoder = FrozenFeatureEncoder(metadata["preprocessing"])
        self.booster = booster
        self._threshold = float(metadata["threshold"])
        self._iteration_range = tuple(metadata["iteration_range"])

    @property
    def threshold(self):
        return self._threshold

    @classmethod
    def load(cls, path: str | Path, *, n_threads=2, batch_size=4096):
        _positive_int("n_threads", n_threads)
        _positive_int("batch_size", batch_size)
        try:
            with zipfile.ZipFile(path) as bundle:
                names = bundle.namelist()
                if sorted(names) != ["manifest.json", "metadata.json", "model.ubj"]:
                    raise ValueError("Unexpected runtime bundle members")
                manifest = json.loads(bundle.read("manifest.json"))
                if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
                    raise ValueError("Unsupported runtime bundle format")
                if not isinstance(manifest.get("sha256"), dict):
                    raise ValueError("Invalid runtime bundle hash manifest")
                payload = {name: bundle.read(name) for name in ("metadata.json", "model.ubj")}
                for name, value in payload.items():
                    if hashlib.sha256(value).hexdigest() != manifest["sha256"][name]:
                        raise ValueError(f"Runtime bundle hash mismatch: {name}")
                metadata = json.loads(payload["metadata.json"])
                if (not isinstance(metadata, dict) or metadata["format"] != FORMAT
                        or metadata["threshold"] != 0.30 or metadata["classes"] != [0, 1]):
                    raise ValueError("Unexpected frozen runtime contract")
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
            raise ValueError("Invalid runtime bundle") from error
        booster = xgb.Booster()
        booster.load_model(bytearray(payload["model.ubj"]))
        booster.set_param({"nthread": n_threads})
        if booster.num_features() != len(metadata["preprocessing"]["output_columns"]):
            raise ValueError("Booster and preprocessing widths differ")
        return cls(metadata, booster, n_threads=n_threads, batch_size=batch_size)

    def predict_score(self, frame: pd.DataFrame) -> np.ndarray:
        """Positive-class probabilities in exactly the caller's row order."""
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("Prediction requires a nonempty feature DataFrame")
        scores = np.empty(len(frame), dtype=np.float32)
        for start in range(0, len(frame), self.batch_size):
            stop = min(start + self.batch_size, len(frame))
            matrix = self.encoder.transform(frame.iloc[start:stop])
            scores[start:stop] = self.booster.inplace_predict(
                matrix, iteration_range=self._iteration_range, validate_features=True,
            )
        return scores

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        scores = self.predict_score(frame)
        result = np.empty((len(scores), 2), dtype=np.float32)
        result[:, 0] = 1.0 - scores
        result[:, 1] = scores
        return result

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return (self.predict_score(frame) >= self.threshold).astype(np.int64)
