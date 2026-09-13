# W2 输入清单

> 创建日期：2026-09-03  
> 用途：确认W2 EDA的前置条件已满足  
> 状态：✅ 已通过，可进入W2

## W2 必须输入

| 输入项 | 状态 | 路径/位置 | 验证方式 |
|--------|------|-----------|---------|
| **原始数据** | ✅ 可用 | `data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv` | SHA-256已验证 |
| **数据合同v1** | ✅ 完成 | `reports/data_contract_v1.md` | 粒度、标签、价值口径已冻结 |
| **字段字典v1** | ✅ 完成 | `reports/data_dictionary_v1.csv` | 21字段含义、类型、泄漏标记齐全 |
| **质量审计结果** | ✅ 完成 | `reports/tables/data_quality_results.csv` | 37项检查完成 |
| **质量问题登记** | ✅ 完成 | `reports/tables/data_quality_issues.csv` | 1个P1问题已记录 |
| **假设矩阵** | ✅ 完成 | `reports/hypothesis_matrix_v1.md` + `.csv` | 10项假设，8项可验证 |
| **业务报告v1** | ✅ 完成 | `reports/business_analysis_report_v1.md` | 业务逻辑和假设来源齐全 |
| **P0阻塞项** | ✅ 无阻塞 | `reports/data_quality_report_v1.md` | 0个P0，可进入W2 |

## W2 优先验证假设

| 优先级 | 假设ID | 假设简述 | 主字段 | 目标图表 |
|-------|--------|---------|--------|---------|
| **P0（必须）** | H1 | 月付/短合同流失率更高 | Contract | 流失率vs合同类型柱状图、卡方检验 |
| **P0（必须）** | H2 | 新客流失率更高 | tenure | 流失率vs tenure分段折线图 |
| **P0（必须）** | H4 | 服务采用少流失率更高 | 服务字段 | 流失率vs服务数量、各服务对比 |
| **P0（必须）** | H10 | 风险×价值交叉 | MonthlyCharges | 费用分位数vs流失率 |
| **P1（重要）** | H5 | 高费用低服务流失率更高 | MonthlyCharges + 服务 | 费用vs服务数散点图 |
| **P1（重要）** | H6 | 手动支付流失率更高 | PaymentMethod | 流失率vs支付方式 |
| **P2（可选）** | H9 | 细分差异 | 人口统计 | 细分流失率对比 |

**最低要求**：验证P0假设（H1, H2, H4, H10），共≥5项假设。

## W2 注意事项

### 数据使用限制

1. **TotalCharges暂不使用**：P1问题，W3清洗后再用
2. **无趋势特征**：只使用静态快照字段
3. **标签不平衡**：分析时注意分层

### 表述红线

- ❌ 不将相关性表述为因果
- ❌ 不将Telco代理数据写成Azure
- ❌ 不将背景数字写成实测结果
- ✅ 明确标注"基于Telco代理数据"

### 输出要求

- ≥15个图表（分布、关联、分组对比）
- 每图标注：假设ID、业务结论、行动建议、数据限制
- ≥5个假设验证结论
- 图表与假设映射表
- EDA发现总结

## W2 可选进阶项

| 进阶项 | 前置条件 | 优先级 |
|-------|---------|--------|
| 验证H7（工单） | 检查客户ID交集 | 低 |
| 更细分人口统计 | H9验证完成 | 中 |
| 服务组合模式聚类 | H4验证完成 | 低 |

## 启动检查清单

在开始W2 EDA前，确认：

- [x] Python虚拟环境可用
- [x] Jupyter Notebook可启动
- [x] 数据文件可读取（路径正确）
- [x] 假设矩阵已熟悉
- [x] 质量问题已知晓（TotalCharges）
- [x] 固定随机种子（42）

## 环境检查命令

```bash
cd g:/VScode/pj_mic/azure-churn-clv
.venv/Scripts/python.exe --version  # 应输出 Python 3.12.x
.venv/Scripts/python.exe -c "import pandas, numpy, matplotlib, seaborn; print('OK')"
```

## W2 参考材料

- 假设矩阵：`reports/hypothesis_matrix_v1.md`
- 字段字典：`reports/data_dictionary_v1.csv`
- 数据合同：`reports/data_contract_v1.md`
- 业务报告：`reports/business_analysis_report_v1.md`
- 质量报告：`reports/data_quality_report_v1.md`

---

**清单状态**：✅ 所有输入已满足，可进入W2  
**检查人**：项目团队  
**检查日期**：2026-09-03
