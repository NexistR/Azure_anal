# 聚合结果阅读说明

这里仅保留方法、阈值、分群或风险档位的汇总，不提供客户级明细、预测名单或本地模型。历史记录形成于2026-10-14，精度调优已于2026-10-16终止。

- `history_validation.csv`：46条历史验证记录，保留各自的阈值来源；重复模型和探索阈值记录不是独立模型。
- `history_oof.csv`：155条训练OOF记录，含融合评分及复用记录；不是155个独立模型。两张历史表的“证据路径”仅标识原研究归档的相对位置，不表示这些底层文件已公开。
- `global_top10.csv`：训练集确定的十项逻辑SHAP重要性；validation排名和bootstrap频率另列，贡献单位为log-odds。
- `risk_summary.json`：train与历史validation分列，风险分档固定为0.10/0.30；训练结果是拟合内描述，不是OOF。
- `common_thresholds.csv`、`capacity_budgets.csv`：历史validation人数容量情景。完整同分组保留，预算选择不使用标签；不改变0.30政策，也不表示干预成功。
- `stage_summary.csv`：各负载的独占阶段平均耗时，不能与另一日期的P50直接混合；阶段占比不是因果消融。
- `algorithm_comparison.csv`：仅训练内的11个聚类候选。DBSCAN轮廓系数为非噪声条件指标，不能忽略覆盖率与KMeans直接判优。
- `cluster_profiles.csv`、`quadrant_summary.csv`、`value_sensitivity.csv`：train/validation分列的静态订阅与月费代理汇总；主价值界限来自训练月费中位数，不能解释成真实RFM、CLV、利润或因果收益。

历史validation已被多次复用，不能称为新的独立测试。原始数值保持不变；两张历史表仅清除机器绝对路径。源文件和公开副本的哈希、检查范围记录在`../cleanup/publication_audit.json`。
