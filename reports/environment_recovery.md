# W2 运行环境恢复记录

日期：2026-09-13（Asia/Hong_Kong）

本记录说明如何在整合后的 `azure-churn-clv` 项目中恢复 Python 3.12.9，并让 W2 Notebook 使用项目自己的 `azure-w2` 内核。

## 发现的故障

1. 旧 `.venv/pyvenv.cfg` 的 `home` 指向已不存在的 `G:\python312`，因此 `.venv/Scripts/python.exe` 无法启动。
2. 系统默认 `python` 是 Python 3.9，不能直接替代 W2 所需的 Python 3.12 环境。
3. IPython 9 删除了 `backend2gui` 公共别名，而 Matplotlib 3.8 的 Notebook 绘图仍会读取它，普通导入检查无法发现这一点。

## 恢复方案与文件

- `scripts/recover_cached_python.py` 使用 Windows Installer 只读 API，从本机 Package Cache 的 Python 3.12.9 `core.msi`、`exe.msi` 和 `lib.msi` 提取运行时到 `.runtime/python312/`。不运行 MSI 安装，不修改注册表。
- `scripts/setup_week2_environment.ps1` 以该运行时重建项目 `.venv` 配置，保留现有依赖；旧的 `week1_dependencies.pth` 保持为空，避免把虚拟环境目录再次指向自身。
- `scripts/launch_kernel.py` 只在 `azure-w2` 内核进程中恢复 Matplotlib 所需的兼容别名，不修改已安装的包。
- `scripts/register_kernel.py` 将 `azure-w2` kernelspec 写入 `.venv/share/jupyter/kernels/azure-w2/`。
- `scripts/verify_environment.py` 启动全新内核，检查科学计算、Agg 绘图、内嵌 PNG 以及解释器路径一致性，并写入 `reports/environment_verification.json`。

## 使用方法

在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_week2_environment.ps1
& .\.venv\Scripts\python.exe .\scripts\run_week2.py --verify-reproducibility
```

在 VS Code 中选择内核 **Python 3.12 (Azure W2)**。迁移项目目录后，应再次运行 setup 脚本，以更新虚拟环境和 kernelspec 中的绝对路径。

如果本机缓存不存在 Python 3.12.9 MSI，可用 `-PythonExe` 显式指定 Python 3.12 解释器；脚本不会自动下载文件。

## 验证结果

2026-09-13 验证通过：Python 3.12.9，`azure-w2` 独立内核可启动；NumPy、pandas、SciPy、Matplotlib、seaborn、Jupyter 依赖均可导入；Agg 和 `%matplotlib inline` 均能生成图像。完整版本和路径见 `environment_verification.json`。
