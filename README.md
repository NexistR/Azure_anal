# Azure 客户流失分析项目（8 周）

本仓库用于完成公开 Telco Customer Churn 代理数据上的客户流失分析。数据不是 Microsoft Azure 内部客户数据；项目结论不得直接外推为 Azure 真实客户结论。

## 当前交付状态与统一入口

W2 的 EDA 已通过复现验收，2026-09-13 补充原生 Power BI 项目和离线交互仪表板。代码、Notebook、图表、表格及分析报告均在本仓库；相邻 `week2_sub/` 保留完成报告和用户随后要求的两份零基础说明。原始要求中的地区、行业和真实订阅类型筛选仍缺真实数据，详见验收审计。

- [W2 完成报告](../week2_sub/W2完成报告_2026-09-09.md)：验收结果、结论与后续事项。
- [W2 运行与交付说明](docs/operations/W2_run_and_delivery.md)：统一运行命令、产物位置和迁移后的路径约定。
- [Power BI 仪表板](dashboard/powerbi/W2_Churn.pbip)：用 Power BI Desktop 打开，首次提示无数据时点击“刷新”；具体操作见 [仪表板使用说明](dashboard/README.md)。
- [离线交互仪表板](dashboard/w2_interactive.html)：用浏览器打开，支持筛选与 15 个交互图表。
- [初步流失模式分析报告](reports/w2_eda_summary.md)及[完整图文版](reports/w2_eda_report.html)：主要结论、假设验证及限制。
- [W2 逐项验收审计](reports/w2_requirements_audit.md)：要求来源、证据及缺失字段。
- [W2 零基础说明](../week2_sub/W2零基础说明.md)及[项目结构说明](../week2_sub/项目结构与构成说明.md)。
- 运行环境：`.venv/Scripts/python.exe`。W2 环境入口：`scripts/setup_week2_environment.ps1`；分析入口：`scripts/run_week2.py`。

## 项目范围

项目只执行 W1–W8：

1. W1：业务理解、数据合同、字段字典、质量审计和路线图。
2. W2：问题导向 EDA 与假设验证。
3. W3：可复用数据清洗 Pipeline。
4. W4：特征工程与泄漏审查。
5. W5：基线模型、不平衡处理和完整指标。
6. W6：高级模型、调参与细分稳定性。
7. W7：模型解释、概率校准和风险评分。
8. W8：价值代理、客户分层/分群、风险-价值矩阵和项目收口。

正式 CLV、留存策略实验、A/B/uplift/因果效果、策略组合 ROI 以及原 12 周计划的 W9–W12 均不属于本项目交付范围。

## 核心说明文件

- [`docs/planning/第一周任务总体框架与推进步骤.md`](docs/planning/第一周任务总体框架与推进步骤.md)：可编辑的项目总体框架、第一周逐日步骤和八周路线图。
- [`docs/planning/第一周任务总体框架与推进步骤.pdf`](docs/planning/第一周任务总体框架与推进步骤.pdf)：与 Markdown 对应的阅读/提交版本。
- [`docs/operations/当前工作进度与续作交接.md`](docs/operations/当前工作进度与续作交接.md)：环境状态和续作边界。
- [`docs/operations/环境安装与配置说明.md`](docs/operations/环境安装与配置说明.md)：本地环境启动与验证方法。
- [`docs/project/`](docs/project/)：项目介绍、零基础指南和原始 brief。
- [`docs/archive/`](docs/archive/)：历史交付版本，仅供追溯。

## 目录结构

```text
configs/              路径、随机种子和运行配置说明
data/raw/             原始数据，只读；数据文件不提交 Git
data/processed/       清洗和特征输出；数据文件不提交 Git
notebooks/            按周编号的探索、建模和解释 Notebook
src/data/             数据读取、质量检查和清洗
src/features/         特征工程
src/models/           模型训练、评估和预测
src/segmentation/     W8 分层、分群和风险-价值规则
models/               本地模型产物；模型文件不提交 Git
reports/figures/      报告图表
reports/tables/       质量、指标、评分和分群表
dashboard/            原生 Power BI 项目、离线交互 HTML 和使用说明
tests/                数据质量规则与代码测试
scripts/              环境和任务运行入口
tools/                环境检查与文档渲染工具
docs/project/         项目介绍、学习指南和原始 brief
docs/planning/        周计划、路线图和执行框架
docs/operations/      环境说明、交接记录和运行约定
docs/archive/         历史交付文件
```

各目录的 `README.md` 说明预期输入、输出和命名规则。Python 业务代码放入 `src/`，Notebook 只负责探索、编排和展示，不复制核心逻辑。

## 当前状态与下一步

- 本地分析环境已经安装和验证，无需重复安装。
- 基础目录结构已经建立。
- 三个 Kaggle 数据集已下载并登记：Telco、Customer Support Tickets、SaaS；来源、许可、文件大小和 SHA-256 见 `reports/tables/data_manifest.csv`。
- Telco 是主练习数据；Support Tickets 与 SaaS 没有可验证的统一客户键，后续默认分开分析。
- Azure 登录、Power BI 在线发布和 GitHub 远程连接不是 W1 的硬依赖。

W2 已完成 20 张静态图、7 项实际假设分析、Notebook 两次完整重跑，以及原生 Power BI 与 HTML 交互展示。下一阶段按 [W3 清洗建议](reports/w2_to_w3_cleaning_recommendations.md)实现清洗 Pipeline；W2 缺失的真实地区、行业与订阅维度保留为待补数据项。

## 数据与安全规则

- `data/raw/` 保持只读，清洗输出写入 `data/processed/`。
- 原始/处理数据、模型二进制、密钥、连接字符串和个人信息不得提交 Git。
- 无稳定共同客户 ID 和一致时间口径时，不合并 Telco、工单或 SaaS 数据。
- Telco 缺完整快照时间时，不声称完成严格时间切分。
- `MonthlyCharges`、`TotalCharges` 等只能作为透明价值代理，不称正式 CLV。
