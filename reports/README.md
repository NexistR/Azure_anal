# 报告目录

## 当前交付状态

W1 基线报告与 W2 分析交付均集中在本目录。W2 EDA 于 2026-09-13 再次通过两次全新内核复现，本轮补充 Power BI 项目和离线交互展示；真实地区/行业/订阅维度仍待补数据。W2 完成报告保留在 [week2_sub](../../week2_sub/W2完成报告_2026-09-09.md)。

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
