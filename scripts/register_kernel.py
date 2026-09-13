"""Write a kernelspec under this virtual environment; no user-level install."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
kernel_dir = Path(sys.prefix) / "share" / "jupyter" / "kernels" / "azure-w2"
kernel_dir.mkdir(parents=True, exist_ok=True)
spec = {
    "argv": [sys.executable, str(ROOT / "scripts" / "launch_kernel.py"),
             "-f", "{connection_file}"],
    "display_name": "Python 3.12 (Azure W2)",
    "language": "python",
    "metadata": {"debugger": True},
}
(kernel_dir / "kernel.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
print(f"Registered project-local azure-w2 kernel: {kernel_dir}")
