"""Handwritten synthetic records, never sampled from customer data."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def cleaning_config():
    return json.loads((ROOT / "configs/w3_cleaning.json").read_text(encoding="utf-8"))


def raw_frame(rows=3):
    base = {
        "tenure": 12, "MonthlyCharges": 60.0, "TotalCharges": 720.0,
        "gender": "Female", "SeniorCitizen": 0, "Partner": "No", "Dependents": "No",
        "PhoneService": "Yes", "MultipleLines": "No", "InternetService": "DSL",
        "OnlineSecurity": "Yes", "OnlineBackup": "No", "DeviceProtection": "No",
        "TechSupport": "Yes", "StreamingTV": "No", "StreamingMovies": "No",
        "Contract": "Month-to-month", "PaperlessBilling": "Yes",
        "PaymentMethod": "Electronic check", "total_charges_missing": 0,
        "tenure_zero": 0, "internet_applicable": 1,
    }
    frame = pd.DataFrame([base.copy() for _ in range(rows)])
    if rows:
        frame["tenure"] = np.arange(rows, dtype=np.int64) % 60 + 1
        frame["MonthlyCharges"] = 35.0 + np.arange(rows) % 20
        frame["TotalCharges"] = frame.tenure * frame.MonthlyCharges
    return frame


def replace_value(frame, column, value, row=0):
    """Preserve invalid numeric tokens without pandas coercing them first."""
    result = frame.copy(deep=True)
    result[column] = result[column].astype(object)
    result.iat[row, result.columns.get_loc(column)] = value
    return result


def value_frame():
    return pd.DataFrame({
        "customerID": ["synthetic-d", "synthetic-c", "synthetic-b", "synthetic-a"],
        "MonthlyCharges": [50.0, 50.0, 49.0, 49.0],
        "p": [.30, np.nextafter(.30, 0), .30, np.nextafter(.30, 0)],
        "y": [0, 1, 1, 0], "tenure": [1, 2, 3, 4], "split": ["validation"] * 4,
    }, index=[8, 5, 3, 1])
