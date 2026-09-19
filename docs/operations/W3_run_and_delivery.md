# W3 运行与交付说明

更新日期：2026-09-16；GitHub 路径整理：2026-09-19。W3 实际项目文件统一放在仓库根目录，`docs/deliverables/week3/` 保存推进大纲、完成报告和验收清单。

W3 把原始客户表整理成可检查、可复用的数据，并演示如何把它转换成机器学习能接收的数字。清洗主表保留未知金额，数值接口在训练内插补；本周没有训练流失预测模型。

## 1. 最快查看结果

- 看处理前后发生了什么：[清洗报告](../../reports/w3_cleaning_report.md)。
- 看逐步执行过程：[Notebook HTML](../../notebooks/03_cleaning.html)；需要改代码时打开 [03_cleaning.ipynb](../../notebooks/03_cleaning.ipynb)。
- 看每条规则：[w3_cleaning_rules.md](../../reports/w3_cleaning_rules.md)。
- 看特征怎么设计、哪些还缺数据：[feature_engineering_design_v1.md](../../reports/feature_engineering_design_v1.md)。
- 看交付是否满足要求：[W3 完成报告](../deliverables/week3/W3完成报告_2026-09-16.md)、[W3 验收清单](../deliverables/week3/W3验收清单_2026-09-16.md)。

主表位置为 `data/processed/w3/telco_clean.csv`。如果用 Excel 查看，TotalCharges 的11个空单元格表示未知，不要手工改成0再覆盖文件。

## 2. 使用现有项目环境一键重跑

在 PowerShell 执行：

```powershell
# 先进入你自己的仓库根目录；以下命令要求已准备原始数据和本地环境。
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --verify-reproducibility
```

命令依次读取并核对冻结数据、执行清洗与质量规则、做示例训练内预处理、输出证据，在另一个全新进程重跑比较业务文件，再执行Notebook并导出HTML。默认输出目录为 `data/processed/w3/`、`models/w3/`、`reports/`；同名W3产物在重跑时更新，原始数据仍只读。

仅需要核心清洗或当前环境没有 Notebook 包时：

```powershell
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --verify-reproducibility --skip-notebook
```

`--skip-notebook` 仍执行清洗和预处理核验，但该次记录的 Notebook 状态为 skipped。不要把以前留在磁盘上的 HTML 当成本次重新执行的证据。

核心测试单独执行并自动留证：

```powershell
& .\.venv\Scripts\python.exe .\scripts\test_week3.py
```

它会发现全部 `tests/test_w3*.py`，生成 `reports/w3_test_results.json` 和 `.log`，并记录代码/测试指纹。若只需直接看 unittest 输出，也可运行：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_w3*.py" -v
```

一键工作流的质量检查与单元测试范围不同。实际测试数量及结果以 [w3_test_results.json](../../reports/w3_test_results.json) 和 [日志](../../reports/w3_test_results.log) 为准。核心用例文件为 [test_w3_cleaning.py](../../tests/test_w3_cleaning.py)、[test_w3_workflow.py](../../tests/test_w3_workflow.py)。

## 3. 换电脑或从干净依赖环境运行

依赖要求是 Python 3.12。核心依赖锁定在 [requirements_w3.txt](../../requirements_w3.txt)；Notebook执行/导出额外依赖在 [requirements-w3-notebook.txt](../../requirements-w3-notebook.txt)，后者包含核心依赖。

在新电脑已经安装 Python 3.12、位于项目根目录时，可创建本机环境：

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements_w3.txt
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --verify-reproducibility --skip-notebook
```

需要完整 Notebook 时再安装并运行：

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-w3-notebook.txt
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --verify-reproducibility
```

原始数据不会随着 Git 仓库上传。先按 [data/raw/README.md](../../data/raw/README.md) 与 [data_manifest.csv](../../reports/tables/data_manifest.csv) 准备经登记的数据；默认Telco输入是 `data/raw/telco_customer_churn/WA_Fn-UseC_-Telco-Customer-Churn.csv`。当前工作流也核对 W1 登记的原始文件完整性，不能仅复制一个处理后CSV就宣称完成原始输入复现。

不要跨电脑复制 `.venv` 后就认为环境可移植。复现验收时“新进程”只表示重新启动Python；“干净环境”表示重新创建隔离环境并安装依赖，两者分别记录。当前正式隔离验证证据见 [w3_clean_environment_verification.json](../../reports/w3_clean_environment_verification.json)。

## 4. 配置和自定义输出

查看参数：

```powershell
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --help
```

| 参数 | 用途 |
|---|---|
| `--config` | 默认 `configs/w3_cleaning.json`；包含规则版本、来源哈希、字段/类别和预处理合同 |
| `--input` | 指定项目内经登记的输入，必须符合配置中的 `expected_sha256`；外部输入在写出前被拒绝 |
| `--output-dir` | 客户级数据输出，限项目 `data/processed/` 或 `.cache/` |
| `--model-dir` | 预处理器输出，限项目 `models/` 或 `.cache/` |
| `--reports-dir` | 报告/汇总证据输出，限项目 `reports/` 或 `.cache/` |
| `--seed`、`--test-size` | 示例分层划分参数；默认42、0.2，不是W5正式切分 |
| `--verify-reproducibility` | 从不同工作目录启动新进程比较业务产物 |
| `--skip-notebook` | 只执行核心工作流，不生成/执行Notebook |

上述相对路径全部以脚本所在的项目根目录解析，与终端当前目录无关。若从任意目录调用，先将 `$projectRoot` 改为本机仓库绝对路径：

```powershell
$projectRoot = 'C:\path\to\your\repository'
& "$projectRoot\.venv\Scripts\python.exe" `
  "$projectRoot\scripts\run_week3.py" `
  --config configs/w3_cleaning.json --verify-reproducibility --skip-notebook
```

想保留一份独立实验输出，可以在项目根目录运行：

```powershell
& .\.venv\Scripts\python.exe .\scripts\run_week3.py `
  --output-dir .cache/w3-example/data `
  --model-dir .cache/w3-example/model `
  --reports-dir .cache/w3-example/reports `
  --seed 42 --test-size 0.2 --verify-reproducibility --skip-notebook
```

数据、模型、报告三个输出目录必须不同，而且不能互相包含。输入文件必须位于项目内，不能放在任何输出目录内。路径会先解析实际位置，不能通过链接绕到 `data/raw` 或源代码目录。换数据版本时将原始文件放入 `data/raw/`，同时更新 `reports/tables/data_manifest.csv` 与配置预期哈希、必要合同；不能只改一个文件名。

Notebook 会嵌入生成时本次实际配置和输入路径，包括自定义种子与切分参数；输出始终在项目 `notebooks/`。独立实验可加 `--skip-notebook` 避免更新主交付Notebook，以独立报告目录内的该次JSON/CSV为准。如果执行Notebook，需核对内嵌配置与对应运行，不能把不同运行的结果混为同一次证据。

## 5. 产物清单与数量

当前 [运行元数据](../../reports/w3_run_metadata.json) 记录：7,043×25清洗主表、22个X输入字段、49列编码输出；示例训练5,634行、验证1,409行。质量规则的数量和passed/documented状态见 [质量表](../../reports/tables/w3_quality_checks.csv)。清洗主表保留11个未知累计费用，数值矩阵无非有限值。

| 位置 | 内容 |
|---|---|
| `src/data/clean.py` | 原始读取、严格合同、清洗变换与4个追踪标记 |
| `src/data/preprocess.py` | X/y/ID分离、特征白名单、训练内预处理和数值检查 |
| `src/data/w3_workflow.py` | 真实数据对账、质量证据、矩阵/预处理器输出 |
| `scripts/run_week3.py` | 参数解析、输出约束、新进程复现和Notebook编排 |
| `scripts/test_week3.py` | 运行全部W3核心测试并写JSON/日志及代码指纹 |
| `configs/w3_cleaning.json` | 冻结的配置、原始哈希、字段/类别字典 |
| `data/processed/w3/` | 主表、缺失追踪、成员索引、X/y/ID训练/验证数据，共9份客户级CSV |
| `models/w3/` | `preprocessor.joblib`与`feature_names.json`，不是分类模型 |
| `reports/tables/w3_*.csv` | 8份运行汇总表，另有独立的20项来源阅读索引 |
| `notebooks/03_cleaning.ipynb`、`.html` | 5个代码单元的Notebook及离线阅读版 |
| `reports/w3_cleaning_rules.md`、`feature_engineering_design_v1.md` | 清洗规则与特征设计交付 |
| `reports/w3_cleaning_report.md` | 运行器自动生成的本次配置、实测前后变化、限制及证据入口 |

两个新进程比较的是9份客户级CSV加8份汇总表，共17份业务文件。运行时间、解释器路径等会变化的元数据不当作业务文件一致性指标。来源阅读索引记录实施前读取的13份README及7份需求/交接文件，共20项，其指纹表示读取当时版本。

## 6. 怎么判断运行成功

首先看命令退出码和最后的JSON状态，然后核对文件内容：

| 证据 | 检查内容 |
|---|---|
| [w3_verification.json](../../reports/w3_verification.json) | 总体status、quality_rules_failed、reproducibility状态、notebook状态及明确限制 |
| [w3_run_metadata.json](../../reports/w3_run_metadata.json) | 数据来源、规则/配置、依赖、示例划分、17份业务指纹、输入不变与训练统计核验 |
| [w3_test_results.json](../../reports/w3_test_results.json) | 独立核心测试实际用例数、执行命令及结果 |
| [w3_clean_environment_verification.json](../../reports/w3_clean_environment_verification.json) | 隔离依赖环境创建、安装和实际运行范围 |
| [w3_before_after.csv](../../reports/tables/w3_before_after.csv) | 客户数/ID/标签、缺失和关键业务状态前后对账 |
| [w3_quality_checks.csv](../../reports/tables/w3_quality_checks.csv) | 每条规则的结果，不能只看一句“已清洗” |

未知类别、错误金额、重复ID、缺失标签、服务逻辑冲突等应导致明确失败。失败表示阻止错误继续流入后续步骤，不应通过手工删报错客户、随意填0或改标签让命令“变绿”。

2026-09-16 最终测试在主环境与隔离环境均执行52项，其中51项通过，1项因Windows权限无法创建单文件符号链接而跳过。目录junction和hardlink实际测试通过；跳过项不能当作通过。详细范围以JSON和日志为准。

## 7. 下游调用与不能省略的边界

`TelcoCleaner` 当前接受含真实Churn的21列历史原表，或完整25列清洗表。它不直接接受去掉Churn后的20列原表。不要为没有标签的新客户编造Churn来迁就接口。

`split_xy()` 对25列清洗表再次验证后，返回22列X、y、ID。预处理器的 `transform(X)` 只需要这个已规范化的22列X，不需要ID和标签，因此没有标签的、已按同一合同规范化的预测特征也可转换。后续真实上线若从20列无标签原表读取，需要另设计并测试无标签清洗入口。

49列是3个缩放数值、43个独热列和3个标记。它不是W4最终至少50项候选特征，也不表示49项独立商业结论。正式特征扩展需更新白名单、登记和测试；正式切分需要重新fit。保存好的W3预处理器仅对应本周示例训练数据。

12项真实时间特征已完成设计，当前Telco无真实事件数据，实际计算为0。累计金额11个未知值仍在主表，原始“零缺失”的字面要求不能通过这一主表全额申报；只有示例数值矩阵经过训练内插补后无NA。W2缺失地区、行业、真实订阅类型的限制继续保留。

## 8. 常见问题

| 现象 | 处理 |
|---|---|
| 找不到原始CSV | 查看默认数据路径和来源清单，准备原始数据；不要把处理后文件冒充输入 |
| 输入哈希不符 | 确认下载版本、文件是否被Excel重保存或手改；若确实换版，先更新来源与合同 |
| 提示缺少Notebook包 | 安装可选Notebook依赖，或使用 `--skip-notebook` 完成核心流程 |
| 自定义路径被拒绝 | 使用各自允许目录或 `.cache/` 的不同子目录，避免相同/嵌套输出和原始输入落在输出内 |
| 显示未知类别/服务冲突 | 查具体字段和行位置，核对合法类别及原始记录；不要静默改成0 |
| 清洗后仍有11个空金额 | 这是有据保留的未知值；查看缺失追踪与规则，不能当成清洗漏做 |
| 想用预处理器直接预测流失 | 本周仅交预处理器；分类模型是后续W5及之后任务 |
