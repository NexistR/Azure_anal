# 处理后数据

本目录只保存由可重复脚本或 Pipeline 生成的数据。数据文件被 Git 忽略；仅本说明文件纳入项目结构。

每个输出都应能追溯到原始文件哈希、处理脚本版本、运行参数和生成时间。不得手工覆盖原始数据。

W3 输出集中在 `w3/`：

| 文件 | 用途 |
|---|---|
| `telco_clean.csv` | 7,043 行、25 列清洗主表；保留 11 个未知 TotalCharges，并有缺失/年限/服务适用性标记 |
| `missing_total_charges_audit.csv` | 11 个未知累计金额客户的本地追踪证据 |
| `split_membership.csv` | 示例训练/验证划分与客户编号对应 |
| `X_train.csv`、`X_validation.csv` | 经训练内插补、标准化和独热编码的49列数值矩阵；当前划分分别为5,634/1,409行 |
| `y_train.csv`、`y_validation.csv` | 独立的0/1标签 |
| `ids_train.csv`、`ids_validation.csv` | 与矩阵逐行对应的追踪键；不进入模型输入 |

主表 CSV 中空单元格仍代表未知金额，不应在电子表格中手工补 0。CSV 本身不保存 pandas dtype，程序使用主表时应再次经过合同校验；例如 `TelcoCleaner(config).fit_transform(pd.read_csv(path))`，再通过 `split_xy()` 得到22列X、y和ID。

这里的数值矩阵用于 W3 接口演示；不是 W4 最终特征集或 W5 冻结测试集。重新划分正式实验时应重新拟合预处理器。字段、缺失语义见 [清洗规则](../../reports/w3_cleaning_rules.md)，输入指纹及输出文件哈希见 [运行元数据](../../reports/w3_run_metadata.json)。

这些客户级文件均被 Git 忽略。共享代码后，需要按 [W3 运行说明](../../docs/operations/W3_run_and_delivery.md)准备经登记的数据并重新生成。
