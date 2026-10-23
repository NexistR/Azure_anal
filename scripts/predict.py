"""Stream a feature-only CSV through the frozen, bounded-memory runtime.

Accepted input: the 22 cleaned predictor columns, optionally customerID.
Labels are forbidden. Output is committed only when every chunk validates.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=ROOT / "models/w7/churn_runtime.zip")
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    import pandas as pd
    from src.models.w7.runtime import FrozenChurnRuntime
    source, destination = args.input.resolve(), args.output.resolve()
    if source == destination or destination == args.model.resolve():
        raise ValueError("Output must differ from the input/model paths")
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    runtime = FrozenChurnRuntime.load(args.model, n_threads=args.threads, batch_size=args.batch_size)
    with source.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    if len(header) != len(set(header)):
        raise ValueError("Input CSV has duplicate column names")
    expected = set(runtime.metadata["preprocessing"]["input_columns"])
    if set(header) not in (expected, expected | {"customerID"}):
        raise ValueError("CSV must contain exactly the 22 predictors, optionally customerID; labels are forbidden")
    has_ids = "customerID" in header
    # Preserve exact integer tokens before pandas can promote a mixed numeric
    # column to float64 (e.g. 9007199254740992.5 alongside 1.0). The inherited
    # Decimal-aware contract, not CSV type inference, decides integrality.
    csv_dtypes = {name: object for name, rule in
                  runtime.metadata["preprocessing"]["cleaning_config"]["numeric_rules"].items()
                  if rule["integer"]}
    if has_ids:
        csv_dtypes["customerID"] = str
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".csv", delete=False) as handle:
        temporary = Path(handle.name)
    offset = 0
    try:
        reader = pd.read_csv(source, chunksize=args.batch_size, dtype=csv_dtypes,
                             encoding="utf-8-sig")
        for chunk in reader:
            features = chunk.drop(columns="customerID") if has_ids else chunk
            scores = runtime.predict_score(features)
            output = pd.DataFrame({"row_index": range(offset, offset + len(chunk)),
                                   "churn_probability": scores,
                                   "churn_prediction": (scores >= runtime.threshold).astype(int)})
            if has_ids:
                output.insert(1, "customerID", chunk["customerID"].to_numpy())
            output.to_csv(temporary, mode="a", header=offset == 0, index=False, encoding="utf-8")
            offset += len(chunk)
        if offset == 0:
            raise ValueError("Input CSV must have at least one row")
        if destination.exists():
            raise FileExistsError(f"Output appeared during prediction: {destination}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Predicted {offset} rows; threshold={runtime.threshold:.2f}; output={destination}")


if __name__ == "__main__":
    main()
