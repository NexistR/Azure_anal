# 输入与运行约定

`scripts/predict.py` 接受 UTF-8 CSV，包含以下 22 个清洗后预测字段，可额外携带 `customerID`。列顺序可变；重复列、未知列、空表和标签列均被拒绝。`Churn`、`churn_label` 不得进入预测输入。

| 字段类型 | 字段 |
|---|---|
| 数值 | `tenure`, `MonthlyCharges`, `TotalCharges` |
| 类别 | `gender`, `SeniorCitizen`, `Partner`, `Dependents`, `PhoneService`, `MultipleLines`, `InternetService`, `OnlineSecurity`, `OnlineBackup`, `DeviceProtection`, `TechSupport`, `StreamingTV`, `StreamingMovies`, `Contract`, `PaperlessBilling`, `PaymentMethod` |
| 确定性标记 | `total_charges_missing`, `tenure_zero`, `internet_applicable` |

精确类别和数值范围以 [清洗配置](../configs/w3_cleaning.json) 为准。`tenure` 为非负整数；`MonthlyCharges` 严格为正；`TotalCharges` 为非负数或缺失，缺失标记须一致。无互联网、无电话对应的附加服务类别必须自洽。整数采用精确解析，不把带小数的超大数值通过浮点舍入误判为整数。

已有的 21 列历史原始表可通过 `TelcoCleaner().fit_transform(raw)` 清洗，再用 `split_xy(cleaned)` 分离 22 个预测字段。此清洗器的 `fit` 只冻结规则、不估计统计量；历史表含标签，该路径不能用于伪造新客户标签。实时业务输入应直接按上述 22 字段合同提供。

```python
from src.data.clean import TelcoCleaner, read_raw
from src.data.preprocess import split_xy

cleaned = TelcoCleaner().fit_transform(read_raw("data/telco.csv"))
features, labels, customer_ids = split_xy(cleaned)
features.to_csv("data/predictors.csv", index=False)
```

推理输出为行号、可选客户标识、`churn_probability` 和 `churn_prediction`。冻结决策为 `p >= 0.30`。CSV 按批次读取，只有全部批次成功才提交结果文件；默认不覆盖已有文件。API 的 `predict_score` 返回完整长度数组，工作矩阵分批，但总输出仍占 O(n) 内存。

`score_risk.py` 接受概率列，生成 `score=100p`、风险档位、冻结决策和复核建议。低风险 `[0,0.10)`，中风险 `[0.10,0.30)`，高风险 `[0.30,1]`；显示舍入不参与分档。这些分数未新增校准，不是经验证的损失概率或干预收益。
