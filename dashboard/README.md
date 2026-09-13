# W2 Dashboard

W2 提供两个入口：

1. **原生 Power BI Desktop 项目**：[`powerbi/W2_Churn.pbip`](powerbi/W2_Churn.pbip)。双击 `.pbip`，或在 Power BI Desktop 选择“文件 → 打开”，选择该文件。首次打开若提示数据不完整，点击“立即刷新”；项目内置 7,043 行 Telco 代理数据，刷新后可在四个页面间切换，并使用 Contract、InternetService、PaymentMethod、tenure_band、fee_level 五个真实字段筛选。运行结果见 [`reports/w2_powerbi_runtime_verification.json`](../reports/w2_powerbi_runtime_verification.json)。
2. **离线 HTML 预览**：[`w2_interactive.html`](w2_interactive.html)。双击即可在浏览器打开，不需要 Power BI 或登录，适合快速查看和演示；验证记录见 [`reports/w2_web_dashboard_verification.json`](../reports/w2_web_dashboard_verification.json)。

构建/更新原生项目：

```powershell
cd azure-churn-clv
.\.venv\Scripts\python.exe scripts\build_w2_powerbi.py
```

构建/更新 HTML 预览：

```powershell
.\.venv\Scripts\python.exe scripts\build_w2_web_dashboard.py
```

源 Telco 数据位于 `data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv`。原始数据没有 `region`、`industry` 或真实 Azure `subscription_type`，项目不伪造这些筛选器；Contract 仅作为合同类型/订阅代理。若有真实映射表，可按脚本帮助中的 `--customer-dimensions` 参数传入。
