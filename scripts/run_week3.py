"""Run W3 from any working directory; artifacts stay under project-owned folders."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.clean import load_config
from src.data.w3_workflow import run_workflow, digest, dump_json, validate_output_targets


def resolve_path(value):
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def destination(value, kind):
    path = resolve_path(value)
    roots = {"data": [ROOT / "data/processed", ROOT / ".cache"],
             "model": [ROOT / "models", ROOT / ".cache"],
             "reports": [ROOT / "reports", ROOT / ".cache"]}[kind]
    if not any(path.is_relative_to(p) for p in roots):
        raise ValueError(f"{kind} output must be in its project artifact folder or .cache; received {path}")
    # Resolve links before comparison, rejecting redirection into data/raw or code.
    return path


def make_notebook(config, source):
    import nbformat as nbf
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter
    from jupyter_client.kernelspec import KernelSpecManager
    from jupyter_client.manager import KernelManager
    nb = nbf.v4.new_notebook()
    nb.cells = [
        nbf.v4.new_markdown_cell("# W3 数据清洗与预处理\n本 Notebook 从原始数据重新执行清洗与训练内预处理，核验 C01–C10。主表保留未知累计费用；模型矩阵的插补不是补出真实账单。"),
        nbf.v4.new_code_cell("from pathlib import Path\nimport sys, json\nROOT = next(p for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents] if (p / 'src/data/clean.py').is_file() and (p / 'configs/w3_cleaning.json').is_file())\nsys.path.insert(0, str(ROOT))\nimport numpy as np\nimport pandas as pd\nfrom sklearn.model_selection import train_test_split\nfrom src.data.clean import read_raw, TelcoCleaner\nfrom src.data.preprocess import split_xy, build_preprocessor\n"
                             + f"config = json.loads({json.dumps(config, ensure_ascii=False)!r})\nsource = ROOT / {source.relative_to(ROOT).as_posix()!r}\n"
                             + "raw = read_raw(source)\ncleaner = TelcoCleaner(config)\ncleaned = cleaner.fit_transform(raw)\nprint('原始与清洗后:', raw.shape, cleaned.shape)"),
        nbf.v4.new_markdown_cell("## 保留所有客户与标签\n空白累计费用转为 NA，并保留缺失/零年限标记；无互联网类别仍然存在。下面仅显示聚合信息。配置与数据路径对应生成本 Notebook 的那次运行。"),
        nbf.v4.new_code_cell("assert len(raw) == len(cleaned)\nassert raw.customerID.str.strip().tolist() == cleaned.customerID.tolist()\nassert raw.Churn.str.strip().tolist() == cleaned.Churn.tolist()\nassert cleaned.churn_label.sum() == raw.Churn.str.strip().eq('Yes').sum()\nassert cleaned.TotalCharges.isna().sum() == raw.TotalCharges.str.strip().eq('').sum()\nassert cleaned.internet_applicable.sum() == raw.InternetService.str.strip().ne('No').sum()\npd.testing.assert_frame_equal(cleaned, cleaner.transform(cleaned))\ncleaned[['TotalCharges', 'tenure']].isna().sum().to_frame('缺失数')"),
        nbf.v4.new_markdown_cell("## 训练内拟合与编码\n固定种子分层切分仅演示接口。验证集不参与中位数、均值或标准差拟合；这不是 W5 模型评估。"),
        nbf.v4.new_code_cell("X, y, ids = split_xy(cleaned, config)\ntrain, valid = train_test_split(np.arange(len(X)), test_size=config['test_size'], random_state=config['seed'], stratify=y)\npipeline = build_preprocessor(config)\nX_train = pipeline.fit_transform(X.iloc[train])\nX_valid = pipeline.transform(X.iloc[valid])\nassert np.isfinite(X_train).all() and np.isfinite(X_valid).all()\nassert not set(train) & set(valid)\nprint('训练矩阵:', X_train.shape, '验证矩阵:', X_valid.shape)\nprint('X 输入不含ID和标签:', not {'customerID', 'Churn', 'churn_label'} & set(X.columns))"),
        nbf.v4.new_code_cell("num = pipeline.named_steps['columns'].named_transformers_['numeric']\nassert np.allclose(num.named_steps['imputer'].statistics_, X.iloc[train][config['features']['numeric']].median().fillna(0))\npd.DataFrame({'字段': config['features']['numeric'], '训练中位数': num.named_steps['imputer'].statistics_, '训练缩放均值': num.named_steps['scaler'].mean_})"),
        nbf.v4.new_markdown_cell("## 累计费用差异诊断\n历史价格、优惠和账单日期不可见。累计费用与当前月费乘以年限的差异只用于检查，不被当作修复目标。"),
        nbf.v4.new_code_cell("difference = cleaned.TotalCharges - cleaned.tenure * cleaned.MonthlyCharges\ndifference.describe(percentiles=[.01, .25, .5, .75, .99]).to_frame('累计费用差异')"),
        nbf.v4.new_markdown_cell("## 交付与限制\n清洗规则见 `reports/w3_cleaning_rules.md`；12 项真实时间特征设计见 `reports/feature_engineering_design_v1.md`。当前没有事件时间数据，实际时序计算为零；49列仅是 W3 接口示例，不代替 W4 的最终特征设计。详细机器核验见 `reports/w3_verification.json`。"),
    ]
    nb.metadata.kernelspec = {"display_name": "Python (Azure W3)", "language": "python", "name": "azure-w3"}
    kernel_dir = Path(sys.prefix) / "share/jupyter/kernels/azure-w3"
    dump_json(kernel_dir / "kernel.json", {"argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                                            "display_name": "Python (Azure W3)", "language": "python"})
    km = KernelManager(kernel_name="azure-w3", kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernel_dir.parent)]))
    nb_dir = ROOT / "notebooks"
    nb_dir.mkdir(exist_ok=True)
    client = NotebookClient(nb, km=km, timeout=180, resources={"metadata": {"path": str(nb_dir)}})
    client.execute()
    code_cells = [cell for cell in nb.cells if cell.cell_type == "code"]
    assert all(cell.execution_count is not None and all(o.output_type != "error" for o in cell.outputs) for cell in code_cells)
    nbf.write(nb, nb_dir / "03_cleaning.ipynb")
    html, _ = HTMLExporter(template_name="lab").from_notebook_node(nb)
    (nb_dir / "03_cleaning.html").write_text(html, encoding="utf-8")
    return {"status": "passed", "fresh_kernel": True, "code_cells_executed": len(code_cells), "notebook": "notebooks/03_cleaning.ipynb"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/w3_cleaning.json")
    parser.add_argument("--input", help="Versioned source; must match config expected_sha256")
    parser.add_argument("--output-dir")
    parser.add_argument("--model-dir")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--test-size", type=float)
    parser.add_argument("--verify-reproducibility", action="store_true")
    parser.add_argument("--skip-notebook", action="store_true", help="Core dependency / child-process verification only")
    args = parser.parse_args()
    config_path = resolve_path(args.config)
    config = load_config(config_path)
    if args.seed is not None:
        config["seed"] = args.seed
    if args.test_size is not None:
        config["test_size"] = args.test_size
    source = resolve_path(args.input or config["input_path"])
    if not source.is_relative_to(ROOT):
        raise ValueError("Versioned input must be inside the project; external input paths are not supported")
    output_dir = destination(args.output_dir or config["output_dir"], "data")
    model_dir = destination(args.model_dir or config["model_dir"], "model")
    reports_dir = destination(args.reports_dir, "reports")
    destinations = [output_dir, model_dir, reports_dir]
    if any(source.is_relative_to(p) for p in destinations):
        raise ValueError("Input file must not be inside an output folder")
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(destinations) for b in destinations[i+1:]):
        raise ValueError("Data/model/report output folders must be distinct and non-overlapping")
    if not args.skip_notebook:
        validate_output_targets(ROOT / "notebooks", [ROOT / "notebooks/03_cleaning.ipynb", ROOT / "notebooks/03_cleaning.html"])
    summary = run_workflow(config, source, output_dir, model_dir, reports_dir)
    summary["config_file_sha256"] = digest(config_path)
    reproducibility = {"requested": args.verify_reproducibility, "status": "not_requested"}
    if args.verify_reproducibility:
        # Keep evidence separate from primary delivery and invoke a completely new process.
        run_root = ROOT / ".cache/w3_reproducibility"
        run_root.mkdir(parents=True, exist_ok=True)
        second = Path(tempfile.mkdtemp(prefix="run-", dir=run_root))
        command = [sys.executable, str(Path(__file__).resolve()), "--config", str(config_path), "--input", str(source),
                   "--output-dir", str(second / "data"), "--model-dir", str(second / "model"), "--reports-dir", str(second / "reports"),
                   "--seed", str(config["seed"]), "--test-size", str(config["test_size"]), "--skip-notebook"]
        subprocess.run(command, cwd=str(ROOT.parent), check=True)
        result = json.loads((second / "reports/w3_run_metadata.json").read_text(encoding="utf-8"))
        if summary["business_hashes"] != result["business_hashes"]:
            raise AssertionError("Reproducibility failed: business data or aggregate evidence differs")
        reproducibility = {"requested": True, "status": "passed", "fresh_process_runs": 2,
                           "non_project_working_directory": True, "files_compared": len(summary["business_hashes"]),
                           "business_hashes_identical": True}
    notebook = {"status": "skipped", "reason": "--skip-notebook requested"} if args.skip_notebook else make_notebook(config, source)
    verification = {k: summary[k] for k in ("status", "rows", "columns", "total_charges_missing", "encoded_columns", "quality_rules", "quality_rules_failed",
                                           "train_only_statistics_verified", "id_label_excluded", "idempotent", "raw_files_unchanged", "serialized_transform_identical")}
    verification.update({"verified_at_utc": datetime.now(timezone.utc).isoformat(), "reproducibility": reproducibility,
                         "notebook": notebook, "source_sha256": summary["source_sha256"], "limitations": summary["limits"]})
    dump_json(reports_dir / "w3_run_metadata.json", summary)
    dump_json(reports_dir / "w3_verification.json", verification)
    print(json.dumps({"status": "passed", "clean_shape": [summary["rows"], summary["columns"]],
                      "encoded_columns": summary["encoded_columns"], "reproducibility": reproducibility["status"], "notebook": notebook["status"]}))


if __name__ == "__main__":
    main()
