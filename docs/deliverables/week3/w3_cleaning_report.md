# W3 数据清洗前后对比报告

本报告由 `scripts/run_week3.py` 随本次运行自动生成。运行时间（UTC）：2026-09-16T09:05:48.576985+00:00；规则版本：`w3-telco-cleaning-v1.0.0`。

## 1. 本次实际结果

原始 Telco 的 7,043 位客户全部保留，生成 25 列清洗主表。流失 1,869 人、未流失 5,174 人，客户顺序、编号与标签对应关系不变。主表保留 11 个未知累计费用，并添加明确缺失标记；模型矩阵经过训练内插补后，缺失和无穷值为 0。

这批数据通过 46 条已实现的质量检查，失败数 0。其中已知缺失和零年限边界属于“保留并说明”，不是偷偷删除后宣称所有问题不存在。数据源为公开教学代理，结论不等于 Azure 真实客户结论。

## 2. 清洗前后对账

| metric | before | after | policy |
| --- | --- | --- | --- |
| rows | 7043 | 7043 | preserve |
| columns | 21 | 25 | add 4 documented fields |
| unique_customer_ids | 7043 | 7043 | preserve |
| churn_yes | 1869 | 1869 | preserve |
| churn_no | 5174 | 5174 | preserve |
| total_charges_blank | 11 | 0 | blank converted to NA |
| total_charges_explicit_na | 0 | 11 | preserve unknown meaning |
| total_charges_semantic_missing | 11 | 11 | preserve |
| total_charges_nonempty_parse_failure | 0 | 0 | strict conversion rejects invalid tokens |
| zero_tenure | 11 | 11 | preserve |
| no_internet | 1526 | 1526 | preserve |
| internet_customers | 5517 | 5517 | preserve |
| monthly_charges_iqr_outliers | 0 | 0 | diagnose, no winsorization |
| dropped_rows | 0 | 0 | no deletion |

原 CSV 读取时所有列暂存为字符串，因此累计费用空白在读取层不是 pandas NA。清洗将其改成显式 NA；信息的未知数量没有增加，也没有被虚构补全。没有删除行、去重删人、缩尾或修改已知累计金额。

逐字段类型和缺失见 [字段审计](../../../reports/tables/w3_field_audit.csv)，逐类别人数见 [类别前后对账](../../../reports/tables/w3_category_reconciliation.csv)。主表新增 churn_label、total_charges_missing、tenure_zero、internet_applicable；前者只用作目标，后三者可以进入特征。

## 3. 异常与账单关系

| rule | count | action | basis |
| --- | --- | --- | --- |
| missing_TotalCharges | 11 | retain_and_flag | data contract |
| zero_tenure_boundary | 11 | retain_and_flag | Legal lower boundary, not deleted |

完整检查及分母见 [质量检查表](../../../reports/tables/w3_quality_checks.csv)。非法类别、重复/空客户键、数值非有限值、违规范围和服务逻辑冲突会报错。当前样本最大值不是永久业务上限；IQR 只是分布诊断。

下面计算 `TotalCharges − tenure × MonthlyCharges`，单位与源费用字段一致：

| statistic | value |
| --- | --- |
| count | 7032 |
| mean | 0.153193 |
| std | 67.2553 |
| min | -370.85 |
| 1% | -190.138 |
| 25% | -28.65 |
| 50% | 0 |
| 75% | 28.7 |
| 99% | 191.46 |
| max | 373.25 |

只有累计费用已知的客户进入差值分布。历史调价、优惠和精确账期不可见，差值不是自动纠错依据，不能拿当前月费乘年限回填真实历史账单。无互联网的结构性类别保持原意；六项增值服务与电话状态均通过交叉检查。

## 4. 标准化、编码与防泄漏

X 有 22 列：3 个数值、16 个类别、3 个标记；不包含 customerID、Churn 或 churn_label。独热展开后共 49 列。固定种子 42，按标签分层切分，留出比例 0.2，本周只演示预处理接口。

| split | rows | churned | churn_rate | missing_total_charges | matrix_columns | nonfinite_values |
| --- | --- | --- | --- | --- | --- | --- |
| train | 5634 | 1495 | 0.265353 | 8 | 49 | 0 |
| validation | 1409 | 374 | 0.265436 | 3 | 49 | 0 |

以下参数只从训练子集拟合：

| field | training_median | training_mean_after_imputation | training_scale | training_variance | fit_rows | training_nonmissing | all_missing_fallback_used |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tenure | 29 | 32.4851 | 24.5666 | 603.516 | 5634 | 5634 | False |
| MonthlyCharges | 70.5 | 64.93 | 30.1354 | 908.144 | 5634 | 5634 | False |
| TotalCharges | 1398.12 | 2301.32 | 2277.61 | 5.18749e+06 | 5634 | 5626 | False |

`training_median` 是训练中位数，`training_mean_after_imputation` 和 `training_scale` 是插补后的训练均值和标准差；缩放为 `(数值−训练均值)/训练标准差`。`all_missing_fallback_used` 表示整列训练数据缺失时是否用了计算用 0，本次可直接查看该列。该回退与一般训练中位数插补均不反写清洗主表。

验证集仅 transform；额外核验了训练参数未被验证集改变、划分无交集、保存再加载预处理器的结果相同。代码测试进一步覆盖错误输入和改变留出数据的情况，见 [测试证据](../../../reports/w3_test_results.json)。本周没有训练流失预测模型，没有输出 AUC、准确率或正式 CLV。

## 5. 交付位置与复现证据

- 清洗主表和客户级追踪：`data/processed/w3/`，共 9 份 CSV；X、y、ids 的同名拆分文件严格按行对应，勿单独排序。
- 已拟合预处理器与 49 列名称：`models/w3/`，这不是预测模型。
- [清洗规则 C01–C10](../../../reports/w3_cleaning_rules.md)、[特征工程设计 v1](../../../reports/feature_engineering_design_v1.md)、[运行说明](../../operations/W3_run_and_delivery.md)。
- [本次配置、代码和业务产物指纹](../../../reports/w3_run_metadata.json)、[新进程与 Notebook 验证](../../../reports/w3_verification.json)、[隔离环境验证](../../../reports/w3_clean_environment_verification.json)。这些验证文件分别记录自身执行状态；未运行的检查不能由本报告代替。
- [已执行 Notebook](../../../notebooks/03_cleaning.ipynb) 与 [浏览器阅读版](../../../notebooks/03_cleaning.html) 展示清洗和训练内变换过程。

输入 SHA-256：`88be4b93fbe0cc83421af1c503794c97c342eca914c1576db7c276e61d61358a`。本次运行开始/结束均核对来源登记中的 6 个原始文件，指纹未变。重跑仅比较 9 份数据 CSV 与 8 份汇总 CSV 的稳定业务内容，不要求执行时间、Notebook 单元 ID 或二进制字节完全相同。

## 6. 验收限制与 W4 交接

原始“清洗后无缺失和异常”的字面要求在清洗主表上不申报通过：未知累计费用仍有 11 个；模型输入无缺失/无穷值，已实现非法值规则没有失败。保留未知含义符合 W2→W3 交接，不能用删人或猜金额消除信息缺口。

特征工程设计交付 12 项真实时间特征，包含公式、窗口、所需数据、可用时点和泄漏约束，满足“设计至少 10 个”的数量要求；实际计算为 0，因为缺事件日期和历史日志。项目介绍中的时间特征构建仍待真实数据。无地区、行业、续约日期或可靠跨表客户键的部分继续登记数据缺口。

W4 从 25 列主表开发正式候选特征、登记公式并审查泄漏。W3 的 49 列编码矩阵不等于已完成 W4 的至少 50 项候选特征。后续正式切分后必须重新建立未拟合 Pipeline，并只在训练折中拟合插补、缩放和特征选择。
