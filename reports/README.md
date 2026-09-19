# 报告目录

## 当前交付状态

W3 已新增清洗与预处理证据，主入口是 [清洗前后报告](w3_cleaning_report.md)。每项结果要按对应运行记录核对；设计文档不代替实际计算证明。

- [清洗规则](w3_cleaning_rules.md)：C01–C10 的实现、输入/输出合同和缺失边界。
- [特征工程设计 v1](feature_engineering_design_v1.md)：22 个输入字段、49 列示例矩阵、12 个静态候选和12项真实时序设计；真实时序计算仍缺数据。
- [运行核验](w3_verification.json)与[运行元数据](w3_run_metadata.json)：质量规则状态、17 份业务 CSV 重跑对账、新内核 Notebook、配置/依赖/来源指纹。
- [核心测试记录](w3_test_results.json)及[日志](w3_test_results.log)、[干净环境记录](w3_clean_environment_verification.json)：各自记录实际执行范围和结果；测试留证入口为 `scripts/test_week3.py`。
- [处理前后对比](tables/w3_before_after.csv)、[质量规则](tables/w3_quality_checks.csv)、[字段审计](tables/w3_field_audit.csv)、[类别频数对账](tables/w3_category_reconciliation.csv)。
- [费用差异诊断](tables/w3_charge_difference_summary.csv)、[预处理参数](tables/w3_preprocessor_parameters.csv)、[矩阵字段字典](tables/w3_feature_dictionary.csv)、[示例切分汇总](tables/w3_split_summary.csv)。
- [来源阅读索引](tables/w3_source_reading_register.csv)：13份项目自有 README 及7份需求/交接来源，共20项。
- [W3 运行与交付说明](../docs/operations/W3_run_and_delivery.md)、[W3 完成报告](../docs/deliverables/week3/W3完成报告_2026-09-16.md)、[验收清单](../docs/deliverables/week3/W3验收清单_2026-09-16.md)。

W1 基线报告与 W2 分析交付均集中在本目录。W2 EDA 于 2026-09-13 再次通过两次全新内核复现，本轮补充 Power BI 项目和离线交互展示；真实地区/行业/订阅维度仍待补数据。W2 完成报告保留在 [week2_sub](../docs/deliverables/week2/W2完成报告_2026-09-09.md)。

- [初步流失模式分析报告](w2_eda_summary.md)及[完整图文 HTML](w2_eda_report.html)。
- [逐项交付审计](w2_requirements_audit.md)：要求、证据、未满足项。
- [方法与决策](w2_methods_and_decisions.md)、[W3 清洗建议](w2_to_w3_cleaning_recommendations.md)。
- [图表映射](tables/w2_chart_hypothesis_mapping.csv)、[假设汇总](tables/w2_hypothesis_results.csv)、[20 张静态图](figures/w2_eda/)。
- [Notebook 复现验证](w2_verification.json)、[Power BI 结构验证](w2_powerbi_verification.json)、[Power BI 运行验证](w2_powerbi_runtime_verification.json)、[HTML 浏览器验证](w2_web_dashboard_verification.json)。
- [仪表板入口与说明](../dashboard/README.md)。

所有报告、表格和图表均以 `azure-churn-clv/` 为相对根路径；引用 W2 运行方式请查看 [W2 运行与交付说明](../docs/operations/W2_run_and_delivery.md)。


本目录保存项目交付报告及其证据索引。第一周预期形成：

- `business_churn_report_v1.md`
- `data_quality_report_v1.md`
- `data_contract_v1.md`
- `data_dictionary_v1.csv`
- `roadmap_8w_v1.md`
- `risk_register_v1.md`
- `week1_review.md`

机器可读表格放入 `tables/`，图表放入 `figures/`。所有结论应标明数据版本、证据路径和适用限制。
