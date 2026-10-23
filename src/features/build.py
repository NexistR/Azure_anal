"""Week 4: 64 auditable logical candidates built from the 22-field W3 contract.

Only row-local arithmetic and configured, fixed thresholds are used here. Labels,
IDs, split membership, future outcomes, population aggregates and inferred dates
never enter the builder. The candidate matrix is deliberately not a selection.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from src.data.clean import load_config as load_cleaning_config
from src.data.preprocess import FeatureContract, FiniteArrayGuard, feature_columns


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "w4_features.json"
ADDONS = ("OnlineSecurity", "OnlineBackup", "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies")
PROTECTION = ("OnlineSecurity", "OnlineBackup", "DeviceProtection")
SUPPORT = ("OnlineSecurity", "TechSupport")
STREAMING = ("StreamingTV", "StreamingMovies")
REGISTRY_COLUMNS = [
    "feature_name", "family", "kind", "formula", "sources", "applicability",
    "missing_policy", "available_at", "leakage_review", "business_meaning", "categories",
]


def load_config(path=None) -> dict:
    """Read the fixed W4 rules, without any run paths or data statistics."""
    with Path(DEFAULT_CONFIG if path is None else path).open(encoding="utf-8-sig") as handle:
        config = json.load(handle)
    return _resolve_config(config)


def _resolve_config(config=None) -> dict:
    if config is None or isinstance(config, (str, Path)):
        return load_config(config)
    if not isinstance(config, Mapping):
        raise ValueError("W4 config must be a dictionary, JSON path, or None")
    resolved = copy.deepcopy(dict(config))
    required = {"version", "tenure_band_edges", "tenure_band_labels", "monthly_charge_band_edges", "monthly_charge_band_labels", "new_customer_months", "contract_months", "semantics"}
    if set(resolved) != required:
        raise ValueError(f"W4 config requires exactly {sorted(required)}")
    for prefix in ("tenure", "monthly_charge"):
        edges, labels = resolved[f"{prefix}_band_edges"], resolved[f"{prefix}_band_labels"]
        if not isinstance(edges, list) or not edges or any(type(v) not in (int, float) or not np.isfinite(v) or v < 0 for v in edges):
            raise ValueError(f"{prefix} band edges must be finite nonnegative numbers")
        if any(a >= b for a, b in zip(edges, edges[1:])):
            raise ValueError(f"{prefix} band edges must be strictly increasing")
        if not isinstance(labels, list) or len(labels) != len(edges) + 1 or any(not isinstance(v, str) or not v or '|' in v for v in labels) or len(labels) != len(set(labels)):
            raise ValueError(f"{prefix} band labels must be unique and match edges")
    if type(resolved["new_customer_months"]) is not int or resolved["new_customer_months"] < 0:
        raise ValueError("new_customer_months must be a nonnegative integer")
    if resolved["contract_months"] != {"Month-to-month": 1, "One year": 12, "Two year": 24}:
        raise ValueError("contract_months must preserve the documented nominal contract lengths")
    return resolved


def feature_registry(config=None) -> pd.DataFrame:
    """Return one provenance record per logical candidate, before one-hot encoding."""
    rules = _resolve_config(config)
    cleaning = load_cleaning_config()
    rows = []

    def add(name, family, kind, formula, sources, meaning, applicability="all customers", missing="none", categories=()):
        if kind == "binary" and applicability == "internet_applicable=1":
            missing = "retain structural NA; encode as computational zero only in preprocessing; internet_applicable distinguishes absence"
        rows.append({
            "feature_name": name, "family": family, "kind": kind, "formula": formula,
            "sources": "|".join(sources), "applicability": applicability,
            "missing_policy": missing,
            "available_at": "provided static snapshot; no verified timestamp",
            "leakage_review": "snapshot inputs only; no target, ID, future event, or population statistic; retrospective proxy only",
            "business_meaning": meaning, "categories": "|".join(map(str, categories)),
        })

    households = ["Partner", "Dependents"]
    internet = ["InternetService"]
    history = ["TotalCharges", "tenure"]
    comparisons = ["MonthlyCharges", "TotalCharges", "tenure"]
    services = ["PhoneService", "MultipleLines", "InternetService", *ADDONS]
    internet_na = "retain structural NA; training-fold median/zero fallback; internet_applicable distinguishes absence"
    history_na = "retain NA for missing TotalCharges or tenure=0; training-fold median/zero fallback plus charge_history_available"
    for kind in ("numeric", "categorical", "binary"):
        for name in cleaning["features"][kind]:
            family = "base_numeric" if kind == "numeric" else "base_category" if kind == "categorical" else "quality_flags"
            missing = "retain unknown NA; training-fold median/zero fallback plus total_charges_missing" if name == "TotalCharges" else "none"
            add(name, family, kind, f"identity({name})", [name], "保留 W3 合同中的原始预测字段或清洗标记", missing=missing, categories=cleaning["categories"].get(name, []))

    add("tenure_log1p", "tenure", "numeric", "log1p(tenure)", ["tenure"], "压缩在网时长尺度")
    add("monthly_charges_log1p", "charges", "numeric", "log1p(MonthlyCharges)", ["MonthlyCharges"], "压缩当前月费尺度")
    add("total_charges_log1p", "charges", "numeric", "log1p(TotalCharges)", ["TotalCharges"], "压缩已知累计费用尺度", missing="retain unknown NA; training-fold median/zero fallback plus total_charges_missing")
    add("tenure_band", "tenure", "categorical", f"right_closed_bins(tenure, {rules['tenure_band_edges']})", ["tenure"], "按固定业务阈值划分在网阶段", categories=rules["tenure_band_labels"])
    add("monthly_charge_band", "charges", "categorical", f"right_closed_bins(MonthlyCharges, {rules['monthly_charge_band_edges']})", ["MonthlyCharges"], "按预设阈值划分月费档位", categories=rules["monthly_charge_band_labels"])
    add("historical_monthly_average", "charge_history", "numeric", "TotalCharges / tenure if tenure > 0", history, "累计费用除在网月数的历史均值代理", applicability="tenure>0 and TotalCharges known", missing=history_na)
    add("current_to_historical_charge_ratio", "charge_history", "numeric", "MonthlyCharges / (TotalCharges / tenure) if tenure > 0 and TotalCharges > 0", comparisons, "当前月费相对历史均值的比例，不代表真实调价记录", applicability="tenure>0 and TotalCharges>0", missing=history_na + "; zero historical average remains NA; historical_charge_positive identifies denominator")
    add("monthly_charge_gap", "charge_history", "numeric", "MonthlyCharges - TotalCharges / tenure if tenure > 0", comparisons, "当前月费与历史均值代理的差额", applicability="tenure>0 and TotalCharges known", missing=history_na)
    add("constant_rate_total_proxy", "charge_history", "numeric", "MonthlyCharges * tenure if tenure > 0", ["MonthlyCharges", "tenure"], "假定当前费率恒定的累计算术场景；不是实际收入或 CLV", applicability="tenure>0", missing="tenure=0 remains NA; training-fold median/zero fallback plus tenure_zero")
    add("cumulative_charge_gap", "charge_history", "numeric", "TotalCharges - MonthlyCharges * tenure if tenure > 0", comparisons, "已知累计费用与恒定当前费率场景的差额", applicability="tenure>0 and TotalCharges known", missing=history_na)
    add("charge_history_available", "quality_flags", "binary", "int(tenure > 0 and TotalCharges is known)", history, "历史月均费用是否可计算")
    add("historical_charge_positive", "quality_flags", "binary", "int(tenure > 0 and TotalCharges > 0)", history, "历史月均费用是否可以作非零分母")
    add("household_profile", "household", "categorical", "concat(Partner, Dependents)", households, "伴侣和被抚养人的联合家庭结构", categories=["neither", "partner_only", "dependents_only", "both"])
    add("household_support_count", "household", "numeric", "int(Partner=Yes) + int(Dependents=Yes)", households, "家庭关系标记的数量；不是家庭人数")
    add("senior_without_household_support", "household", "binary", "int(SeniorCitizen=1 and Partner=No and Dependents=No)", ["SeniorCitizen", *households], "没有伴侣或被抚养人标记的老年客户")
    add("phone_applicable", "quality_flags", "binary", "int(PhoneService=Yes)", ["PhoneService"], "电话服务适用性标记")
    for name, fields, meaning in (
        ("internet_addon_count", ADDONS, "六项互联网附加服务的已开通数量"),
        ("protection_addon_count", PROTECTION, "安全、备份和设备保护的已开通数量"),
        ("support_security_count", SUPPORT, "安全与技术支持的已开通数量"),
        ("streaming_addon_count", STREAMING, "电视与电影流媒体的已开通数量"),
    ):
        add(name, "internet_bundle", "numeric", f"sum({','.join(fields)} = Yes) if InternetService != No", [*internet, *fields], meaning, applicability="internet_applicable=1", missing=internet_na)
    add("internet_without_addons", "internet_bundle", "binary", "int(all six add-ons != Yes) if InternetService != No", [*internet, *ADDONS], "有互联网服务但未购买附加项", applicability="internet_applicable=1", missing=internet_na)
    add("unprotected_streaming", "internet_bundle", "binary", "int(any streaming=Yes and OnlineSecurity=No and DeviceProtection=No) if internet applies", [*internet, *STREAMING, "OnlineSecurity", "DeviceProtection"], "使用流媒体但未开通安全或设备保护", applicability="internet_applicable=1", missing=internet_na)
    add("unsupported_fiber", "internet_bundle", "binary", "int(InternetService=Fiber optic and TechSupport=No) if internet applies", [*internet, "TechSupport"], "缺少技术支持的光纤用户", applicability="internet_applicable=1", missing=internet_na)
    add("internet_bundle_profile", "internet_bundle", "categorical", "profile(any protection/support, any streaming); no internet is explicit not_applicable", [*internet, *ADDONS], "支持保护与娱乐服务的组合", categories=["not_applicable", "basic", "protection_support", "entertainment", "mixed"])
    add("core_service_count", "service_mix", "numeric", "int(PhoneService=Yes) + int(InternetService!=No)", ["PhoneService", *internet], "电话和互联网两类核心服务的开通数量")
    add("active_service_count", "service_mix", "numeric", "int(PhoneService=Yes) + int(MultipleLines=Yes) + int(InternetService!=No) + sum(add-ons=Yes)", services, "已开通核心服务、附加线路与附加服务的总数；不适用项不计数")
    add("charge_per_active_service", "charges", "numeric", "MonthlyCharges / active_service_count if active_service_count > 0", ["MonthlyCharges", *services], "整张月账单按已开通项均摊的代理；不是单项服务价格", applicability="at least one active service", missing="zero active services remains NA; training-fold median/zero fallback; core_service_count identifies absence")
    add("contract_months", "contract", "numeric", "map Contract to nominal months {Month-to-month:1, One year:12, Two year:24}", ["Contract"], "名义合约月数，不代表剩余锁定期限")
    add("tenure_contract_ratio", "contract", "numeric", "tenure / nominal contract months", ["tenure", "Contract"], "在网时长相对当前名义合约长度的比例，不推断续约日期")
    add("nominal_contract_charge_proxy", "contract", "numeric", "MonthlyCharges * nominal contract months", ["MonthlyCharges", "Contract"], "当前月费乘名义合约长度的算术场景；不是未来收入或 CLV")
    add("tenure_contract_phase", "contract", "categorical", "zero if tenure=0; within_nominal if tenure<=contract_months; beyond_nominal otherwise", ["tenure", "Contract"], "在网时长与名义合约长度的相对位置，不代表实际合同到期", categories=["zero", "within_nominal", "beyond_nominal"])
    add("automatic_payment", "billing", "binary", "int(PaymentMethod in automatic bank transfer or credit card)", ["PaymentMethod"], "是否使用自动扣款渠道")
    add("billing_profile", "billing", "categorical", "concat(PaperlessBilling, automatic_payment)", ["PaperlessBilling", "PaymentMethod"], "无纸账单与自动付款的联合模式", categories=["paper_manual", "paper_auto", "paperless_manual", "paperless_auto"])
    add("manual_paperless", "billing", "binary", "int(PaperlessBilling=Yes and not automatic_payment)", ["PaperlessBilling", "PaymentMethod"], "使用无纸账单但尚未自动付款")
    add("month_to_month_manual_payment", "billing", "binary", "int(Contract=Month-to-month and not automatic_payment)", ["Contract", "PaymentMethod"], "按月合约与人工付款的组合")
    add("fiber_month_to_month", "contract", "binary", "int(InternetService=Fiber optic and Contract=Month-to-month) if internet applies", [*internet, "Contract"], "光纤服务且采用按月合约", applicability="internet_applicable=1", missing=internet_na)
    add("new_month_to_month", "contract", "binary", f"int(tenure <= {rules['new_customer_months']} and Contract=Month-to-month)", ["tenure", "Contract"], "预设新客阶段内采用按月合约")
    add("senior_manual_payment", "billing", "binary", "int(SeniorCitizen=1 and not automatic_payment)", ["SeniorCitizen", "PaymentMethod"], "采用人工付款渠道的老年客户")
    add("household_long_contract", "household", "binary", "int((Partner=Yes or Dependents=Yes) and Contract!=Month-to-month)", [*households, "Contract"], "有家庭关系标记且采用年度合约")
    add("fiber_streaming_count", "internet_bundle", "numeric", "streaming add-on count * int(InternetService=Fiber optic) if internet applies", [*internet, *STREAMING], "光纤环境下的流媒体服务数量交互项", applicability="internet_applicable=1", missing=internet_na)
    add("support_streaming_balance", "internet_bundle", "numeric", "sum(OnlineSecurity,TechSupport=Yes) - sum(StreamingTV,StreamingMovies=Yes) if internet applies", [*internet, *SUPPORT, *STREAMING], "支持安全项与娱乐项数量的差值", applicability="internet_applicable=1", missing=internet_na)
    add("household_streaming", "household", "binary", "int((Partner=Yes or Dependents=Yes) and any streaming=Yes) if internet applies", [*households, *internet, *STREAMING], "有家庭关系标记且使用流媒体服务", applicability="internet_applicable=1", missing=internet_na)
    result = pd.DataFrame(rows, columns=REGISTRY_COLUMNS)
    allowed = set(feature_columns(cleaning))
    if result.feature_name.duplicated().any() or len(result) != 64:
        raise RuntimeError("W4 registry must have exactly 64 distinct logical candidates")
    if any(set(value.split("|")) - allowed for value in result.sources):
        raise RuntimeError("Registry sources must be W3 feature whitelist fields")
    return result


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Unknown numerators and nonpositive/unknown denominators produce NA."""
    result = pd.Series(np.nan, index=numerator.index, dtype="float64")
    valid = numerator.notna() & denominator.notna() & denominator.gt(0)
    result.loc[valid] = numerator.loc[valid].astype(float) / denominator.loc[valid].astype(float)
    return result


class TelcoFeatureBuilder(TransformerMixin, BaseEstimator):
    """Cloneable stateless feature formulas with fitted schema/config validation."""

    def __init__(self, config=None):
        self.config = config

    def fit(self, X: pd.DataFrame, y=None):
        self.config_ = _resolve_config(self.config)
        self.contract_ = FeatureContract().fit(X)
        self.registry_ = feature_registry(self.config_)
        self.feature_names_in_ = self.contract_.feature_names_in_.copy()
        self.n_features_in_ = len(self.feature_names_in_)
        self._derive(self.contract_.transform(X))
        return self

    def _derive(self, frame: pd.DataFrame) -> pd.DataFrame:
        x = frame.copy(deep=True)
        cfg = self.config_
        tenure, monthly, total = x["tenure"], x["MonthlyCharges"], x["TotalCharges"]
        internet = x["InternetService"].ne("No")
        phone = x["PhoneService"].eq("Yes")
        fiber = x["InternetService"].eq("Fiber optic")
        partner, dependents = x["Partner"].eq("Yes"), x["Dependents"].eq("Yes")
        household = partner | dependents
        senior = x["SeniorCitizen"].eq(1)
        month_contract = x["Contract"].eq("Month-to-month")
        automatic = x["PaymentMethod"].isin(["Bank transfer (automatic)", "Credit card (automatic)"])
        paperless = x["PaperlessBilling"].eq("Yes")

        def internet_count(columns):
            return x.loc[:, list(columns)].eq("Yes").sum(axis=1).astype(float).where(internet)

        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            x["tenure_log1p"] = np.log1p(tenure.astype(float))
            x["monthly_charges_log1p"] = np.log1p(monthly)
            x["total_charges_log1p"] = np.log1p(total)
            x["tenure_band"] = pd.cut(tenure, [-np.inf, *cfg["tenure_band_edges"], np.inf], labels=cfg["tenure_band_labels"], right=True).astype(object)
            x["monthly_charge_band"] = pd.cut(monthly, [-np.inf, *cfg["monthly_charge_band_edges"], np.inf], labels=cfg["monthly_charge_band_labels"], right=True).astype(object)
            x["historical_monthly_average"] = _safe_divide(total, tenure)
            x["current_to_historical_charge_ratio"] = _safe_divide(monthly, x["historical_monthly_average"])
            x["monthly_charge_gap"] = monthly - x["historical_monthly_average"]
            x["constant_rate_total_proxy"] = (monthly * tenure.astype(float)).where(tenure.gt(0))
            x["cumulative_charge_gap"] = total - x["constant_rate_total_proxy"]
            x["charge_history_available"] = (tenure.gt(0) & total.notna()).astype(int)
            x["historical_charge_positive"] = (tenure.gt(0) & total.gt(0)).astype(int)
            x["household_profile"] = np.select([partner & dependents, partner, dependents], ["both", "partner_only", "dependents_only"], default="neither")
            x["household_support_count"] = partner.astype(int) + dependents.astype(int)
            x["senior_without_household_support"] = (senior & ~household).astype(int)
            x["phone_applicable"] = phone.astype(int)
            x["internet_addon_count"] = internet_count(ADDONS)
            x["protection_addon_count"] = internet_count(PROTECTION)
            x["support_security_count"] = internet_count(SUPPORT)
            x["streaming_addon_count"] = internet_count(STREAMING)
            x["internet_without_addons"] = x["internet_addon_count"].eq(0).astype(float).where(internet)
            streaming = x["streaming_addon_count"].gt(0)
            x["unprotected_streaming"] = (streaming & x["OnlineSecurity"].eq("No") & x["DeviceProtection"].eq("No")).astype(float).where(internet)
            x["unsupported_fiber"] = (fiber & x["TechSupport"].eq("No")).astype(float).where(internet)
            protected = x["protection_addon_count"].gt(0) | x["support_security_count"].gt(0)
            x["internet_bundle_profile"] = np.select([~internet, protected & streaming, protected, streaming], ["not_applicable", "mixed", "protection_support", "entertainment"], default="basic")
            x["core_service_count"] = phone.astype(int) + internet.astype(int)
            # For a total active-product count an inapplicable product contributes
            # zero. Internet-only counts above remain NA with an applicability flag.
            x["active_service_count"] = x["core_service_count"] + x["MultipleLines"].eq("Yes").astype(int) + x["internet_addon_count"].fillna(0)
            x["charge_per_active_service"] = _safe_divide(monthly, x["active_service_count"])
            x["contract_months"] = x["Contract"].map(cfg["contract_months"]).astype(int)
            x["tenure_contract_ratio"] = _safe_divide(tenure, x["contract_months"])
            x["nominal_contract_charge_proxy"] = monthly * x["contract_months"]
            x["tenure_contract_phase"] = np.select([tenure.eq(0), tenure.le(x["contract_months"])], ["zero", "within_nominal"], default="beyond_nominal")
            x["automatic_payment"] = automatic.astype(int)
            x["billing_profile"] = np.select([paperless & automatic, paperless, automatic], ["paperless_auto", "paperless_manual", "paper_auto"], default="paper_manual")
            x["manual_paperless"] = (paperless & ~automatic).astype(int)
            x["month_to_month_manual_payment"] = (month_contract & ~automatic).astype(int)
            x["fiber_month_to_month"] = (fiber & month_contract).astype(float).where(internet)
            x["new_month_to_month"] = (tenure.le(cfg["new_customer_months"]) & month_contract).astype(int)
            x["senior_manual_payment"] = (senior & ~automatic).astype(int)
            x["household_long_contract"] = (household & ~month_contract).astype(int)
            x["fiber_streaming_count"] = x["streaming_addon_count"] * fiber.astype(int)
            x["support_streaming_balance"] = x["support_security_count"] - x["streaming_addon_count"]
            x["household_streaming"] = (household & streaming).astype(float).where(internet)
        numeric = self.registry_.loc[self.registry_.kind.ne("categorical"), "feature_name"].tolist()
        if np.isinf(x.loc[:, numeric].to_numpy(dtype=float)).any():
            raise ValueError("Feature arithmetic produced infinity; inputs exceed safe numerical range")
        if set(x.columns) != set(self.registry_.feature_name):
            raise RuntimeError("Feature builder and provenance registry disagree")
        return x.loc[:, self.registry_.feature_name].copy()

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, ["contract_", "config_", "registry_"])
        return self._derive(self.contract_.transform(X))

    def get_feature_names_out(self, input_features=None) -> np.ndarray:
        check_is_fitted(self, ["contract_", "registry_"])
        if input_features is not None and list(input_features) != list(self.feature_names_in_):
            raise ValueError("input_features must match the registered 22-field order")
        return self.registry_.feature_name.to_numpy(dtype=object, copy=True)


def build_feature_preprocessor(config=None) -> Pipeline:
    """Return a named candidate matrix; fit imputation/scaling only in train folds.

    All-missing numeric columns are kept using sklearn's computational zero
    fallback. This does not change source/engineered NA into known money or
    applicable services. Binary structural NA is encoded as zero only here and
    is accompanied by the untouched internet_applicable input indicator.
    """
    rules = _resolve_config(config)
    registry = feature_registry(rules)
    numeric = registry.loc[registry.kind.eq("numeric"), "feature_name"].tolist()
    categorical = registry.loc[registry.kind.eq("categorical"), "feature_name"].tolist()
    binary = registry.loc[registry.kind.eq("binary"), "feature_name"].tolist()
    clean_categories = load_cleaning_config()["categories"]
    category_map = {row.feature_name: row.categories.split("|") for row in registry.itertuples() if row.kind == "categorical"}
    category_map.update({name: values for name, values in clean_categories.items() if name in categorical})
    columns = ColumnTransformer([
        ("numeric", Pipeline([
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scaler", StandardScaler()),
        ]), numeric),
        ("categorical", OneHotEncoder(categories=[category_map[name] for name in categorical], handle_unknown="error", sparse_output=False, dtype=np.float64), categorical),
        ("binary", SimpleImputer(strategy="constant", fill_value=0, keep_empty_features=True), binary),
    ], remainder="drop", sparse_threshold=0, verbose_feature_names_out=True)
    return Pipeline([
        ("builder", TelcoFeatureBuilder(rules)),
        ("columns", columns),
        ("finite", FiniteArrayGuard()),
    ])
