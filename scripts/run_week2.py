"""Build and execute the Week 2 notebook; verify and package all deliverables.

Usage: python scripts/run_week2.py --verify-reproducibility
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT
for name, folder in {"JUPYTER_CONFIG_DIR":"jupyter_config", "JUPYTER_DATA_DIR":"jupyter_data",
                     "JUPYTER_RUNTIME_DIR":"jupyter_runtime", "IPYTHONDIR":"ipython",
                     "MPLCONFIGDIR":"matplotlib"}.items():
    directory = ROOT / ".cache" / folder
    directory.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(directory)

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter
from nbconvert.filters import markdown2html
import pandas as pd
import numpy as np
from PIL import Image as PILImage


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_notebook():
    md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell
    cells = [
        md("# Week 2：问题导向 EDA 与假设验证\n\n"
           "基于 Telco 公开代理数据，执行冻结的八周项目 W2 范围。\n\n"
           "20 张图表，7 项完成分析并形成结论，另 3 项说明不可验证。"
           "所有比例是静态快照已观察流失率，不是未来风险预测。\n\n"
           "复现：从项目根目录运行 `.venv/Scripts/python.exe scripts/run_week2.py --verify-reproducibility`。"
           "首次环境准备参见交付目录 README；选择 **Python 3.12 (Azure W2)** 内核后可 Restart & Run All。"),
        md("## D1：数据合同与分析口径\n\n"
           "1. 主键客户粒度，原始输入 7,043×21，以 W1 SHA-256 冻结版本。\n"
           "2. 六项服务：OnlineSecurity、OnlineBackup、DeviceProtection、TechSupport、StreamingTV、StreamingMovies。"
           "H4 主分析为互联网客户，保留全体及 DSL/光纤敏感性。\n"
           "3. tenure 分箱左闭右开：[0,6)、[6,12)、[12,24)、[24,48)、[48,73)。\n"
           "4. 高月费≥全样本中位数70.35；少服务≤2。风险规则为月付且tenure<6，不使用标签计算个体风险。\n"
           "5. TotalCharges 只检查空白，不转数值或加入分析。分箱和计数是临时分析变量，不输出客户特征表。\n"
           "6. 双侧检验，α=.05；6项主检验、6项服务检验、4项人口检验、6项敏感性检验分别 Bonferroni 校正。"
           "比例区间为逐组 Wilson 95%，非同时区间；格内 n<30 标*。"),
        code("from pathlib import Path\nimport sys\n"
             "start = Path.cwd().resolve()\n"
             "candidates = [start, *start.parents]\n"
             "PACKAGE = next(p for p in candidates if (p / 'src/w2_analysis.py').is_file())\n"
             "sys.path.insert(0, str(PACKAGE))\n"
             "from src.w2_analysis import load_data, analyze, plot_all, hypothesis_results, SEED\n"
             "import numpy as np\nfrom IPython.display import display, Markdown, Image\n"
             "np.random.seed(SEED)\n"
             "raw, df, source, fee_edges = load_data()\n"
             "print(f'数据形状：{raw.shape}；流失：{df.churn.sum()}/{len(df)}（{df.churn.mean():.2%}）；seed={SEED}')\n"
             "print('月费分位边界：', fee_edges.tolist())\n"
             "display(raw.dtypes.rename('dtype').to_frame())\n"
             "display(df[['tenure', 'MonthlyCharges']].describe())"),
        md("## D2–D4：执行统计与生成图表\n\n核心逻辑复用于 `src/w2_analysis.py`，Notebook 负责编排、展示与解释。"
           "表格保留样本量、流失人数、比例及区间；分析仅导出聚合结果。"),
        code("result = analyze()\n"
             "chart_index = plot_all(result)\n"
             "hypotheses = hypothesis_results(result)\n"
             "display(result['tests'][['test_id','n','method','effect_name','effect','p_value','p_bonferroni']])"),
    ]
    phases=[(1,6,"D2：六张单变量分布"),(7,8,"D2：合同与客户年限假设"),
            (9,13,"D3：服务采用、费用与支付方式"),(14,20,"D4：人口细分、交叉分析与矩阵雏形")]
    for start, end, title in phases:
        cells.append(md("## "+title))
        for number in range(start,end+1):
            cells.append(code(
                f"chart = chart_index.loc[chart_index.chart_id.eq('{number:02d}')].iloc[0]\n"
                "display(Markdown(f'### 图{chart.chart_id}：{chart.title}（{chart.hypothesis_id}）'))\n"
                "display(Image(filename=str(PACKAGE / chart.path), width=1000))\n"
                "display(Markdown(f'**结论：** {chart.conclusion}\\n\\n**下一步：** {chart.action}\\n\\n**限制：** {chart.limitations}'))\n"
                "display(Markdown(f'聚合证据：`{chart.evidence}`'))"))
    cells.extend([
        md("## 假设结果与限制\n\nH1/H2支持预设方向；H4/H5/H6/H9/H10仅部分支持可观察命题。"
           "H1 p值为合同总体检验；H5高费DSL少服务仅3人，不足以作稳定结论；"
           "H10 p值仅对应费用分位与标签关联，不验证资源分配收益。"),
        code("display(hypotheses[['hypothesis_id','status','conclusion','p_bonferroni','effect']])\n"
             "display(result['tables']['w2_fee_service_by_internet'])\n"
             "display(result['tables']['w2_risk_value_prototype'])"),
        md("## W3 输入与验收\n\n11 个 TotalCharges 空白与 tenure=0 重合，先核查业务规则再确定处理；"
           "保留 No internet service 的结构性含义。完整建议见 `reports/w2_to_w3_cleaning_recommendations.md`。"
           "H3缺使用序列，H7缺客户映射和时间，H8缺自动续费/续约历史。"),
        code("display(result['tables']['w2_quality_observations'])\n"
             "print(result['h7']['decision'])\n"
             "assert len(chart_index) >= 15\n"
             "assert hypotheses.analyzed.sum() >= 5\n"
             "assert set(['H1','H2','H4','H10']).issubset(set(hypotheses.loc[hypotheses.analyzed,'hypothesis_id']))\n"
             "assert all((PACKAGE / path).is_file() for path in chart_index.path)\n"
             "assert result['metadata']['raw_unchanged']\n"
             "print(f'完成：{len(chart_index)}张图，{int(hypotheses.analyzed.sum())}项完成分析并形成结论；原始数据哈希未改变。')"),
    ])
    notebook=nbformat.v4.new_notebook(cells=cells)
    notebook.metadata.kernelspec={"name":"azure-w2","display_name":"Python 3.12 (Azure W2)","language":"python"}
    notebook.metadata.language_info={"name":"python","version":"3.12.9"}
    # Stable cell identifiers keep source diffs reviewable.
    for index,cell in enumerate(notebook.cells):
        cell.id=f"w2-cell-{index:02d}"
    return notebook


def snapshot_raw():
    manifest=pd.read_csv(PROJECT / "reports/tables/data_manifest.csv")
    result={}
    for row in manifest.itertuples():
        path=PROJECT/row.relative_path
        actual=digest(path)
        assert actual==row.sha256.lower(), f"W1 raw hash mismatch: {row.relative_path}"
        result[row.relative_path]=actual
    return result


def snapshot_outputs():
    paths=list((ROOT/"reports/tables").glob("*.csv"))+list((ROOT/"reports/figures/w2_eda").glob("*.png"))
    return {p.relative_to(ROOT).as_posix():digest(p) for p in sorted(paths)}


def execute(notebook):
    if sys.platform=="win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    client=NotebookClient(notebook,timeout=600,kernel_name="azure-w2",
                          resources={"metadata":{"path":str(ROOT/"notebooks")}})
    client.execute()
    for cell in notebook.cells:
        if cell.cell_type=="code":
            assert cell.execution_count is not None
            assert all(out.output_type!="error" for out in cell.outputs)
    return notebook


def validate_artifacts():
    tables=ROOT/"reports/tables"
    charts=pd.read_csv(tables/"w2_chart_hypothesis_mapping.csv",dtype={"chart_id":str})
    hypotheses=pd.read_csv(tables/"w2_hypothesis_results.csv")
    assert len(charts)>=15 and charts.chart_id.is_unique
    assert set(charts.category)=={"分布","关联","交叉"}
    assert len(hypotheses)==10 and hypotheses.hypothesis_id.is_unique
    assert int(hypotheses.analyzed.sum())>=5
    assert hypotheses.loc[hypotheses.hypothesis_id.isin(["H1","H2","H4","H10"]),"analyzed"].all()
    for row in charts.itertuples():
        assert all(isinstance(getattr(row,c),str) and getattr(row,c) for c in ["conclusion","action","evidence","limitations"])
        assert (ROOT/row.evidence).is_file()
        with PILImage.open(ROOT/row.path) as image:
            image.verify()
        with PILImage.open(ROOT/row.path) as image:
            assert image.width>1000 and image.height>1000
            assert all(abs(x-300)<1 for x in image.info["dpi"])
    for path in tables.glob("*.csv"):
        frame=pd.read_csv(path)
        if {"n","churned","churn_rate","ci_low","ci_high"}.issubset(frame.columns):
            assert frame.n.gt(0).all() and frame.churned.between(0,frame.n).all()
            assert np.allclose(frame.churned/frame.n,frame.churn_rate,atol=1e-10)
            assert frame.ci_low.le(frame.churn_rate+1e-10).all() and frame.ci_high.ge(frame.churn_rate-1e-10).all()
    for filename in ["w2_contract_rates","w2_tenure_rates","w2_service_count_all","w2_fee_quartile_rates","w2_payment_rates","w2_risk_value_prototype"]:
        frame=pd.read_csv(tables/f"{filename}.csv")
        assert frame.n.sum()==7043 and frame.churned.sum()==1869
    internet=pd.read_csv(tables/"w2_service_count_internet.csv")
    assert internet.n.sum()==5517 and internet.churned.sum()==1756
    return {"figures":len(charts),"analyzed_hypotheses":int(hypotheses.analyzed.sum()),"hypotheses_registered":len(hypotheses),
            "figure_dpi":300,"rate_tables_consistent":True,"primary_partitions_reconcile":True}


def export_report():
    reports=ROOT/"reports"
    sections=[]
    for filename in ["w2_eda_summary.md","w2_methods_and_decisions.md","w2_to_w3_cleaning_recommendations.md"]:
        text=(reports/filename).read_text(encoding="utf-8")
        sections.append(str(markdown2html(text)))
    charts=pd.read_csv(reports/"tables/w2_chart_hypothesis_mapping.csv",dtype={"chart_id":str})
    sections.append("<h1>图表及行动索引</h1>")
    for row in charts.itertuples():
        encoded=base64.b64encode((ROOT/row.path).read_bytes()).decode("ascii")
        sections.append(f'<article><h2>图{row.chart_id} · {html.escape(row.title)} · {row.hypothesis_id}</h2>'
                        f'<img src="data:image/png;base64,{encoded}" alt="{html.escape(row.title)}">'
                        f'<p><strong>结论：</strong>{html.escape(row.conclusion)}</p>'
                        f'<p><strong>下一步：</strong>{html.escape(row.action)}</p>'
                        f'<p class="muted">{html.escape(row.limitations)}</p></article>')
    style="body{font-family:'Microsoft YaHei',sans-serif;max-width:1200px;margin:40px auto;padding:0 30px;color:#20323b;line-height:1.75}h1,h2,h3{color:#176b87}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #ccd6dc;padding:8px;text-align:left}th{background:#edf5f7}img{max-width:100%;height:auto}article{margin:48px 0;border-top:1px solid #ccd6dc}code{background:#edf1f4;overflow-wrap:anywhere}.muted{font-size:13px;color:#5b6570}@media print{article{break-inside:avoid}body{margin:0;max-width:none}}"
    document=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Week2 EDA分析交付报告</title><style>{style}</style></head><body>'+"\n".join(sections)+"</body></html>"
    (reports/"w2_eda_report.html").write_text(document,encoding="utf-8")


def artifact_manifest():
    records=[]
    # Keep the W2 manifest scoped to W2 deliverables after integration.
    paths = [ROOT / "notebooks/02_eda.ipynb", ROOT / "notebooks/02_eda.html",
             ROOT / "src/w2_analysis.py", ROOT / "scripts/run_week2.py",
             ROOT / "requirements_w2.txt"]
    paths += list((ROOT / "reports").glob("w2_*.md"))
    paths += list((ROOT / "reports").glob("w2_*.json"))
    paths += list((ROOT / "reports/tables").glob("w2_*.csv"))
    paths += list((ROOT / "reports/figures/w2_eda").glob("*.png"))
    paths += [ROOT / "reports/w2_eda_report.html", ROOT / "dashboard/README.md",
              ROOT / "dashboard/w2_interactive.html", ROOT / "scripts/build_w2_powerbi.py",
              ROOT / "scripts/build_w2_web_dashboard.py", ROOT / "tests/validate_w2_powerbi_schema.py",
              ROOT / "docs/operations/W2_run_and_delivery.md"]
    paths += [p for p in (ROOT / "dashboard/powerbi").rglob("*")
              if p.is_file() and ".pbi" not in p.parts and p.suffix in {".json", ".pbip", ".pbix", ".pbir", ".pbism", ".bim"}]
    paths += list((ROOT / "screenshots").glob("w2_*.png"))
    paths += list((ROOT / "reports/screenshots").glob("w2_*.png"))
    paths += [ROOT / "reports/environment_recovery.md", ROOT / "reports/environment_smoke.ipynb",
              ROOT / "reports/environment_verification.json", ROOT / "reports/runtime_provenance.json",
              ROOT / "references/project_brief_extracted.txt",
              ROOT / "scripts/launch_kernel.py", ROOT / "scripts/register_kernel.py",
              ROOT / "scripts/recover_cached_python.py", ROOT / "scripts/verify_environment.py",
              ROOT / "scripts/setup_week2_environment.ps1"]
    for path in sorted({p for p in paths if p.is_file()}):
        if path.name=="w2_artifact_manifest.csv":
            continue
        records.append({"path":path.relative_to(ROOT).as_posix(),"bytes":path.stat().st_size,"sha256":digest(path)})
    pd.DataFrame(records).to_csv(ROOT/"reports/w2_artifact_manifest.csv",index=False,encoding="utf-8-sig")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--verify-reproducibility",action="store_true")
    parser.add_argument("--package-only",action="store_true",help="Refresh HTML and manifest after documentation-only edits")
    args=parser.parse_args()
    if args.package_only:
        export_report(); artifact_manifest(); print("Refreshed HTML report and artifact manifest"); return
    (ROOT/"notebooks").mkdir(exist_ok=True)
    raw_before=snapshot_raw()
    print("Executing Week 2 notebook in a fresh kernel...",flush=True)
    notebook=execute(make_notebook())
    nbformat.write(notebook,ROOT/"notebooks/02_eda.ipynb")
    first=snapshot_outputs()
    identical=None
    if args.verify_reproducibility:
        print("Re-executing in a second fresh kernel and comparing CSV/PNG hashes...",flush=True)
        notebook=execute(make_notebook())
        second=snapshot_outputs()
        identical=first==second
        changed=[p for p in first.keys()|second.keys() if first.get(p)!=second.get(p)]
        assert identical, f"Non-reproducible outputs: {changed}"
        nbformat.write(notebook,ROOT/"notebooks/02_eda.ipynb")
    checks=validate_artifacts()
    assert raw_before==snapshot_raw(),"Raw files changed during execution"
    legacy_templates=PROJECT/".venv/share/jupyter/nbconvert/templates"
    exporter=HTMLExporter(template_name="lab",
                          extra_template_basedirs=[str(legacy_templates)] if legacy_templates.is_dir() else [],
                          extra_template_paths=[str(legacy_templates)] if legacy_templates.is_dir() else [])
    html_body,_=exporter.from_notebook_node(notebook)
    (ROOT/"notebooks/02_eda.html").write_text(html_body,encoding="utf-8")
    summary=ROOT/"reports/w2_eda_summary.md"
    recommendations=ROOT/"reports/w2_to_w3_cleaning_recommendations.md"
    assert len(summary.read_text(encoding="utf-8"))>=500
    assert recommendations.is_file()
    export_report()
    verification={"status":"passed","verified_at_utc":datetime.now(timezone.utc).isoformat(),
                  "fresh_kernel_runs":2 if args.verify_reproducibility else 1,
                  "code_cells_executed":sum(c.cell_type=="code" for c in notebook.cells),
                  "all_code_cells_successful":True,"csv_png_hashes_identical":identical,
                  "reproduced_files":len(first) if identical else None,
                  "all_six_raw_files_match_w1_manifest":True,"seed":42,"checks":checks}
    (ROOT/"reports/w2_verification.json").write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding="utf-8")
    artifact_manifest()
    print(json.dumps(verification,ensure_ascii=False,indent=2),flush=True)


if __name__=="__main__":
    main()
