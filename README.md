# 客户流失预测与价值分层

基于公开 Telco 代理数据的冻结模型应用工程，保留严格清洗、特征变换、批量推理、SHAP/LIME 解释及客户分群。研究结论、性能对照和最终论文随仓库提供。本副本整理于 2026-10-23；原始研究目录及实验记录另行保留。

## 成果与范围

| 项目 | 已完成结果 |
|---|---|
| 模型 | 冻结 XGBoost，22 个输入、64 个逻辑字段、111 个编码列，阈值 0.30 |
| 历史验证 | AUC 0.852193，流失正类 F1 0.656160；验证集曾多次复用 |
| 运行性能 | 历史 1,056 行批量推理 P50：52.26 → 10.14 ms，5.15 倍；分阶段均值比较为 4.90 倍 |
| 客户分群 | 训练内选择的 KMeans（3 簇）及 DBSCAN 对照，冻结后应用验证集 |
| 价值分层 | 训练月费中位数约 70.575 与固定风险阈值构建四象限 |

性能目标 AUC > 0.88、正类 F1 > 0.80 及至少三个稳定监督细分未达到（稳定细分为 2/10，不等同于聚类簇数）。数据不是真实 Azure 内部数据，月费代理不代表 CLV。整理工作未重新调优或改变预测结论。

## 快速开始

使用 Python 3.12，从仓库根目录运行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/score_risk.py --input examples/probabilities.csv --output outputs/risk_demo.csv
python -m unittest discover -s tests -v
```

Linux/macOS 激活命令为 `source .venv/bin/activate`。示例均为人工构造数据，仅演示接口，不用于性能或业务结论。

本机整理副本包含 Git 忽略的本地模型；GitHub/ZIP 副本需要从可信原工程恢复工件后才能预测：

```powershell
python scripts/restore_local_artifacts.py --source "<原项目目录>"
python scripts/predict.py --input examples/predictors.csv --output outputs/predictions.csv --batch-size 4096 --threads 2
python scripts/score_risk.py --input outputs/predictions.csv --output outputs/risk.csv
```

已有输出文件不会被覆盖。输入格式见 [输入规范](docs/input_schema.md)，本地模型策略见 [模型说明](models/README.md)。

## 工程结构

```text
configs/             输入合同、固定规则、模型指纹
src/data/            清洗及严格数值解析
src/features/        原特征构造与序列化兼容类
src/models/w7/       冻结推理、风险分层和可选解释
src/segmentation/    分群及月费风险分析
scripts/             推理、分层、工件恢复入口
tests/               合成数据合同测试与可选模型回归测试
examples/            不含真实客户的最小输入
docs/                论文、历史方法对照、接口文档
reports/results/     聚合研究结果
reports/cleanup/     本次整理与核验记录
models/, data/       由 Git 忽略的本地资产
```

历史调参、深度学习试验、环境恢复、周报封存与文档渲染脚本未纳入运行工程。源码中的公开 API、sklearn 协议方法及历史序列化类不按“当前 CLI 未调用”判为死代码。原模型文件和固定决策规则保持不变。

## 开发与验证

```powershell
python -m pip install -r requirements/dev.txt
python -m ruff check .
python -m compileall -q src scripts tests
python -m unittest discover -s tests -v
$env:CHURN_RUNTIME_MODEL = (Resolve-Path models/w7/churn_runtime.zip).Path
python -m unittest discover -s tests -v
```

默认测试不依赖原始数据或模型；环境变量启用额外的冻结推理与 CLI 测试。GitHub Actions 配置为 Python 3.12、Windows/Linux 的默认检查；远程执行结果以实际 Actions 记录为准。

解释分析另装 `python -m pip install -r requirements/explain.txt`，用法见 [分析 API](docs/api.md)。依赖版本沿用已核验环境，未混入历史研究所需的 PyTorch、TabPFN、PySpark、Java 或 Notebook 环境。

## 文档与成果

- [最终论文](docs/final_report.md) · [Word](docs/final_report.docx) · [PDF](docs/final_report.pdf)
- [历史模型性能与尝试方法](docs/model_history.md)
- [聚合结果索引](reports/results/README.md)
- [工程整理与验证报告](reports/cleanup/README.md)
- [数据来源与研究边界](data/README.md)

## 上传 GitHub

本机整理目录已初始化独立 Git 仓库，不包含原项目 Git 历史，尚未提交或连接远程仓库。ZIP 解压目录需先执行 `git init -b main`。上传前执行 `git status --short --ignored` 检查列表；`data/`、拟合模型、运行输出、环境和缓存已忽略。然后提交代码、设置自己的远程地址并推送，无需复制原目录的 `.git`。

公开发布 ZIP 只包含可跟踪文件，不含 `.git` 和本地模型。模型恢复脚本不下载第三方文件；没有原模型工件时，仓库仍可执行合成接口测试和概率分层示例。未替原作者指定新的开源许可证；第三方数据和软件遵循各自许可。
