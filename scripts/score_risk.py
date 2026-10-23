"""Attach the fixed W7 risk card to a probability CSV, without model fitting.

Use predict.py first for cleaned predictor inputs. This command
accepts its churn_probability column (or an explicitly named probability column).
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import sys
import tempfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.models.w7.risk import load_config, score_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--probability-column", default="churn_probability")
    parser.add_argument("--batch-size", type=int, default=4096)
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size must be positive")
    source, destination = args.input.resolve(), args.output.resolve()
    if source == destination or destination.exists():
        raise FileExistsError("Choose a new output path different from the input")
    with source.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    if not header or len(header) != len(set(header)) or args.probability_column not in header:
        raise ValueError("CSV needs unique columns and the named model-probability column")
    config = load_config()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".csv", delete=False) as handle:
        temporary = Path(handle.name)
    count = 0
    try:
        for chunk in pd.read_csv(source, encoding="utf-8-sig", chunksize=args.batch_size,
                                 float_precision="round_trip", dtype={"customerID": str}):
            scored = score_frame(chunk, p_col=args.probability_column, config=config)
            scored["review_action"] = scored.risk.map(config.actions)
            scored.to_csv(temporary, mode="a", header=count == 0, index=False,
                          encoding="utf-8", float_format="%.17g")
            count += len(scored)
        if not count:
            raise ValueError("No probability rows to score")
        if destination.exists():
            raise FileExistsError("Output appeared during scoring")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Scored {count} rows: low=[0,.10), medium=[.10,.30), high=[.30,1]; output={destination}")


if __name__ == "__main__":
    main()
