"""Build a native, offline Power BI project from the verified W2 input.

Run from any directory using the project's Python 3.12 environment. No Azure
credentials or cloud publication are needed. Rebuild to update the snapshot.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.w2_analysis import load_data, SERVICES
import pandas as pd

OUT = ROOT / "dashboard" / "powerbi"
REPORT = OUT / "W2_Churn.Report"
MODEL = OUT / "W2_Churn.SemanticModel"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
CHARTS = []


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def literal(value):
    if isinstance(value, bool):
        value = str(value).lower()
    elif isinstance(value, (int, float)):
        value = str(value) + "D"
    else:
        value = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": value}}}


def column(name):
    return {"Column": {"Expression": {"SourceRef": {"Entity": "Customers"}}, "Property": name}}


def measure(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "Customers"}}, "Property": name}}


def projection(name, is_measure=False):
    return {"field": measure(name) if is_measure else column(name),
            "queryRef": "Customers." + name, "nativeQueryRef": name}


def visual(page, name, kind, title, x, y, w, h, roles=None, objects=None):
    v = {"visualType": kind, "drillFilterOtherVisuals": True}
    if roles:
        v["query"] = {"queryState": {role: {"projections": [projection(n, m) for n, m in fields]}
                                           for role, fields in roles.items()}}
    if objects:
        v["objects"] = objects
    v["visualContainerObjects"] = {
        "title": [{"properties": {"show": literal(True), "text": literal(title),
                    "fontSize": literal(13), "fontColor": {"solid": {"color": literal("#163546")}}}}],
        "background": [{"properties": {"show": literal(True),
                        "color": {"solid": {"color": literal("#FFFFFF")}}, "transparency": literal(0)}}],
        "border": [{"properties": {"show": literal(True),
                     "color": {"solid": {"color": literal("#E1E8EE")}}, "radius": literal(6)}}],
    }
    write_json(REPORT / "definition/pages" / page / "visuals" / name / "visual.json", {
        "$schema": SCHEMA + "visualContainer/2.9.0/schema.json", "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": v,
    })


def textbox(page, name, text, x, y, w, h, size=14, color="#163546"):
    visual(page, name, "textbox", "", x, y, w, h, objects={"general": [{"properties": {
        "paragraphs": [{"textRuns": [{"value": text, "textStyle": {
            "fontSize": f"{size}pt", "fontFamily": "Microsoft YaHei", "color": color}}]}]
    }}]})


def chart(page, name, field, title, x, y, w, h, internet=False, kind="clusteredColumnChart"):
    value = "Internet churn rate" if internet else "Observed churn rate"
    count = "Internet customers" if internet else "Customer count"
    churned = "Internet churned" if internet else "Churned customers"
    visual(page, name, kind, title, x, y, w, h,
           {"Category": [(field, False)], "Y": [(value, True)],
            "Tooltips": [(count, True), (churned, True)]})
    CHARTS.append({"page": page, "visual": name, "field": field, "measure": value,
                   "title": title, "population": "internet customers" if internet else "current filter context"})


def page(name, title, internet=False, dimension_fields=None):
    """Create one PBIR page and its slicers/KPI cards.

    The optional dimension fields are only added when a real customer mapping
    CSV was supplied. This keeps region/industry out of the default Telco
    proxy model while allowing the requested filters when evidence exists.
    """
    extra = bool(dimension_fields)
    offset = 120 if extra else 0
    write_json(REPORT / "definition/pages" / name / "page.json", {
        "$schema": SCHEMA + "page/2.0.0/schema.json", "name": name, "displayName": title,
        "displayOption": "FitToPage", "height": 1080 + offset, "width": 1600,
    })
    textbox(name, "header", title + " | W2 客户流失探索", 20, 12 + offset, 1560, 60, 24)
    textbox(name, "subtitle", "Telco 公开代理数据｜横截面关联分析｜筛选后会按所选客户群重新计算", 20, 77 + offset, 1560, 38, 12)
    slicers = [
        ("Contract", "合同类型（订阅代理）"), ("InternetService", "网络服务类型"),
        ("PaymentMethod", "付款方式"), ("tenure_band", "客户期限（月）"),
        ("fee_level", "月费分组"),
    ]
    if dimension_fields:
        labels = {"region": "地区（真实映射）", "industry": "行业（真实映射）",
                  "subscription_type": "订阅类型（真实映射）"}
        slicers.extend((field, labels[field]) for field in dimension_fields)
    for i, (field, label) in enumerate(slicers):
        visual(name, "slicer_" + str(i), "slicer", label, 20 + 314 * (i % 5), 125 + 120 * (i // 5), 304, 112,
               {"Values": [(field, False)]}, {"data": [{"properties": {"mode": literal("Dropdown")}}],
               "selection": [{"properties": {"singleSelect": literal(False), "selectAllCheckboxEnabled": literal(True)}}]})
    metrics = [("Internet customers" if internet else "Customer count", "所选客户数"),
               ("Internet churned" if internet else "Churned customers", "观察到的流失客户数"),
               ("Internet churn rate" if internet else "Observed churn rate", "观察到的流失率"),
               ("Internet average monthly charge" if internet else "Average monthly charge", "平均月费")]
    for i, (metric, label) in enumerate(metrics):
        visual(name, "kpi_" + str(i), "card", label, 20 + i * 394, 248 + offset, 384, 115,
               {"Values": [(metric, True)]})
    textbox(name, "limitations", "源数据没有地区和行业；只有提供真实映射文件后才能筛选。合同类型只是订阅代理，月费不是 CLV。少于 30 人的小组请谨慎解读。", 20, 1005 + offset, 1560, 58, 11)


def build_model(dimensions=None):
    raw, df, source, edges = load_data()
    # A read-only analytic snapshot: omit customer identifiers and TotalCharges.
    # Tabular column identifiers are case-insensitive: Churn/churn would collide.
    data = df.drop(columns=["churn"]).copy()
    data["combination"] = data[SERVICES].eq("Yes").astype(int).astype(str).agg("".join, axis=1)
    data["tenure_band_order"] = data["tenure_band"].map({"[0,6)": 0, "[6,12)": 1, "[12,24)": 2, "[24,48)": 3, "[48,73)": 4}).astype("int64")
    data["manual_payment"] = data.manual_payment.map({True: "Manual", False: "Automatic"})
    data["has_internet"] = data.has_internet.map({True: "Yes", False: "No"})
    dimension_status = {"region": "source_missing", "industry": "source_missing", "subscription_type": "Contract proxy only"}
    if dimensions:
        extra = pd.read_csv(dimensions, dtype=str)
        required = {"customerID", "region", "industry", "subscription_type"}
        if not required.issubset(extra):
            raise ValueError(f"Real dimension mapping requires columns: {sorted(required)}")
        if extra.customerID.isna().any() or not extra.customerID.is_unique:
            raise ValueError("Customer mapping keys must be present and unique")
        joined = raw[["customerID"]].merge(extra[list(required)], on="customerID", how="left", validate="one_to_one")
        for c in ["region", "industry", "subscription_type"]:
            if joined[c].isna().any() or joined[c].str.strip().eq("").any():
                raise ValueError(f"Real mapping must cover all customers with a nonblank {c}")
            data[c] = joined[c].to_numpy()
            dimension_status[c] = "provided_real_mapping"
    columns, mtypes = [], []
    for c in data:
        if pd.api.types.is_integer_dtype(data[c]):
            typ, mt = "int64", "Int64.Type"
        elif pd.api.types.is_float_dtype(data[c]):
            typ, mt = "double", "type number"
        else:
            data[c] = data[c].astype(str)
            typ, mt = "string", "type text"
        definition = {"name": c, "dataType": typ, "sourceColumn": c, "summarizeBy": "none"}
        if c == "tenure_band_order":
            definition["isHidden"] = True
        if c == "tenure_band":
            definition["sortByColumn"] = "tenure_band_order"
        columns.append(definition)
        mtypes.append('{"' + c + '", ' + mt + '}')
    payload = data.to_json(orient="values", force_ascii=False).encode("utf-8")
    compressed = base64.b64encode(zlib.compress(payload)[2:-4]).decode("ascii")
    names = "{" + ", ".join('"' + c + '"' for c in data.columns) + "}"
    m = ["let", '    Rows = Json.Document(Binary.Decompress(Binary.FromText("' + compressed + '", BinaryEncoding.Base64), Compression.Deflate)),',
         "    Source = Table.FromRows(Rows, " + names + "),",
         "    Typed = Table.TransformColumnTypes(Source, {" + ", ".join(mtypes) + "})", "in", "    Typed"]
    definitions = [
        ("Customer count", "COALESCE(COUNTROWS('Customers'), 0)", "#,0"),
        ("Churned customers", "COALESCE(CALCULATE(COUNTROWS('Customers'), KEEPFILTERS('Customers'[Churn] = \"Yes\")), 0)", "#,0"),
        ("Observed churn rate", "DIVIDE([Churned customers], [Customer count])", "0.00%"),
        ("Average monthly charge", "AVERAGE('Customers'[MonthlyCharges])", "0.00"),
        ("Average tenure", "AVERAGE('Customers'[tenure])", "0.0"),
        ("Internet customers", "CALCULATE([Customer count], KEEPFILTERS('Customers'[InternetService] <> \"No\"))", "#,0"),
        ("Internet churned", "CALCULATE([Churned customers], KEEPFILTERS('Customers'[InternetService] <> \"No\"))", "#,0"),
        ("Internet churn rate", "DIVIDE([Internet churned], [Internet customers])", "0.00%"),
        ("Small group note", 'IF([Customer count] < 30, "n < 30: interpret cautiously", "")', None),
        ("Internet average monthly charge", "CALCULATE(AVERAGE('Customers'[MonthlyCharges]), KEEPFILTERS('Customers'[InternetService] <> \"No\"))", "0.00"),
    ]
    measures = [{"name": n, "expression": e, **({"formatString": f} if f else {})} for n, e, f in definitions]
    write_json(MODEL / "definition.pbism", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json", "version": "4.0", "settings": {}})
    write_json(MODEL / "model.bim", {"name": "W2_Churn", "compatibilityLevel": 1601, "model": {
        "culture": "en-US", "sourceQueryCulture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "tables": [{"name": "Customers", "columns": columns, "measures": measures,
                    "partitions": [{"name": "Customers", "mode": "import", "source": {"type": "m", "expression": m}}]}],
        "annotations": [{"name": "PBI_QueryOrder", "value": '["Customers"]'}]}})
    return {"source": source.relative_to(ROOT).as_posix(), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "rows": len(data), "churned": int(df.churn.sum()), "dimension_status": dimension_status,
            "data_contains_customer_id": False, "data_contains_TotalCharges": False,
            "snapshot_mode": "Embedded read-only analytic snapshot; rerun builder when input changes",
            "fee_quartile_edges": edges.tolist()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-dimensions", type=Path, help="Optional real customerID/region/industry/subscription_type mapping")
    parser.add_argument("--report-only", action="store_true", help="Regenerate PBIR pages without rewriting the semantic model")
    args = parser.parse_args()
    if args.report_only:
        model_json = json.loads((MODEL / "model.bim").read_text(encoding="utf-8"))
        model_columns = {c["name"] for t in model_json.get("model", {}).get("tables", []) for c in t.get("columns", [])}
        dimensions = [c for c in ("region", "industry", "subscription_type") if c in model_columns]
        metadata_path = ROOT / "reports" / "w2_powerbi_build.json"
        fallback_path = ROOT / "reports" / "w2_analysis_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else (
            json.loads(fallback_path.read_text(encoding="utf-8")) if fallback_path.exists() else {})
        source_path = ROOT / "data" / "raw" / "telco_customer_churn" / "WA_Fn-UseC_-Telco-Customer-Churn.csv"
        if source_path.exists():
            metadata["source"] = source_path.relative_to(ROOT).as_posix()
            metadata["source_sha256"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
        metadata["dimension_status"] = {
            "region": "existing_model" if "region" in model_columns else "source_missing",
            "industry": "existing_model" if "industry" in model_columns else "source_missing",
            "subscription_type": "existing_model" if "subscription_type" in model_columns else "Contract proxy only",
        }
    else:
        metadata = build_model(args.customer_dimensions)
    write_json(OUT / "W2_Churn.pbip", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0", "artifacts": [{"report": {"path": REPORT.name}}], "settings": {"enableAutoRecovery": True}})
    write_json(REPORT / "definition.pbir", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json", "version": "4.0", "datasetReference": {"byPath": {"path": "../" + MODEL.name}}})
    write_json(REPORT / "definition/version.json", {"$schema": SCHEMA + "versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write_json(REPORT / "definition/report.json", {"$schema": SCHEMA + "report/2.0.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY20SU09", "reportVersionAtImport": "2.0.0", "type": "SharedResources"}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources", "items": [
            {"name": "CY20SU09", "path": "BaseThemes/CY20SU09.json", "type": "BaseTheme"}]}]})
    if not args.report_only:
        dimensions = ["region", "industry", "subscription_type"] if args.customer_dimensions else []
    order = ["overview", "services", "profiles", "intersections"]
    write_json(REPORT / "definition/pages/pages.json", {"$schema": SCHEMA + "pagesMetadata/1.0.0/schema.json", "pageOrder": order, "activePageName": order[0]})
    page("overview", "01 总览：合同与客户期限", dimension_fields=dimensions)
    for i, (field, title) in enumerate([
        ("Contract", "H1｜各合同类型的观察流失率"), ("tenure_band", "H2｜各客户期限组的观察流失率"),
        ("InternetService", "网络服务类型与观察流失率"), ("fee_quartile", "H10｜月费四分位与观察流失率")]):
        chart("overview", "chart_" + str(i), field, title, 20 + (i % 2) * 788, 375 + (i // 2) * 310, 778, 300)
    page("services", "02 增值服务（互联网客户）", internet=True, dimension_fields=dimensions)
    chart("services", "service_count", "service_count", "H4 | 六项增值服务数量与观察流失率", 20, 375, 500, 610, True)
    for i, (field, title) in enumerate(zip(SERVICES, ["网络安全", "在线备份", "设备保护", "技术支持", "电视服务", "电影服务"])):
        chart("services", "service_" + str(i), field, "H4 | " + title, 532 + (i % 3) * 350, 375 + (i // 3) * 310, 338, 300, True)
    page("profiles", "03 付款方式与客户画像", dimension_fields=dimensions)
    for i, (field, title) in enumerate([
        ("PaymentMethod", "H6｜付款方式"), ("manual_payment", "H6｜手动与自动付款"),
        ("gender", "H9｜性别"), ("SeniorCitizen", "H9｜老年客户"), ("Partner", "H9｜是否有伴侣"), ("Dependents", "H9｜是否有受抚养人")]):
        chart("profiles", "profile_" + str(i), field, title, 20 + (i % 3) * 526, 375 + (i // 3) * 310, 514, 300)
    page("intersections", "04 组合模式与规则矩阵", dimension_fields=dimensions)
    for i, (row, col, title) in enumerate([
        ("Contract", "tenure_band", "合同 × 客户期限：观察流失率"),
        ("risk_rule", "fee_level", "H10｜规则 × 月费（仅描述性）"),
        ("Contract", "PaymentMethod", "合同 × 付款方式：观察流失率")]):
        visual("intersections", "matrix_" + str(i), "pivotTable", title, 20 + (i % 2) * 788, 375 + (i // 2) * 310, 778, 300,
               {"Rows": [(row, False)], "Columns": [(col, False)], "Values": [("Observed churn rate", True), ("Customer count", True)]})
        CHARTS.append({"page": "intersections", "visual": "matrix_" + str(i), "field": row + " x " + col, "measure": "Observed churn rate", "title": title})
    chart("intersections", "fee_services", "service_level", "H5 | 服务广度与观察流失率", 808, 685, 778, 300, True)
    metadata.update({"built_at_utc": datetime.now(timezone.utc).isoformat(), "format": "Native Power BI Project (PBIP / PBIR / TMSL)",
                     "pages": order, "analytical_visual_count": len(CHARTS), "analytical_visuals": CHARTS,
                     "requires_cloud_login": False, "native_desktop_verified": False})
    write_json(ROOT / "reports/w2_powerbi_build.json", metadata)
    print(json.dumps({"project": str(OUT / "W2_Churn.pbip"), "rows": metadata["rows"], "charts": len(CHARTS)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

