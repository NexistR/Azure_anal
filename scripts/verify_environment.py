"""Verify scientific imports and execute a fresh project-local Jupyter kernel."""
from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for name, folder in {
    "JUPYTER_CONFIG_DIR": "jupyter_config",
    "JUPYTER_DATA_DIR": "jupyter_data",
    "JUPYTER_RUNTIME_DIR": "jupyter_runtime",
    "IPYTHONDIR": "ipython",
    "MPLCONFIGDIR": "matplotlib",
}.items():
    path = ROOT / ".cache" / folder
    path.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(path)

import matplotlib
matplotlib.use("Agg")
import numpy
import pandas
import scipy
import seaborn
import nbformat
from nbclient import NotebookClient


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(
        "import sys, json, pandas as pd, numpy as np, scipy.stats as stats\n"
        "import matplotlib; matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "assert abs(pd.Series([1, 2, 3]).mean() - 2.0) < 1e-12\n"
        "assert abs(stats.norm.cdf(0) - 0.5) < 1e-12\n"
        "fig, ax = plt.subplots(); ax.plot([1, 2], [3, 4]); fig.canvas.draw(); plt.close(fig)\n"
        "print(json.dumps({'status': 'w2_kernel_ok', 'python': sys.executable}))"
    ), nbformat.v4.new_code_cell(
        "%matplotlib inline\n"
        "fig, ax = plt.subplots(); ax.plot([1, 2], [3, 4]); plt.show()"
    )])
    notebook.metadata.kernelspec = {
        "name": "azure-w2", "display_name": "Python 3.12 (Azure W2)", "language": "python"
    }
    NotebookClient(notebook, timeout=120, kernel_name="azure-w2",
                   resources={"metadata": {"path": str(ROOT)}}).execute()
    streams = "".join(output.get("text", "") for output in notebook.cells[0].outputs
                      if output.output_type == "stream")
    payload = json.loads(next(line for line in streams.splitlines() if '"status"' in line))
    assert payload["status"] == "w2_kernel_ok"
    assert Path(payload["python"]).resolve() == Path(sys.executable).resolve()
    assert any("image/png" in output.get("data", {}) for output in notebook.cells[1].outputs)
    names = ["numpy", "pandas", "scipy", "matplotlib", "seaborn", "nbformat",
             "nbclient", "nbconvert", "ipykernel", "jupyter-client", "jupyter-core",
             "pyzmq", "traitlets", "openpyxl", "ipython", "matplotlib-inline"]
    report = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "base_prefix": sys.base_prefix,
        "kernel": "azure-w2",
        "fresh_kernel": payload,
        "checks": ["scientific_imports", "pandas_mean", "scipy_normal_cdf",
                   "matplotlib_agg_render", "fresh_jupyter_kernel", "kernel_interpreter_matches",
                   "matplotlib_inline_png"],
        "compatibility_adapter": "scripts/launch_kernel.py restores the IPython backend2gui alias for Matplotlib < 3.9",
        "versions": {name: importlib.metadata.version(name) for name in names},
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "environment_verification.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    nbformat.write(notebook, ROOT / "reports" / "environment_smoke.ipynb")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
