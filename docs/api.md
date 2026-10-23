# 分析 API

以下接口保留原模块路径，以兼容历史类和模型状态；路径中的 `w7`、`w8` 是版本标识。项目从仓库根目录执行，不提供可脱离配置文件的独立 wheel。

## 解释冻结模型

安装 `requirements/explain.txt` 后使用 `FrozenTreeShap`。仅传入已核实属于原训练或验证分区的 22 字段表；当前 API 的分区字段不能用来把任意外部输入标为“验证集”。

```python
from src.models.w7.explain import FrozenTreeShap, global_rank

explainer = FrozenTreeShap.load("models/w7/churn_runtime.zip")
# validation_features 由调用方从可信的固定验证分区提供。
batch = explainer.explain(validation_features, partition="validation")
ranking = global_rank(batch.logical_values, explainer.logical_names)
```

SHAP 的单位为 log-odds；先按 64 个逻辑变量汇总 111 个编码列的有符号贡献，再计算平均绝对贡献。与原生 XGBoost 的比较是接口一致性检查，并非独立算法交叉验证。

`EmpiricalLimeExplainer(runtime, train_frame, train_ids=...)` 以真实、已观测的训练客户建立邻域；`explain(instance_one_row)` 返回局部替代模型及保真度。该替代模型会拟合，冻结的流失预测模型不会重训。不得用示例中的合成行冒充原训练邻域。`catalog.py` 提供解释标签和复核建议。

## 应用已有分群与价值规则

先按 `configs/artifacts.json` 核对可信本地工件；加载过程使用 joblib。以下仅调用已拟合对象，不执行分群搜索。

```python
import joblib
from src.segmentation.w8 import static_features, assign_dbscan, add_value_risk

bundle = joblib.load("models/w8/segmentation.joblib")
matrix = bundle["preprocessor"].transform(static_features(features))
kmeans_labels = bundle["kmeans"].predict(matrix)
dbscan_labels, ambiguous, distances, core_indices = assign_dbscan(matrix, bundle)
# scored_frame 包含唯一非空 customerID、MonthlyCharges、冻结模型概率 p。
priorities = add_value_risk(scored_frame, bundle["value_rules"]["high_value_threshold"])
```

DBSCAN 在新行上使用到训练核心点的最近邻扩展；这是项目定义的应用规则，不是 DBSCAN 原生 `predict`。全局优先级在传入的完整表内排序，不宜分批后直接合并各批次排名。

`fit_segmentation`、`fit_value_rules` 及聚合函数作为研究 API 保留；只有显式调用才拟合。它们要求调用方提供训练分区，不能把本发布副本的整理验证当作重新训练或新盲测。月费阈值来自训练中位数，`p × MonthlyCharges` 是情景排序权重，不能解释为 CLV、利润或挽留收益。
