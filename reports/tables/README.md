# 报告表格

保存数据清单、质量结果、模型指标、客户评分和分群摘要等机器可读输出。每个表格应能追溯输入数据、生成代码和运行时间。

W3 表格以 `w3_` 开头：

| 文件 | 内容 |
|---|---|
| `w3_before_after.csv` | 行数、主键、标签、空白与缺失等前后对账 |
| `w3_quality_checks.csv` | 质量规则的实际结果、数量与处置；passed与documented分别记录，不把有据缺失写成零缺失 |
| `w3_field_audit.csv` | 字段类型、缺失及值域审计 |
| `w3_category_reconciliation.csv` | 16 个预测类别及标签等原始类别的频数前后对账 |
| `w3_charge_difference_summary.csv` | 累计费用与当前月费乘年限之差的诊断；差值不直接认定错误 |
| `w3_preprocessor_parameters.csv` | 训练内插补与缩放参数 |
| `w3_feature_dictionary.csv` | 49 个示例数值矩阵列及其来源 |
| `w3_split_summary.csv` | 示例训练/验证的人数、标签分布 |
| `w3_source_reading_register.csv` | 实施前读取的20份源文档及指纹；不是运行后导航文件的最新指纹 |

前8份是运行器生成的汇总业务证据，与9份客户级 CSV 一起参与17份文件重跑比较。来源阅读索引单独记录阅读时版本。客户级主表、ID、标签、逐客户缺失追踪留在被忽略的 `data/processed/w3/`，不复制到可提交的汇总表中。

W2 的 `w2_*.csv` 继续作为原始 EDA 证据；W3 不改写它们。详见 [W3 清洗报告](../w3_cleaning_report.md)与[运行元数据](../w3_run_metadata.json)。
