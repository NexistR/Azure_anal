# 模型产物

用于保存本地训练得到的 Pipeline、模型和相关元数据。模型二进制被 Git 忽略；仅本说明文件纳入项目结构。

W3 在 `w3/` 保存：

| 文件 | 内容 |
|---|---|
| `preprocessor.joblib` | 在示例训练子集拟合的完整预处理 Pipeline：输入合同、插补/缩放/独热编码、有限数值检查 |
| `feature_names.json` | 49 个输出列名，顺序与矩阵一致 |

这是预处理器，没有训练流失分类器，不包含预测性能结论。加载后只对符合合同的 22 列 X 调用 `transform()`；X 不含客户 ID、Churn 或 churn_label。新的正式切分、交叉验证折或模型实验必须从未拟合接口重新 fit，不能把本周已拟合示例直接用于另一个测试集。

保存/加载后的转换一致性与训练内统计核验见 [w3_verification.json](../reports/w3_verification.json)，示例切分、来源及依赖见 [w3_run_metadata.json](../reports/w3_run_metadata.json)。操作说明见 [W3 运行与交付](../docs/operations/W3_run_and_delivery.md)。

每个模型应记录数据版本、特征版本、切分方式、随机种子、训练参数和评估结果，且必须保存完整预处理 Pipeline，而非只保存分类器。
