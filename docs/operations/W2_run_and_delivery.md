# W2 运行与交付说明

更新时间：2026-09-13。所有 W2 可执行文件、Notebook、数据、图表和分析报告已整合到 `azure-churn-clv/`。相邻 `week2_sub/` 保存完成报告及用户随后要求的两份零基础说明。

## 直接查看交付物

| 想看什么 | 打开什么 |
|---|---|
| 原生 Power BI 交互报告 | [dashboard/powerbi/W2_Churn.pbip](../../dashboard/powerbi/W2_Churn.pbip)，用 Power BI Desktop 打开 |
| 浏览器交互预览 | [dashboard/w2_interactive.html](../../dashboard/w2_interactive.html)，双击打开 |
| 初步流失模式分析报告 | [w2_eda_summary.md](../../reports/w2_eda_summary.md)；含全部静态图的[完整 HTML](../../reports/w2_eda_report.html) |
| 代码与运行输出 | [02_eda.ipynb](../../notebooks/02_eda.ipynb)；[Notebook HTML](../../notebooks/02_eda.html) |
| 图表及证据 | [20 张 PNG](../../reports/figures/w2_eda/)；[图表映射 CSV](../../reports/tables/w2_chart_hypothesis_mapping.csv) |
| 假设与统计检验 | [十项假设 CSV](../../reports/tables/w2_hypothesis_results.csv)；[统计检验 CSV](../../reports/tables/w2_statistical_tests.csv) |
| 下一周怎么做 | [10 条 W3 清洗建议](../../reports/w2_to_w3_cleaning_recommendations.md) |
| 要求是否满足 | [逐项验收审计](../../reports/w2_requirements_audit.md)；[完成报告](../../../week2_sub/W2完成报告_2026-09-09.md) |

## Power BI 怎么进入

1. 在文件管理器进入 `azure-churn-clv/dashboard/powerbi/`，双击 `W2_Churn.pbip`。如果没有文件关联，启动 Power BI Desktop，用“文件 → 打开”选择它。
2. `.pbip` 是 Power BI 原生项目格式。旁边的 `W2_Churn.Report/` 是页面定义，`W2_Churn.SemanticModel/` 是字段、数据快照和公式，搬动时保留整个 `powerbi/` 目录。
3. 如果出现“某些表包含不完整数据或没有数据”，点击“立即刷新”，或“主页 → 刷新”。等待完成后，总览应显示 **7,043 人、流失 1,869 人、26.54%**。
4. 从底部选择总览、增值服务、客户画像、组合模式四个页面。上方五个筛选器可以联合选择；点击切片器的清除图标恢复全部。页内筛选影响当前页，请逐页确认选择状态。
5. 例如合同类型选 `Month-to-month`，总览应变为 **3,875 人、流失 1,655 人、42.71%**。这是所选人群的历史观察比例。

本地查看不需要 Azure 登录或 Power BI 在线发布。若旧版 Desktop 不识别 PBIP/PBIR，请使用支持项目格式的新版 Desktop；本机已安装并验证版本为 `2.157.879.0`。

## 从头重跑

以下命令在 `azure-churn-clv/` 根目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_week2_environment.ps1
& .\.venv\Scripts\python.exe .\scripts\run_week2.py --verify-reproducibility
& .\.venv\Scripts\python.exe .\scripts\build_w2_powerbi.py
& .\.venv\Scripts\python.exe .\scripts\build_w2_web_dashboard.py
```

分析使用 Python 3.12、项目专用 `azure-w2` 内核和固定 seed=42，版本记录于 `requirements_w2.txt`。Notebook、20 张 PNG 和 28 张 W2 CSV 的两次全新内核验收结果见 [w2_verification.json](../../reports/w2_verification.json)。

**重建 Power BI 前先关闭当前报告并保存自己的改动。** 生成脚本会重写生成的页面和模型；手工调整的布局请另外保存副本。之后重新打开项目并刷新。快照内嵌在模型定义中，没有依赖某台电脑的 CSV 绝对路径；Power BI 的“刷新”加载当前快照。原始数据更新后，需要重新运行构建脚本才能更新快照，单点“刷新”不会重新执行 Python。

## 地区、行业和真实订阅类型缺口

当前 Telco 数据只有电信合同、服务及人口特征，没有地区、行业或 Azure 订阅类型，不能由现有字段推断。`Contract` 仅是合同类型代理。原始验收中的三个真实维度尚未完成；五个现有筛选器不能算作这项要求通过。

如得到与 Telco 客户一一对应的真实映射 CSV，字段必须为 `customerID,region,industry,subscription_type`，客户编号唯一、覆盖全部 7,043 位客户且字段非空。可执行：

```powershell
& .\.venv\Scripts\python.exe .\scripts\build_w2_powerbi.py --customer-dimensions .\data\raw\customer_dimensions.csv
```

不要使用另一个无共同客户键的数据集拼接地区或行业。当前 HTML 预览使用同一 Telco 代理数据，仍只有五个现有筛选器。

## 验证记录与边界

- [Power BI 结构校验](../../reports/w2_powerbi_verification.json)：官方 schema、页面、视觉对象及字段引用。
- [Power BI 快照对账](../../reports/w2_powerbi_data_verification.json)：7,043 行共有原始字段逐行一致、隐藏年限顺序列正确、互联网客户人数与平均月费对账。
- [Power BI 实际运行核验](../../reports/w2_powerbi_runtime_verification.json)：Desktop 内模型 DAX 查询及筛选结果。
- [HTML 浏览器验证](../../reports/w2_web_dashboard_verification.json)：15 图渲染、筛选、空结果提示。

数据为公开 Telco 代理样本，不代表 Azure 真实客户。W2 描述横截面关联，月费不是正式 CLV，观察流失率不是未来预测概率。环境目录 `.venv`、`.runtime`、`.cache`、Power BI 的 `.pbi` 本地缓存不属于交付源码；数据快照是本地分析产物，不应随意提交到公开 Git 仓库。
