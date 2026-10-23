# 数据说明

本目录用于本地输入，除本说明外均被 Git 忽略。仓库只提供 `examples/` 中人工编造的接口示例。

原项目的数据登记如下；本副本未重新下载数据，也未重新确认网站当前许可。

| 数据源 | 原项目规模 | 研究用途 | 原登记许可 |
|---|---:|---|---|
| [Telco Customer Churn](https://www.kaggle.com/datasets/blastchar/telco-customer-churn) | 7,043 行、21 列 | 客户流失监督建模 | Data files © Original Authors |
| [Customer Support Tickets](https://www.kaggle.com/datasets/suraj520/customer-support-ticket-dataset) | 8,469 行、17 列 | 客服体验探索 | CC0 |
| SaaS Churn Rate Statistics | 10 个工作表、50 条汇总记录 | 行业基准比较 | CC0 |

三源缺少经验证的共同客户标识及预测前时间信息，未拼接成一张监督学习表。Telco 为公开教学代理数据，不代表 Azure 内部客户。固定划分为训练 4,930、验证 1,056、历史测试 1,057；该划分不是时间外推检验。

清洗与推理接口见 [输入规范](../docs/input_schema.md)。真实客户数据、含明细的 Notebook/HTML/Power BI 文件及训练缓存均不随本副本发布。
