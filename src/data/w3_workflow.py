"""W3 orchestration and aggregate evidence, independent of the working directory."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .clean import PROJECT_ROOT, TelcoCleaner, read_raw
from .preprocess import build_preprocessor, split_xy

DATA_FILES = ["telco_clean.csv", "missing_total_charges_audit.csv", "X_train.csv", "X_validation.csv",
              "y_train.csv", "y_validation.csv", "ids_train.csv", "ids_validation.csv", "split_membership.csv"]
TABLE_FILES = ["w3_field_audit.csv", "w3_category_reconciliation.csv", "w3_quality_checks.csv",
               "w3_charge_difference_summary.csv", "w3_before_after.csv", "w3_split_summary.csv",
               "w3_preprocessor_parameters.csv", "w3_feature_dictionary.csv"]


def validate_output_targets(root, paths):
    """Reject redirected or non-file destinations before writing any artifacts."""
    root = Path(root).absolute()
    if root.resolve() != root:
        raise ValueError(f"Output root must already be resolved and must not redirect through a link: {root}")
    for path in paths:
        path = Path(path)
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError(f"Output target is redirected outside its destination or is a link: {path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"Output target must be a file: {path}")
        if path.exists() and path.stat().st_nlink > 1:
            raise ValueError(f"Output target has multiple hard links and cannot be overwritten: {path}")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump_json(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def dump_csv(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n", float_format="%.12g")


def relative(path):
    return Path(path).resolve().relative_to(PROJECT_ROOT).as_posix()


def markdown_table(frame):
    def cell(value):
        return (f"{value:.6g}" if isinstance(value, (float, np.floating)) else str(value)).replace("|", "\\|")
    return "\n".join(["| " + " | ".join(map(str, frame.columns)) + " |",
                       "| " + " | ".join(["---"] * len(frame.columns)) + " |"] +
                      ["| " + " | ".join(cell(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None)])


def write_cleaning_report(summary, balance, stats, split_summary, checks, fee_difference, reports_dir):
    documented = checks.loc[checks.status.eq("documented"), ["rule", "count", "action", "basis"]]
    body = f"""# W3 数据清洗前后对比报告

本报告由 `scripts/run_week3.py` 随本次运行自动生成。运行时间（UTC）：{summary['completed_at_utc']}；规则版本：`{summary['rule_version']}`。

## 1. 本次实际结果

原始 Telco 的 {summary['rows']:,} 位客户全部保留，生成 {summary['columns']} 列清洗主表。流失 {summary['churned']:,} 人、未流失 {summary['nonchurned']:,} 人，客户顺序、编号与标签对应关系不变。主表保留 {summary['total_charges_missing']} 个未知累计费用，并添加明确缺失标记；模型矩阵经过训练内插补后，缺失和无穷值为 0。

这批数据通过 {summary['quality_rules']} 条已实现的质量检查，失败数 {summary['quality_rules_failed']}。其中已知缺失和零年限边界属于“保留并说明”，不是偷偷删除后宣称所有问题不存在。数据源为公开教学代理，结论不等于 Azure 真实客户结论。

## 2. 清洗前后对账

{markdown_table(balance)}

原 CSV 读取时所有列暂存为字符串，因此累计费用空白在读取层不是 pandas NA。清洗将其改成显式 NA；信息的未知数量没有增加，也没有被虚构补全。没有删除行、去重删人、缩尾或修改已知累计金额。

逐字段类型和缺失见 [字段审计](tables/w3_field_audit.csv)，逐类别人数见 [类别前后对账](tables/w3_category_reconciliation.csv)。主表新增 churn_label、total_charges_missing、tenure_zero、internet_applicable；前者只用作目标，后三者可以进入特征。

## 3. 异常与账单关系

{markdown_table(documented)}

完整检查及分母见 [质量检查表](tables/w3_quality_checks.csv)。非法类别、重复/空客户键、数值非有限值、违规范围和服务逻辑冲突会报错。当前样本最大值不是永久业务上限；IQR 只是分布诊断。

下面计算 `TotalCharges − tenure × MonthlyCharges`，单位与源费用字段一致：

{markdown_table(fee_difference)}

只有累计费用已知的客户进入差值分布。历史调价、优惠和精确账期不可见，差值不是自动纠错依据，不能拿当前月费乘年限回填真实历史账单。无互联网的结构性类别保持原意；六项增值服务与电话状态均通过交叉检查。

## 4. 标准化、编码与防泄漏

X 有 {summary['input_feature_columns']} 列：3 个数值、16 个类别、3 个标记；不包含 customerID、Churn 或 churn_label。独热展开后共 {summary['encoded_columns']} 列。固定种子 {summary['seed']}，按标签分层切分，留出比例 {summary['test_size']}，本周只演示预处理接口。

{markdown_table(split_summary)}

以下参数只从训练子集拟合：

{markdown_table(stats)}

`training_median` 是训练中位数，`training_mean_after_imputation` 和 `training_scale` 是插补后的训练均值和标准差；缩放为 `(数值−训练均值)/训练标准差`。`all_missing_fallback_used` 表示整列训练数据缺失时是否用了计算用 0，本次可直接查看该列。该回退与一般训练中位数插补均不反写清洗主表。

验证集仅 transform；额外核验了训练参数未被验证集改变、划分无交集、保存再加载预处理器的结果相同。代码测试进一步覆盖错误输入和改变留出数据的情况，见 [测试证据](w3_test_results.json)。本周没有训练流失预测模型，没有输出 AUC、准确率或正式 CLV。

## 5. 交付位置与复现证据

- 清洗主表和客户级追踪：`{summary['output_dir']}/`，共 9 份 CSV；X、y、ids 的同名拆分文件严格按行对应，勿单独排序。
- 已拟合预处理器与 49 列名称：`{summary['model_dir']}/`，这不是预测模型。
- [清洗规则 C01–C10](w3_cleaning_rules.md)、[特征工程设计 v1](feature_engineering_design_v1.md)、[运行说明](../docs/operations/W3_run_and_delivery.md)。
- [本次配置、代码和业务产物指纹](w3_run_metadata.json)、[新进程与 Notebook 验证](w3_verification.json)、[隔离环境验证](w3_clean_environment_verification.json)。这些验证文件分别记录自身执行状态；未运行的检查不能由本报告代替。
- [已执行 Notebook](../notebooks/03_cleaning.ipynb) 与 [浏览器阅读版](../notebooks/03_cleaning.html) 展示清洗和训练内变换过程。

输入 SHA-256：`{summary['source_sha256']}`。本次运行开始/结束均核对来源登记中的 {summary['raw_files_unchanged']} 个原始文件，指纹未变。重跑仅比较 9 份数据 CSV 与 8 份汇总 CSV 的稳定业务内容，不要求执行时间、Notebook 单元 ID 或二进制字节完全相同。

## 6. 验收限制与 W4 交接

原始“清洗后无缺失和异常”的字面要求在清洗主表上不申报通过：未知累计费用仍有 {summary['total_charges_missing']} 个；模型输入无缺失/无穷值，已实现非法值规则没有失败。保留未知含义符合 W2→W3 交接，不能用删人或猜金额消除信息缺口。

特征工程设计交付 12 项真实时间特征，包含公式、窗口、所需数据、可用时点和泄漏约束，满足“设计至少 10 个”的数量要求；实际计算为 0，因为缺事件日期和历史日志。项目介绍中的时间特征构建仍待真实数据。无地区、行业、续约日期或可靠跨表客户键的部分继续登记数据缺口。

W4 从 25 列主表开发正式候选特征、登记公式并审查泄漏。W3 的 49 列编码矩阵不等于已完成 W4 的至少 50 项候选特征。后续正式切分后必须重新建立未拟合 Pipeline，并只在训练折中拟合插补、缩放和特征选择。
"""
    (reports_dir / "w3_cleaning_report.md").write_text(body, encoding="utf-8")


def raw_snapshot():
    manifest = pd.read_csv(PROJECT_ROOT / "reports/tables/data_manifest.csv")
    result = {}
    for row in manifest.itertuples():
        path = (PROJECT_ROOT / row.relative_path).resolve()
        if not path.is_relative_to(PROJECT_ROOT / "data/raw"):
            raise ValueError("Raw manifest path escapes data/raw")
        actual = digest(path)
        if actual.casefold() != row.sha256.casefold():
            raise ValueError(f"Raw source does not match W1 manifest: {row.relative_path}")
        result[row.relative_path] = actual
    return result


def quality_tables(raw, clean, config):
    """Report explicit/semantic missingness separately, without customer identifiers."""
    fields, categories, checks = [], [], []
    n = len(clean)
    for name in clean:
        source = raw[name] if name in raw else None
        blank = source.map(lambda v: isinstance(v, str) and not v.strip()) if source is not None else None
        fields.append({"field": name, "before_dtype": str(source.dtype) if source is not None else "not_present",
                       "after_dtype": str(clean[name].dtype),
                       "before_explicit_na": int(source.isna().sum()) if source is not None else 0,
                       "before_blank": int(blank.sum()) if source is not None else 0,
                       "before_semantic_missing": int((source.isna() | blank).sum()) if source is not None else 0,
                       "after_missing": int(clean[name].isna().sum()),
                       "after_unique": int(clean[name].nunique(dropna=False)),
                       "origin": name if source is not None else {
                           "churn_label": "Churn", "total_charges_missing": "TotalCharges",
                           "tenure_zero": "tenure", "internet_applicable": "InternetService"}[name]})
    for name, allowed in config["categories"].items():
        before = raw[name].astype(str).str.strip()
        if name == "SeniorCitizen":
            before = pd.to_numeric(before)
        for category in allowed:
            categories.append({"field": name, "category": category,
                               "before": int(before.eq(category).sum()), "after": int(clean[name].eq(category).sum())})

    def check(rule, count, action="reject", basis="data contract", scope="all customers"):
        checks.append({"rule": rule, "count": int(count), "proportion": float(count/n), "scope": scope,
                       "action": action, "basis": basis, "status": "passed" if count == 0 else "documented" if action == "retain_and_flag" else "failed"})

    check("missing_customer_id", clean.customerID.isna().sum())
    check("duplicate_customer_id", clean.customerID.duplicated().sum())
    check("invalid_churn_label", (~clean.Churn.isin(config["label_mapping"])).sum())
    for name, allowed in config["categories"].items():
        check("invalid_category_" + name, (~clean[name].isin(allowed)).sum())
    for name in config["numeric_rules"]:
        values = clean[name]
        rule = config["numeric_rules"][name]
        check("nonfinite_" + name, (values.notna() & ~np.isfinite(values)).sum())
        check("missing_" + name, values.isna().sum(), "retain_and_flag" if name in config["allowed_nulls"] else "reject")
        if rule["minimum"] is not None:
            lower = values.lt(rule["minimum"]) if rule["minimum_inclusive"] else values.le(rule["minimum"])
            check("below_minimum_" + name, lower.sum())
        if rule["maximum"] is not None:
            check("above_maximum_" + name, values.gt(rule["maximum"]).sum())
        if rule["integer"]:
            check("noninteger_" + name, values.dropna().mod(1).ne(0).sum())
    no_internet = clean.InternetService.eq("No")
    for name in config["internet_service_columns"]:
        check("internet_consistency_" + name, no_internet.ne(clean[name].eq("No internet service")).sum())
    check("phone_consistency", clean.PhoneService.eq("No").ne(clean.MultipleLines.eq("No phone service")).sum())
    check("zero_tenure_boundary", clean.tenure.eq(0).sum(), "retain_and_flag", "Legal lower boundary, not deleted")
    for name in ("tenure", "MonthlyCharges", "TotalCharges"):
        q1, q3 = clean[name].quantile([.25, .75])
        multiplier = config.get("iqr_multiplier", 1.5)
        low, high = q1-multiplier*(q3-q1), q3+multiplier*(q3-q1)
        check("iqr_diagnostic_"+name, (clean[name].lt(low) | clean[name].gt(high)).sum(), "retain_and_flag",
              f"{multiplier:g} IQR diagnostic, fences [{low:g}, {high:g}], not a business validity bound")
    return pd.DataFrame(fields), pd.DataFrame(categories), pd.DataFrame(checks)


def run_workflow(config, source, output_dir, model_dir, reports_dir):
    """Generate canonical data, a fit/transform demonstration and auditable outputs."""
    source = Path(source).resolve()
    if not source.is_relative_to(PROJECT_ROOT):
        raise ValueError("Versioned input must be inside the project; copy it under data/raw and update the config/manifest first")
    validate_output_targets(output_dir, [output_dir / name for name in DATA_FILES])
    validate_output_targets(model_dir, [model_dir / name for name in ("preprocessor.joblib", "feature_names.json")])
    validate_output_targets(reports_dir, [reports_dir / "tables" / name for name in TABLE_FILES] +
                            [reports_dir / name for name in ("w3_run_metadata.json", "w3_verification.json", "w3_cleaning_report.md")])
    source_before = digest(source)
    if source_before != config["expected_sha256"].lower():
        raise ValueError("Input SHA-256 does not match the explicitly configured data version")
    raw_before = raw_snapshot()
    raw = read_raw(source)
    unchanged = raw.copy(deep=True)
    cleaner = TelcoCleaner(config)
    cleaned = cleaner.fit_transform(raw)
    pd.testing.assert_frame_equal(raw, unchanged)
    pd.testing.assert_frame_equal(cleaned, cleaner.transform(cleaned))
    if list(raw.customerID.str.strip()) != list(cleaned.customerID):
        raise AssertionError("Cleaning changed customer order or identifiers")
    if not raw.Churn.str.strip().equals(cleaned.Churn):
        raise AssertionError("Cleaning changed churn labels")
    X, y, ids = split_xy(cleaned, config)
    train, valid = train_test_split(np.arange(len(cleaned)), test_size=config["test_size"],
                                    random_state=config["seed"], stratify=y)
    preprocessor = build_preprocessor(config)
    train_matrix = preprocessor.fit_transform(X.iloc[train])
    valid_matrix = preprocessor.transform(X.iloc[valid])
    columns = preprocessor.get_feature_names_out().tolist()
    assert not any("churn" in name.casefold() or "customerid" in name.casefold() for name in columns)
    num = preprocessor.named_steps["columns"].named_transformers_["numeric"]
    imputer, scaler = num.named_steps["imputer"], num.named_steps["scaler"]
    medians = X.iloc[train][config["features"]["numeric"]].median().fillna(0).to_numpy()
    np.testing.assert_allclose(imputer.statistics_, medians)
    means_before = scaler.mean_.copy()
    preprocessor.transform(X.iloc[valid])
    np.testing.assert_array_equal(means_before, scaler.mean_)
    assert not set(train) & set(valid) and len(set(train) | set(valid)) == len(cleaned)
    for folder in (output_dir, model_dir, reports_dir / "tables"):
        folder.mkdir(parents=True, exist_ok=True)
    dump_csv(output_dir / "telco_clean.csv", cleaned)
    audit_private = cleaned.loc[cleaned.total_charges_missing.eq(1),
                                ["customerID", "tenure", "MonthlyCharges", "TotalCharges", "total_charges_missing", "tenure_zero", "Churn"]].copy()
    audit_private["reason"] = "Unknown cumulative charge: retain NA; no business evidence for zero"
    dump_csv(output_dir / "missing_total_charges_audit.csv", audit_private)
    for split, index, matrix in (("train", train, train_matrix), ("validation", valid, valid_matrix)):
        dump_csv(output_dir / f"X_{split}.csv", pd.DataFrame(matrix, columns=columns))
        dump_csv(output_dir / f"y_{split}.csv", y.iloc[index].reset_index(drop=True).to_frame())
        dump_csv(output_dir / f"ids_{split}.csv", ids.iloc[index].reset_index(drop=True).to_frame())
    split_labels = np.full(len(cleaned), "validation", dtype=object)
    split_labels[train] = "train"
    dump_csv(output_dir / "split_membership.csv", pd.DataFrame({"customerID": ids, "split": split_labels}))
    pipeline_path = model_dir / "preprocessor.joblib"
    joblib.dump(preprocessor, pipeline_path)
    restored = joblib.load(pipeline_path)
    np.testing.assert_array_equal(valid_matrix, restored.transform(X.iloc[valid]))

    field_table, frequency_table, checks = quality_tables(raw, cleaned, config)
    tables_dir = reports_dir / "tables"
    dump_csv(tables_dir / "w3_field_audit.csv", field_table)
    dump_csv(tables_dir / "w3_category_reconciliation.csv", frequency_table)
    dump_csv(tables_dir / "w3_quality_checks.csv", checks)
    difference = cleaned.TotalCharges - cleaned.tenure * cleaned.MonthlyCharges
    # Large differences are diagnostics only: current monthly price is not a historical bill.
    fee_difference = difference.describe(percentiles=[.01, .25, .5, .75, .99]).rename_axis("statistic").reset_index(name="value")
    dump_csv(tables_dir / "w3_charge_difference_summary.csv", fee_difference)
    monthly_rule = checks.loc[checks.rule.eq("iqr_diagnostic_MonthlyCharges"), "count"].item()
    balance = pd.DataFrame([
        ("rows", len(raw), len(cleaned), "preserve"),
        ("columns", raw.shape[1], cleaned.shape[1], "add 4 documented fields"),
        ("unique_customer_ids", raw.customerID.str.strip().nunique(), ids.nunique(), "preserve"),
        ("churn_yes", raw.Churn.str.strip().eq("Yes").sum(), y.sum(), "preserve"),
        ("churn_no", raw.Churn.str.strip().eq("No").sum(), y.eq(0).sum(), "preserve"),
        ("total_charges_blank", raw.TotalCharges.str.strip().eq("").sum(), 0, "blank converted to NA"),
        ("total_charges_explicit_na", raw.TotalCharges.isna().sum(), cleaned.TotalCharges.isna().sum(), "preserve unknown meaning"),
        ("total_charges_semantic_missing", raw.TotalCharges.str.strip().eq("").sum()+raw.TotalCharges.isna().sum(), cleaned.TotalCharges.isna().sum(), "preserve"),
        ("total_charges_nonempty_parse_failure", 0, 0, "strict conversion rejects invalid tokens"),
        ("zero_tenure", pd.to_numeric(raw.tenure).eq(0).sum(), cleaned.tenure_zero.sum(), "preserve"),
        ("no_internet", raw.InternetService.str.strip().eq("No").sum(), cleaned.internet_applicable.eq(0).sum(), "preserve"),
        ("internet_customers", raw.InternetService.str.strip().ne("No").sum(), cleaned.internet_applicable.sum(), "preserve"),
        ("monthly_charges_iqr_outliers", monthly_rule, monthly_rule, "diagnose, no winsorization"),
        ("dropped_rows", 0, 0, "no deletion"),
    ], columns=["metric", "before", "after", "policy"])
    dump_csv(tables_dir / "w3_before_after.csv", balance)
    split_summary = pd.DataFrame([
        {"split": name, "rows": len(index), "churned": int(y.iloc[index].sum()),
         "churn_rate": float(y.iloc[index].mean()), "missing_total_charges": int(cleaned.iloc[index].total_charges_missing.sum()),
         "matrix_columns": len(columns), "nonfinite_values": int((~np.isfinite(matrix)).sum())}
        for name, index, matrix in (("train", train, train_matrix), ("validation", valid, valid_matrix))])
    dump_csv(tables_dir / "w3_split_summary.csv", split_summary)
    stats = pd.DataFrame({"field": config["features"]["numeric"], "training_median": imputer.statistics_,
                          "training_mean_after_imputation": scaler.mean_, "training_scale": scaler.scale_,
                          "training_variance": scaler.var_, "fit_rows": len(train),
                          "training_nonmissing": X.iloc[train][config["features"]["numeric"]].notna().sum().to_numpy(),
                          "all_missing_fallback_used": X.iloc[train][config["features"]["numeric"]].isna().all().to_numpy()})
    dump_csv(tables_dir / "w3_preprocessor_parameters.csv", stats)
    dump_csv(tables_dir / "w3_feature_dictionary.csv", pd.DataFrame([
        {"position": i, "feature": name, "type": "float64", "source": name.split("__", 1)[1],
         "meaning": "training median then z-score" if name.startswith("numeric__") else "explicit registered category" if name.startswith("categorical__") else "unscaled cleaning flag",
         "scope": "W3 preprocessing demonstration; not W4 final feature set"}
        for i, name in enumerate(columns)]))
    dump_json(model_dir / "feature_names.json", columns)
    if digest(source) != source_before or raw_snapshot() != raw_before:
        raise AssertionError("A raw source changed while executing W3")
    business_files = [*[output_dir / name for name in DATA_FILES], *[tables_dir / name for name in TABLE_FILES]]
    business_hashes = {("data/" if p.parent == output_dir else "tables/") + p.name: digest(p) for p in sorted(business_files)}
    summary = {
        "status": "passed", "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "rule_version": config["version"], "seed": config["seed"], "test_size": config["test_size"],
        "source": relative(source), "source_sha256": source_before, "raw_files_unchanged": len(raw_before),
        "rows": len(cleaned), "columns": cleaned.shape[1], "unique_customer_ids": int(ids.nunique()),
        "churned": int(y.sum()), "nonchurned": int(y.eq(0).sum()), "total_charges_missing": int(cleaned.TotalCharges.isna().sum()),
        "internet_customers": int(cleaned.internet_applicable.sum()), "tenure_zero": int(cleaned.tenure_zero.sum()),
        "input_feature_columns": len(X.columns), "encoded_columns": len(columns),
        "train_rows": len(train), "validation_rows": len(valid), "matrix_nonfinite_values": 0,
        "quality_rules": len(checks), "quality_rules_failed": int(checks.status.eq("failed").sum()),
        "train_only_statistics_verified": True, "id_label_excluded": True, "idempotent": True,
        "input_dataframe_unchanged": True, "serialized_transform_identical": True,
        "output_dir": relative(output_dir), "model_dir": relative(model_dir), "reports_dir": relative(reports_dir),
        "code_sha256": {relative(p): digest(p) for p in [PROJECT_ROOT / "src/data/clean.py", PROJECT_ROOT / "src/data/preprocess.py", Path(__file__), PROJECT_ROOT / "scripts/run_week3.py"]},
        "resolved_config": config,
        "packages": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "scipy", "scikit-learn", "joblib")},
        "business_hashes": business_hashes,
        "limits": {"canonical_data_without_missing": bool(not cleaned.isna().any().any()),
                   "canonical_missing_values": f"{int(cleaned.TotalCharges.isna().sum())} unknown TotalCharges retained; no claimed true zero",
                   "temporal_features_computed": 0, "temporal_features_design": "See feature_engineering_design_v1.md; source has no event dates",
                   "model_evaluation_performed": False, "structural_absence_is_not_missing": True},
    }
    assert summary["quality_rules_failed"] == 0
    write_cleaning_report(summary, balance, stats, split_summary, checks, fee_difference, reports_dir)
    dump_json(reports_dir / "w3_run_metadata.json", summary)
    return summary
