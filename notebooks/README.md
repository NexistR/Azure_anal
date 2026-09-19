# Notebook 目录

## 当前 W3 入口

[03_cleaning.ipynb](03_cleaning.ipynb) 与 [03_cleaning.html](03_cleaning.html) 展示原始读取、25 列清洗主表、训练内插补/编码、幂等检查和费用差异诊断。5 个代码单元在新内核执行，状态记录于 [w3_verification.json](../reports/w3_verification.json)。Notebook 只展示汇总信息，不输出客户编号明细。

在项目根目录运行以下命令生成并执行 Notebook、导出 HTML：

```powershell
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --verify-reproducibility
```

W3 运行器注册当前解释器的局部 `azure-w3` 内核。核心依赖见 [requirements_w3.txt](../requirements_w3.txt)，Notebook 可选依赖见 [requirements-w3-notebook.txt](../requirements-w3-notebook.txt)。仅运行核心清洗时加 `--skip-notebook`；此时不应把 Notebook 标为本次已重跑。

Notebook 会嵌入生成它的那次实际配置与输入路径，包括自定义的种子和切分参数；输出始终位于项目 `notebooks/`。做独立输出实验时可加 `--skip-notebook` 避免更新主交付Notebook，以该次独立目录里的JSON/CSV为准；如果执行了Notebook，应核对其内嵌配置对应哪次运行。

## W2 入口

`02_eda.ipynb` 与对应的 `02_eda.html` 已完成并迁移至本目录。请从项目根目录使用 `.venv/Scripts/python.exe`，由 `scripts/run_week2.py` 统一执行和验证；不要再使用 `week2_sub` 下的旧路径。

Notebook 按执行顺序编号，建议命名：

- `01_data_profile.ipynb`：W1 数据概况与质量审计。
- `02_eda.ipynb`：W2 EDA 与假设验证。
- `03_cleaning.ipynb`：W3 清洗与预处理接口。
- `04_features.ipynb`：W4 特征工程（计划）。
- `05_baseline_models.ipynb`：W5 基线模型结果展示（计划）。
- `06_advanced_models.ipynb`：W6 高级模型（计划）。
- `07_model_interpretation.ipynb`：W7 模型解释和风险评分（计划）。
- `08_segmentation_matrix.ipynb`：W8 分层/分群和风险-价值矩阵（计划）。

可复用读取、清洗、特征和模型逻辑应放入 `src/`；Notebook 负责探索、编排、图表和结论。
