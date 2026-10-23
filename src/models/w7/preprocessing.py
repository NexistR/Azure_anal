"""Frozen W4 preprocessing expressed as NumPy arrays, without fitting.

Export accepts the fitted W4 feature pipeline (or its enclosing classifier).
Inference keeps the original 64 logical formulas, including unused fields and
their overflow checks, and returns the original 111 positions as float32.
"""
from __future__ import annotations

import copy
import numpy as np

from .contract import validate_frame


def _plain(value):
    if isinstance(value, np.ndarray):
        return [_plain(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return copy.deepcopy(value)


def export_preprocessor(preprocessor) -> dict:
    """Export only already-fitted parameters; never call fit or transform."""
    if "features" in preprocessor.named_steps:
        preprocessor = preprocessor.named_steps["features"]
    if list(preprocessor.named_steps) != ["builder", "columns", "finite"]:
        raise ValueError("Expected the frozen W4 builder/columns/finite pipeline")
    builder = preprocessor.named_steps["builder"]
    columns = preprocessor.named_steps["columns"]
    groups = {name: list(names) for name, _, names in columns.transformers_ if name != "remainder"}
    numeric = columns.named_transformers_["numeric"]
    imputer, scaler = numeric.named_steps["imputer"], numeric.named_steps["scaler"]
    categorical = columns.named_transformers_["categorical"]
    binary = columns.named_transformers_["binary"]
    if (imputer.strategy != "median" or not imputer.keep_empty_features
            or not scaler.with_mean or not scaler.with_std
            or categorical.handle_unknown != "error" or categorical.drop is not None
            or categorical.sparse_output or binary.strategy != "constant"
            or not binary.keep_empty_features or columns.sparse_output_):
        raise ValueError("Unsupported frozen preprocessing configuration")
    metadata = {
        "schema_version": "w7-frozen-w4-numpy-v1",
        "cleaning_config": _plain(builder.contract_.config_),
        "feature_config": _plain(builder.config_),
        "input_columns": _plain(builder.feature_names_in_),
        "output_columns": _plain(preprocessor.get_feature_names_out()),
        "logical_columns": builder.registry_.feature_name.tolist(),
        "logical_numeric_columns": builder.registry_.loc[builder.registry_.kind.ne("categorical"), "feature_name"].tolist(),
        "numeric": {"names": groups["numeric"], "medians": _plain(imputer.statistics_),
                    "mean": _plain(scaler.mean_), "scale": _plain(scaler.scale_)},
        "categorical": [{"name": name, "categories": _plain(categories)}
                        for name, categories in zip(groups["categorical"], categorical.categories_)],
        "binary": {"names": groups["binary"], "fill": _plain(binary.statistics_)},
        "output_dtype": "float32",
        "numeric_execution": "float64 impute, subtract frozen mean, divide frozen scale, cast float32",
    }
    if len(metadata["input_columns"]) != 22 or len(metadata["logical_columns"]) != 64 or len(metadata["output_columns"]) != 111:
        raise ValueError("Frozen champion dimensions must be 22 -> 64 -> 111")
    return metadata


def _safe_divide(numerator, denominator):
    """Mirror the original masked float64 division, including NA semantics."""
    numerator = np.asarray(numerator, dtype=np.float64)
    denominator = np.asarray(denominator, dtype=np.float64)
    valid = ~np.isnan(numerator) & ~np.isnan(denominator) & (denominator > 0)
    result = np.full(numerator.shape, np.nan, dtype=np.float64)
    np.divide(numerator, denominator, out=result, where=valid)
    return result


class FrozenFeatureEncoder:
    def __init__(self, metadata: dict):
        self.metadata = copy.deepcopy(metadata)
        if self.metadata.get("schema_version") != "w7-frozen-w4-numpy-v1":
            raise ValueError("Unknown frozen preprocessing metadata version")
        numeric = self.metadata["numeric"]
        self._medians = np.asarray(numeric["medians"], dtype=np.float64)
        self._mean = np.asarray(numeric["mean"], dtype=np.float64)
        self._scale = np.asarray(numeric["scale"], dtype=np.float64)
        self._binary_fill = np.asarray(self.metadata["binary"]["fill"], dtype=np.float64)
        if (any(array.shape != (len(numeric["names"]),) for array in (self._medians, self._mean, self._scale))
                or self._binary_fill.shape != (len(self.metadata["binary"]["names"]),)
                or not all(np.isfinite(array).all() for array in (self._medians, self._mean, self._scale, self._binary_fill))
                or (self._scale <= 0).any()):
            raise ValueError("Invalid frozen imputation/scaling metadata")
        expected_width = len(numeric["names"]) + sum(len(x["categories"]) for x in self.metadata["categorical"]) + len(self._binary_fill)
        if expected_width != 111 or len(self.metadata["output_columns"]) != expected_width:
            raise ValueError("Frozen encoded width differs from 111")

    def _derive(self, frame):
        x = {name: frame[name].to_numpy(copy=False) for name in self.metadata["input_columns"]}
        cfg = self.metadata["feature_config"]
        tenure = x["tenure"]  # Retain integer precision for predicates and bins.
        monthly, total = x["MonthlyCharges"], x["TotalCharges"]
        internet, phone = x["InternetService"] != "No", x["PhoneService"] == "Yes"
        fiber = x["InternetService"] == "Fiber optic"
        partner, dependents = x["Partner"] == "Yes", x["Dependents"] == "Yes"
        household = partner | dependents
        senior = x["SeniorCitizen"] == 1
        month_contract = x["Contract"] == "Month-to-month"
        automatic = np.isin(x["PaymentMethod"], ["Bank transfer (automatic)", "Credit card (automatic)"])
        paperless = x["PaperlessBilling"] == "Yes"

        def internet_count(names):
            counts = np.sum(np.column_stack([x[name] == "Yes" for name in names]), axis=1, dtype=np.int64).astype(np.float64)
            counts[~internet] = np.nan
            return counts

        def internet_binary(values):
            result = values.astype(np.float64)
            result[~internet] = np.nan
            return result

        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            x["tenure_log1p"] = np.log1p(tenure.astype(np.float64))
            x["monthly_charges_log1p"] = np.log1p(monthly)
            x["total_charges_log1p"] = np.log1p(total)
            # pd.cut(..., right=True): an exact edge belongs to the lower bin.
            for name, values, prefix in [("tenure_band", tenure, "tenure"), ("monthly_charge_band", monthly, "monthly_charge")]:
                edges = np.asarray(cfg[prefix + "_band_edges"])
                positions = np.searchsorted(edges, values, side="left")
                x[name] = np.asarray(cfg[prefix + "_band_labels"], dtype=object)[positions]
            x["historical_monthly_average"] = _safe_divide(total, tenure)
            x["current_to_historical_charge_ratio"] = _safe_divide(monthly, x["historical_monthly_average"])
            x["monthly_charge_gap"] = monthly - x["historical_monthly_average"]
            x["constant_rate_total_proxy"] = np.where(tenure > 0, monthly * tenure.astype(np.float64), np.nan)
            x["cumulative_charge_gap"] = total - x["constant_rate_total_proxy"]
            x["charge_history_available"] = ((tenure > 0) & ~np.isnan(total)).astype(np.int64)
            x["historical_charge_positive"] = ((tenure > 0) & (total > 0)).astype(np.int64)
            x["household_profile"] = np.select([partner & dependents, partner, dependents], ["both", "partner_only", "dependents_only"], default="neither")
            x["household_support_count"] = partner.astype(np.int64) + dependents.astype(np.int64)
            x["senior_without_household_support"] = (senior & ~household).astype(np.int64)
            x["phone_applicable"] = phone.astype(np.int64)
            x["internet_addon_count"] = internet_count(["OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies"])
            x["protection_addon_count"] = internet_count(["OnlineSecurity", "OnlineBackup", "DeviceProtection"])
            x["support_security_count"] = internet_count(["OnlineSecurity", "TechSupport"])
            x["streaming_addon_count"] = internet_count(["StreamingTV", "StreamingMovies"])
            x["internet_without_addons"] = internet_binary(x["internet_addon_count"] == 0)
            streaming = x["streaming_addon_count"] > 0
            x["unprotected_streaming"] = internet_binary(streaming & (x["OnlineSecurity"] == "No") & (x["DeviceProtection"] == "No"))
            x["unsupported_fiber"] = internet_binary(fiber & (x["TechSupport"] == "No"))
            protected = (x["protection_addon_count"] > 0) | (x["support_security_count"] > 0)
            x["internet_bundle_profile"] = np.select([~internet, protected & streaming, protected, streaming], ["not_applicable", "mixed", "protection_support", "entertainment"], default="basic")
            x["core_service_count"] = phone.astype(np.int64) + internet.astype(np.int64)
            x["active_service_count"] = x["core_service_count"] + (x["MultipleLines"] == "Yes").astype(np.int64) + np.nan_to_num(x["internet_addon_count"], nan=0.)
            x["charge_per_active_service"] = _safe_divide(monthly, x["active_service_count"])
            x["contract_months"] = np.asarray([cfg["contract_months"][value] for value in x["Contract"]], dtype=np.int64)
            x["tenure_contract_ratio"] = _safe_divide(tenure, x["contract_months"])
            x["nominal_contract_charge_proxy"] = monthly * x["contract_months"]
            x["tenure_contract_phase"] = np.select([tenure == 0, tenure <= x["contract_months"]], ["zero", "within_nominal"], default="beyond_nominal")
            x["automatic_payment"] = automatic.astype(np.int64)
            x["billing_profile"] = np.select([paperless & automatic, paperless, automatic], ["paperless_auto", "paperless_manual", "paper_auto"], default="paper_manual")
            x["manual_paperless"] = (paperless & ~automatic).astype(np.int64)
            x["month_to_month_manual_payment"] = (month_contract & ~automatic).astype(np.int64)
            x["fiber_month_to_month"] = internet_binary(fiber & month_contract)
            x["new_month_to_month"] = ((tenure <= cfg["new_customer_months"]) & month_contract).astype(np.int64)
            x["senior_manual_payment"] = (senior & ~automatic).astype(np.int64)
            x["household_long_contract"] = (household & ~month_contract).astype(np.int64)
            x["fiber_streaming_count"] = x["streaming_addon_count"] * fiber.astype(np.int64)
            x["support_streaming_balance"] = x["support_security_count"] - x["streaming_addon_count"]
            x["household_streaming"] = internet_binary(household & streaming)
        if set(x) != set(self.metadata["logical_columns"]):
            raise RuntimeError("Feature builder and provenance registry disagree")
        if any(np.isinf(np.asarray(x[name], dtype=np.float64)).any() for name in self.metadata["logical_numeric_columns"]):
            raise ValueError("Feature arithmetic produced infinity; inputs exceed safe numerical range")
        return x

    def transform(self, frame):
        checked = validate_frame(frame, self.metadata["cleaning_config"])
        x = self._derive(checked)
        result = np.empty((len(checked), 111), dtype=np.float32)
        numeric = np.column_stack([x[name] for name in self.metadata["numeric"]["names"]]).astype(np.float64, copy=False)
        np.copyto(numeric, np.broadcast_to(self._medians, numeric.shape), where=np.isnan(numeric))
        # Preserve StandardScaler's two operations rather than fused scale/bias.
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            numeric -= self._mean
            numeric /= self._scale
        if not np.isfinite(numeric).all():
            raise ValueError("Preprocessing output must be a 2D matrix without NA or infinity")
        position = numeric.shape[1]
        # The original feature pipeline checks finite float64 values; XGBoost's
        # inplace path subsequently casts them to float32.  A finite extreme
        # value may become float32 infinity there and is still accepted.  Do
        # not add a stricter input rejection at this equivalent cast boundary.
        with np.errstate(over="ignore", invalid="ignore"):
            result[:, :position] = numeric
        for group in self.metadata["categorical"]:
            values = x[group["name"]]
            seen = np.zeros(len(checked), dtype=bool)
            for value in group["categories"]:
                matches = values == value
                result[:, position] = matches
                seen |= matches
                position += 1
            if not seen.all():
                raise ValueError(f"Unknown category in {group['name']}")
        for index, name in enumerate(self.metadata["binary"]["names"]):
            values = np.asarray(x[name], dtype=np.float64)
            result[:, position] = np.where(np.isnan(values), self._binary_fill[index], values)
            position += 1
        if position != result.shape[1]:
            raise RuntimeError("Frozen output width mismatch")
        return result
