# W2 交付要求审计报告

审计日期：2026-09-13  
审计范围：工作区内项目自有 Markdown；排除 `.venv`、`.tools`、`.runtime`、`.cache`、`.git` 及第三方许可证/依赖文档。本文只记录证据、缺口和验收口径，不宣称尚未完成的交付。

## 已阅读文件索引

以下文件已逐一读取（共 52 个；不含第三方依赖/许可证 Markdown）：

- `azure-churn-clv/`：`README.md`；`configs/README.md`；`dashboard/README.md`；`data/README.md`；`data/raw/README.md`；`data/processed/README.md`；`docs/README.md`；`models/README.md`；`notebooks/README.md`；`tests/README.md`。
- `azure-churn-clv/docs/`：`operations/W2_run_and_delivery.md`、`operations/当前工作进度与续作交接.md`、`operations/环境安装与配置说明.md`、`planning/第一周任务总体框架与推进步骤.md`、`planning/项目总体理解与个人12周计划.md`、`project/Azure客户流失预测与CLV提升_项目介绍.md`、`project/Azure客户流失预测与CLV提升_零基础实现指南.md`。
- `azure-churn-clv/reports/`：`business_analysis_report_v1.md`、`data_contract_v1.md`、`data_quality_report_v1.md`、`decision_log.md`、`environment_recovery.md`、`glossary_v1.md`、`hypothesis_matrix_v1.md`、`README.md`、`roadmap_8w_v1.md`、`scope_v1.md`、`w1_d1_startup_checklist.md`、`w2_eda_summary.md`、`w2_input_checklist.md`、`w2_methods_and_decisions.md`、`w2_to_w3_cleaning_recommendations.md`、`figures/README.md`、`tables/README.md`。
- `week1_sub/`：`business_analysis_report_v1.md`、`data_quality_report_v1.md`、`PDF转换说明.md`、`roadmap_8w_v1.md`。
- `week2_sub/`：`W2完成报告_2026-09-09.md`、`W2零基础说明.md`、`项目结构与构成说明.md`。
- `交付报告/`：`W1完成总结.md`、`W1完成情况核查报告_2026-09-04.md`、`W2准备工作总结_2026-09-08.md`、`W2启动清单与立即行动.md`、`W2工作框架与推进计划.md`、`交付报告week_1.md`、`交付物清单.md`、`第一周任务完成报告.md`。
- `交接文档/`：`项目交接文档_2026-09-02.md`、`项目交接文档_2026-09-03-1.md`。

## 统一后的 W2 要求矩阵

| 编号 | 要求及来源 | 当前证据与状态 | 仍需做的事/验收方式 |
|---|---|---|---|
| W2-01 | EDA Jupyter Notebook，可完整重跑（W2 框架、启动清单；项目介绍第 2 周） | `notebooks/02_eda.ipynb`、`02_eda.html` 已存在；`w2_verification.json` 记录两次全新内核、24 个代码单元成功。**已满足** | 2026-09-13 两次全新内核复现已完成，CSV/PNG 哈希一致，原始文件未修改。 |
| W2-02 | Power BI 交互式仪表板（项目介绍《逐周计划》明确列为第 2 周交付；用户本轮明确要求补回） | 原生 Power BI 项目已生成；结构校验见 `reports/w2_powerbi_verification.json`，Desktop 模型查询与刷新见 `reports/w2_powerbi_runtime_verification.json`（7,043 行、1,869 流失）。本目录同时提供 `dashboard/w2_interactive.html` 离线 Plotly 预览，已用 Edge 验证 15 图和联合筛选。**HTML 不替代 Power BI** | 原生项目须能在 Power BI Desktop 打开、刷新本地数据并保留页面/度量值/入口说明；在线工作区发布不属于 W1-W8 范围。 |
| W2-03 | 《初步流失模式分析报告》（项目介绍第 2 周） | `reports/w2_eda_summary.md` 与 `reports/w2_eda_report.html` 包含 Top 5、假设结果和限制，README/交付清单已统一名称入口。**已满足** | 摘要实测 2,452 个中文字符，超过不少于 500 字要求。 |
| W2-04 | 至少 15 个不同维度图表，覆盖单变量、关联、交叉（框架/启动清单） | `reports/figures/w2_eda/` 有 20 张 PNG；映射表和 HTML 已生成。**满足** | 验证每张图 300 dpi、标题/轴标签、假设 ID、结论、行动和证据表均可追溯。 |
| W2-05 | 仪表板可按地区、行业、订阅类型筛选（项目介绍第 2 周验收标准） | Telco 代理数据 21 列中无 `region`、`industry`、`subscription_type`；只有 `Contract`、`InternetService` 等可用分类。**未满足：缺少真实数据** | 已标注缺失字段、Contract 仅作合同代理。已实现真实 `customerID,region,industry,subscription_type` 映射接入，要求唯一客户键、全覆盖且非空；获得真实表后重建 Power BI 并核验三个新增切片器。 |
| W2-06 | 至少 5 个可验证假设，必须含 H1/H2/H4/H10（框架/启动清单） | `w2_verification.json`：7 项已分析、10 项注册；H1/H2 操作化支持，H4/H5/H6/H9/H10 部分通过，H3/H7/H8 不可验证。**满足** | 保持“部分通过/不可验证”状态，不把缺字段算作通过；核对 `w2_hypothesis_results.csv` 共 10 行。 |
| W2-07 | 统计证据：p 值、效应量、区间及多重比较说明（启动清单与方法记录） | `w2_statistical_tests.csv`、`w2_eda_summary.md` 已记录 22 项检验、Bonferroni 说明和 Wilson 区间。**满足** | 仪表板若显示统计值，需注明它们来自横截面代理数据，不显示因果或个人预测概率。 |
| W2-08 | W3 清洗建议，至少 10 条（框架/准备总结） | `w2_to_w3_cleaning_recommendations.md` 已给出字段、规则、验收口径。**满足** | 保持“建议”语气；不得把 W3 清洗写成已执行。 |
| W2-09 | 可复现：固定 seed=42、相对路径、依赖锁定、原始数据不改（框架/运行指南） | `w2_analysis_metadata.json`、`w2_verification.json`、`requirements_w2.txt`、原始哈希记录齐全。**满足** | 在最终交付说明中给出 Windows 启动命令，并从项目根目录验证一次。 |
| W2-10 | 图表映射 CSV 与十项假设汇总 CSV（框架六类必须交付物） | `reports/tables/w2_chart_hypothesis_mapping.csv`、`w2_hypothesis_results.csv` 存在。**满足** | 检查 CSV UTF-8、列名、图号与 PNG 一一对应；摘要中链接使用仓库内相对路径。 |

## 文档冲突及处理决定

1. 原 `交付报告/W2工作框架与推进计划.md`、`W2启动清单与立即行动.md`、`W2准备工作总结_2026-09-08.md`把 Power BI 放在冻结 DoD 之外或未来阶段，原 `dashboard/README.md` 也只是占位说明。本轮已更新当前 README 和运行指南，并给三份历史计划加入补充说明。
2. `azure-churn-clv/docs/project/Azure客户流失预测与CLV提升_项目介绍.md`第 147 行的逐周计划把 **Power BI 交互仪表板**列为 W2 关键交付，并要求地区/行业/订阅类型筛选；用户本轮再次明确要求完成先前缺失的 W2 全部交付。
3. 因此本轮按较高优先级的项目介绍原始要求和用户最新指令执行：Power BI 本地可打开项目属于 W2 必须项；不要求在线发布（项目范围文档将云端发布列为范围外）。当前审计明确区分原生 Power BI 与离线 HTML 预览，不能声称原始全部要求已经通过。

## 不可伪造字段与分析边界

- Telco 数据实际字段为 `customerID`、人口统计、`tenure`、服务、`Contract`、`PaymentMethod`、`MonthlyCharges`、`TotalCharges`、`Churn`，没有地区、行业、Azure 订阅 ID 或资源使用量。
- `Contract` 只能叫“合同类型”；若在仪表板中作为订阅类型代理，必须在页面和报告中标注“代理字段”，不能写成 Azure 订阅类型。
- W2 是横截面 EDA。没有事件日期、连续账单、真实成本/利润和随机干预，不能宣称因果效果、正式 CLV、未来流失概率或 Azure 真实客户结论。
- W2 方法记录将 H4 的服务计数限定为六个互联网服务，并另存全服务计数以保留 “No internet service” 适用性；这与早期模板列出的九个服务字段不同，最终口径应以方法记录和 CSV 为准。

## 给最终验收人的清单

- [ ] `dashboard/` 有 `.pbip`/`.pbix`，Power BI Desktop 能打开并刷新本地 CSV。
- [ ] 仪表板至少有流失概览、合同/年限、费用/服务、支付方式或人口统计页面；真实字段可筛选，缺失的地区/行业/订阅维度有醒目标注。
- [x] 交付说明给出打开路径、相对数据路径、内嵌快照的更新与刷新步骤；本地使用不依赖在线发布。
- [x] 20 张 PNG、28 张 W2 CSV、Notebook、HTML、摘要、映射表、假设汇总和 W3 建议均能从 README 进入；入口文档链接已检查。
- [x] `scripts/run_week2.py --verify-reproducibility` 于 2026-09-13 通过；20 图、7 项已分析假设、10 项登记假设和 28 张 W2 CSV 已核对。
- [ ] W2-05：真实地区、行业、订阅类型筛选——缺少映射数据，保留未完成状态。

