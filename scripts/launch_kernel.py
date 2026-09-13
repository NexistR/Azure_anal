"""Project-local IPython kernel entry point with the legacy plotting adapter.

Matplotlib 3.8 imports IPython.core.pylabtools.backend2gui. IPython 9.16 removed
the public alias while retaining the same mapping under its deprecated name.
Restore that alias only in this kernel process; installed packages stay intact.
"""
from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path

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

from packaging.version import Version
if Version(importlib.metadata.version("matplotlib")) < Version("3.9"):
    import IPython.core.pylabtools as pylabtools
    if not hasattr(pylabtools, "backend2gui"):
        pylabtools.backend2gui = pylabtools._deprecated_backend2gui.copy()

from ipykernel.kernelapp import IPKernelApp

if __name__ == "__main__":
    IPKernelApp.launch_instance()
