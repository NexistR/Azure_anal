# Notebook 目录

## 当前 W2 状态

`02_eda.ipynb` 与对应的 `02_eda.html` 已完成并迁移至本目录。请从项目根目录使用 `.venv/Scripts/python.exe`，由 `scripts/run_week2.py` 统一执行和验证；不要再使用 `week2_sub` 下的旧路径。

Notebook 按执行顺序编号，建议命名：

- `01_data_profile.ipynb`：W1 数据概况与质量审计。
- `02_eda.ipynb`：W2 EDA 与假设验证。
- `03_baseline.ipynb`：W5 基线模型结果展示。
- `04_explainability.ipynb`：W7 模型解释和风险评分。
- `05_segmentation.ipynb`：W8 分层/分群和风险-价值矩阵。

可复用读取、清洗、特征和模型逻辑应放入 `src/`；Notebook 负责探索、编排、图表和结论。
