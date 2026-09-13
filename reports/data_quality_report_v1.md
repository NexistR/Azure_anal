# 数据质量评估报告 v1

> 创建日期：2026-09-03  
> 数据版本：Telco Customer Churn (Kaggle v1, 下载于2026-09-02)  
> 报告状态：v1 - 第一周交付

## 执行摘要

**质量基线**：对 Telco Customer Churn 数据集（7,043行，21列）进行了系统化质量审计。

**关键发现**：
- ✅ **主键唯一性**：customerID 无空值、无重复，可作为唯一主键
- ✅ **标签完整性**：Churn 无缺失，流失率 26.54%（1,869/7,043）
- ✅ **结构完整**：所有预期字段存在，无解析错误
- ⚠️ **P1 问题**：TotalCharges 为字符串类型，包含 11 个空格字符串（0.16%）
- ⚠️ **时间限制**：无快照时间、事件时间字段，影响时间切分和趋势特征

**质量评级**：**良好（Good）** - 可用于建模，需在 W3 处理 TotalCharges 清洗。

**阻塞项**：0个 P0 阻塞项，可进入 W2 EDA。

## 1. 数据来源与版本

| 属性 | 值 |
|------|---|
| 数据集 | Telco Customer Churn |
| 来源 | Kaggle (https://www.kaggle.com/datasets/blastchar/telco-customer-churn) |
| 版本 | 1 |
| 下载日期 | 2026-09-02 |
| 文件路径 | data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv |
| SHA-256 | 88BE4B93FBE0CC83421AF1C503794C97C342ECA914C1576DB7C276E61D61358A |
| 文件大小 | 977,501 字节 |
| 许可 | Data files © Original Authors |

**可复现性**：✅ 来源、版本、哈希已记录，任何人可验证文件版本一致性。

## 2. 质量审计方法

**审计工具**：`scripts/profile_data.py`（可重复运行的Python脚本）  
**运行时间**：2026-09-03 10:52:27  
**审计维度**：9类检查（结构、唯一性、完整性、类型、范围、类别、一致性、异常、标签）  
**总检查数**：37项  
**输出**：
- `reports/tables/data_quality_results.csv`：检查结果汇总
- `reports/tables/data_quality_issues.csv`：问题登记表

## 3. 质量检查结果

### 3.1 九维度检查汇总

| 维度 | 检查数 | PASS | WARN | FAIL | P0 | P1 | P2 |
|------|-------|------|------|------|----|----|---|
| 结构 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 唯一性 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 完整性 | 21 | 21 | 0 | 0 | 0 | 0 | 0 |
| 类型/格式 | 1 | 0 | 1 | 0 | 0 | 1 | 0 |
| 合法范围 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 类别取值 | 8 | 8 | 0 | 0 | 0 | 0 | 0 |
| 业务逻辑 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 异常值 | 0 | - | - | - | 0 | 0 | 0 |
| 标签质量 | 2 | 1 | 1 | 0 | 0 | 0 | 0 |
| **总计** | **37** | **34** | **2** | **0** | **0** | **1** | **0** |

**结论**：✅ 92% 检查通过，0 个阻塞项，1 个 P1 问题需在建模前处理。

### 3.2 关键发现详情

#### ✅ 通过项（高质量）

1. **结构与可读性**
   - 文件正常解析，7,043 行，21 列
   - 列名与预期一致
   - UTF-8 编码无乱码

2. **主键唯一性**
   - `customerID`：7,043 个唯一 ID
   - 无空值（0）
   - 无重复（0）
   - ✅ **可作为唯一主键**

3. **完整性**
   - 所有 21 个字段无缺失值
   - 标签 `Churn` 无缺失
   - 关键特征（tenure, MonthlyCharges, Contract）无缺失

4. **类别取值**
   - `gender`: Male, Female（符合预期）
   - `SeniorCitizen`: 0, 1（符合预期）
   - `Contract`: Month-to-month, One year, Two year（符合预期）
   - `Churn`: Yes, No（符合预期）
   - 其他类别字段取值正常

5. **合法范围**
   - `tenure`: 0-72 月（合理范围，无负值）
   - `MonthlyCharges`: 18.25-118.75（合理，无负值、无零值）

#### ⚠️ P1 问题（建模前必须处理）

**问题 #1：TotalCharges 数据类型错误**

| 属性 | 值 |
|------|---|
| 字段 | TotalCharges |
| 问题 | 应为数值类型，实际为字符串（object） |
| 影响行数 | 11 行为空格字符串 `" "` |
| 影响比例 | 0.16% |
| 严重程度 | P1（建模前必须处理） |
| 影响 | 无法作为数值特征使用；需类型转换 |
| 样例 | 空格字符串（11 行） |
| 建议 | W3 清洗：空格转 NaN，字符串转 float，检查与 tenure×MonthlyCharges 一致性 |
| 需业务确认 | 否（技术问题） |

**处理策略（W3）**：
```python
# 1. 空格转NaN
df['TotalCharges'] = df['TotalCharges'].replace(' ', np.nan)

# 2. 转换为float
df['TotalCharges'] = pd.to_numeric(df['TotalCharges'], errors='coerce')

# 3. 检查一致性
df['TotalCharges_expected'] = df['tenure'] * df['MonthlyCharges']
df['TotalCharges_diff'] = abs(df['TotalCharges'] - df['TotalCharges_expected'])

# 4. 决策：删除、插补或保留缺失标志
```

#### ⚠️ 注意项（不阻塞建模）

**标签不平衡**：
- 流失客户：1,869（26.54%）
- 未流失客户：5,174（73.46%）
- 不平衡比例：约 1:2.8
- 影响：W5 需考虑不平衡处理（SMOTE、类别权重、阈值调整）
- 不阻塞建模，但影响评估指标选择（使用 PR-AUC 优于 ROC-AUC）

## 4. 数据限制登记

### 4.1 时间字段缺失（P0 风险）

| 限制项 | 影响 | 应对策略 |
|-------|------|---------|
| **无快照时间** | 无法定义观察截止日 | MVP 使用静态快照分类 |
| **无事件时间** | 无法定义预测窗口 | 不声称"预测未来X天" |
| **无时间序列** | 无法计算趋势特征（H3） | 记录为数据缺口 |
| **无法时间切分** | 只能随机切分 | 明确说明验证限制 |

**风险评级**：P0（影响建模方法和结果表述）  
**缓解措施**：
- W5 使用分层随机切分（stratified split）
- 报告中明确标注"静态快照分类"
- 不声称"严格时间验证"
- 记录为未来数据需求

### 4.2 其他数据缺口

| 缺口 | 影响假设 | 优先级 | 应对 |
|------|---------|-------|------|
| 使用量时间序列 | H3 不可验证 | 中 | 记录为未来需求 |
| 工单数据关联 | H7 不可验证 | 低 | W2+ 可选验证 |
| 续约历史 | H8 不可验证 | 低 | 用 tenure 间接推断 |
| 真实成本/毛利 | 价值代理限制 | 低 | 使用费用作透明代理 |

## 5. 质量问题分级与优先级

### 5.1 P0 阻塞项（必须解决才能进入下一阶段）

✅ **无 P0 阻塞项** - 可进入 W2 EDA

### 5.2 P1 问题（建模前必须处理）

| ID | 字段 | 问题 | 影响 | 计划解决 |
|----|------|------|------|---------|
| Q1 | TotalCharges | 字符串类型，11 个空格 | 无法作为数值特征 | W3 清洗 Pipeline |

### 5.3 P2 问题（后续优化）

✅ **无 P2 问题**

## 6. 数据概况统计

### 6.1 基本统计

| 指标 | 值 |
|------|---|
| 总行数 | 7,043 |
| 总列数 | 21 |
| 主键 | customerID（唯一） |
| 标签 | Churn（26.54% 流失） |
| 缺失值 | 0（TotalCharges 有 11 个空格字符串） |
| 重复行 | 0 |

### 6.2 字段类型分布

| 类型 | 数量 | 字段示例 |
|------|------|---------|
| 字符串 | 17 | customerID, gender, Contract, PaymentMethod... |
| 整数 | 2 | SeniorCitizen, tenure |
| 浮点数 | 1 | MonthlyCharges |
| 待转换 | 1 | TotalCharges（字符串→浮点数） |

### 6.3 关键字段统计

**tenure（客户年限）**：
- 范围：0-72 月
- 均值：32.4 月
- 中位数：29 月
- 25%分位：9 月，75%分位：55 月

**MonthlyCharges（月度费用）**：
- 范围：18.25-118.75
- 均值：64.76
- 中位数：70.35
- 标准差：约30（推测）

**Contract（合同类型）**：
- Month-to-month：3,875（55.0%）
- Two year：1,695（24.1%）
- One year：1,473（20.9%）

**PaymentMethod（支付方式）**：
- Electronic check：2,365（33.6%）
- Mailed check：1,612（22.9%）
- Bank transfer (automatic)：1,544（21.9%）
- Credit card (automatic)：1,522（21.6%）

## 7. W2 输入确认

### 7.1 W2 EDA 输入清单

| 输入项 | 状态 | 路径/说明 |
|--------|------|-----------|
| 原始数据文件 | ✅ 可用 | data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv |
| 数据合同 v1 | ✅ 完成 | reports/data_contract_v1.md |
| 字段字典 v1 | ✅ 完成 | reports/data_dictionary_v1.csv |
| 质量审计结果 | ✅ 完成 | reports/tables/data_quality_results.csv |
| 质量问题登记 | ✅ 完成 | reports/tables/data_quality_issues.csv |
| 假设矩阵 | ✅ 完成 | reports/hypothesis_matrix_v1.md / .csv |
| P0 阻塞项 | ✅ 无阻塞 | 可进入 W2 |

### 7.2 W2 注意事项

1. **TotalCharges 使用前需清洗**：先转换为数值类型再使用
2. **标签不平衡**：EDA 时注意分层分析
3. **时间限制**：不尝试构建趋势特征，使用静态快照字段
4. **假设优先级**：优先验证 H1, H2, H4, H10（数据支持度高）

## 8. 质量监控建议

### 8.1 W3 清洗后复查

- [ ] TotalCharges 转换成功率
- [ ] TotalCharges 与 tenure×MonthlyCharges 一致性
- [ ] 清洗后数据行数变化
- [ ] 重新运行质量审计脚本

### 8.2 质量指标基线

用于 W3 前后对比：

| 指标 | W1 基线 | W3 目标 |
|------|---------|---------|
| 行数 | 7,043 | 保持或合理减少 |
| 主键唯一性 | 100% | 100% |
| TotalCharges 可用性 | 99.84% | 100%（清洗后） |
| 标签完整性 | 100% | 100% |

## 9. 附录

### A. 质量审计脚本

路径：`scripts/profile_data.py`

**可复现性**：
```bash
cd g:/VScode/pj_mic/azure-churn-clv
.venv/Scripts/python.exe scripts/profile_data.py
```

输出：
- 控制台日志
- reports/tables/data_quality_results.csv
- reports/tables/data_quality_issues.csv

### B. 详细检查结果

见：`reports/tables/data_quality_results.csv`（37 项检查）

### C. 问题登记表

见：`reports/tables/data_quality_issues.csv`（1 个 P1 问题）

---

**报告状态**：✅ v1 完成  
**质量评级**：良好（Good） - 可用于建模，需处理 TotalCharges  
**阻塞项**：0 个  
**下一步**：✅ 可进入 W2 EDA  
**创建人**：项目团队  
**复核日期**：W3 清洗后更新版本
