# 原始数据

本目录保存经许可确认的原始数据文件。数据文件被 Git 忽略；仅本说明文件纳入项目结构。

要求：

- 下载后立即登记来源 URL、发布者、许可、下载日期、文件大小和 SHA-256。
- 保持原文件只读，不在本目录覆盖或清洗数据。
- Telco 数据必须标注为公开代理/教学数据，不得称为 Azure 内部数据。

## 已下载数据

| 子目录 | 文件 | 用途 | 许可 |
| --- | --- | --- | --- |
| `telco_customer_churn/` | `WA_Fn-UseC_-Telco-Customer-Churn.csv` | 主练习数据；客户级 Churn 标签和订阅画像（7,043 行、21 列） | Data files © Original Authors |
| `customer_support_tickets/` | `customer_support_tickets.csv` | 客服体验探索（8,469 行、17 列） | CC0: Public Domain |
| `saas_customer_churn/` | `saas_churn_rate_dataset.xlsx` | SaaS 行业基准对比（5 行、4 列汇总表） | CC0: Public Domain |

三个数据集没有统一客户 ID、时间口径和标签定义，默认分开分析，不按行或姓名合并。Telco 是本项目的主要代理数据；Support Tickets 和 SaaS 仅作为补充研究材料。

详细来源、下载日期、文件大小和 SHA-256 见 [`reports/tables/data_manifest.csv`](../../reports/tables/data_manifest.csv)。
