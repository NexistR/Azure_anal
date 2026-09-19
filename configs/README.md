# 配置目录

用于保存可提交的运行配置示例，例如相对输入/输出路径、随机种子、切分参数和模型参数。

W3 当前配置是 [w3_cleaning.json](w3_cleaning.json)，规则版本 `w3-telco-cleaning-v1.0.0`，集中定义：

- 原始 21 字段、清洗后新增 4 字段、允许类别、结构性服务类别、数值范围与标签映射。
- 输入相对路径、预期 SHA-256、数据/预处理器输出目录。
- `seed=42`、`test_size=0.2`，仅用于本周预处理接口的随机分层示例。
- 22 字段 X 白名单、训练中位数插补、StandardScaler、未知类别报错策略。

通过 `scripts/run_week3.py --config configs/w3_cleaning.json` 使用配置。运行入口的相对路径以项目根目录解析，与当前终端工作目录无关。数据输出限 `data/processed/`、模型输出限 `models/`、报告输出限 `reports/`，三类也可放在项目 `.cache/` 的不同子目录；输出目录不能相同或互相包含，输入不能位于任何输出目录中。

输入必须位于项目内；换数据版本时将原始文件放入 `data/raw/`，先更新来源清单 `reports/tables/data_manifest.csv` 与配置的预期哈希。不能仅为绕过错误而修改标签、类别或缺失规则。配置检查会拒绝不支持的合同变更。详见 [W3 运行说明](../docs/operations/W3_run_and_delivery.md)与[清洗规则](../reports/w3_cleaning_rules.md)。

账号、密钥、连接字符串和本机绝对路径不得写入此目录；敏感配置只通过已忽略的 `.env` 或安全凭据机制提供。
