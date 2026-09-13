# 从零开始实现 Azure 客户流失预测与 CLV 提升项目

## 这份指南要带你做到什么

即使没有数据分析基础，你也可以按本文逐步完成一个可运行的最小项目（MVP）：

```text
读入客户数据 -> 找出谁可能流失 -> 解释可能原因
                     -> 估算客户未来价值
                     -> 选择留存行动并计算收益
```

最终再把 MVP 升级成项目 brief 要求的完整版本：时间切分、50 个以上特征、模型调优、客户分群、BG/NBD 或 Gamma-Gamma CLV、因果/A-B 测试模拟和 Azure 部署。

本文中的公开 Telco 数据只是练习用代理数据，不是微软内部 Azure 数据。没有真实来源的虚拟机时长、存储量、API 调用等字段必须标成“模拟/教学字段”，不能把练习结果写成微软客户事实。

## 1. 先弄懂 10 个词

| 词 | 通俗解释 |
| --- | --- |
| 客户流失（churn） | 客户取消服务、停止续费，或按事先约定的规则被视为离开 |
| 标签（label） | 机器学习要猜的答案，本项目通常是 `churn=1`（会流失）或 `0`（不会流失） |
| 特征（feature） | 用来猜答案的线索，例如合同类型、使用量、月费和工单数 |
| EDA | 探索性数据分析：先用表格和图了解数据，再决定怎么建模 |
| 训练/验证/测试集 | 训练集学规则，验证集选方案，测试集只在最后检查一次 |
| 数据泄漏 | 把预测时还不知道的信息偷偷放进特征，结果会虚高、上线会失效 |
| 召回率（Recall） | 真会流失的人中，模型找出了多少 |
| 精确率（Precision） | 模型判为高风险的人中，真的会流失多少 |
| AUC-ROC | 模型把会流失客户排在不会流失客户前面的整体能力，越接近 1 越好 |
| CLV/LTV | 一个客户从现在到未来可能带来的价值；本指南统一写作 CLV |

再记住三个词：

- **SHAP**：把模型的预测拆成“哪些因素把风险推高或拉低”，帮助业务人员理解原因。
- **RFM**：用最近一次活跃时间（Recency）、活跃/交易频率（Frequency）和金额（Monetary）描述客户价值。
- **A/B 测试**：把相似客户随机分成行动组和对照组，比较行动带来的增量效果。

## 2. 两条实现路线

不要一开始就安装所有高级库。先完成小闭环，再增加复杂度。

| 路线 | 数据和内容 | 适合什么时候 |
| --- | --- | --- |
| MVP | Telco 静态 CSV；清洗、EDA、逻辑回归/树模型、SHAP、代理 RFM、风险-价值矩阵 | 第一次练习，先确认代码能跑通 |
| 进阶版 | 带日期的账号快照、交易、工单和真实云资源使用数据；时间切分、BG/NBD/Gamma-Gamma、因果/A-B、Azure 任务调度 | 已经跑通 MVP，准备满足 PDF 的完整验收要求 |

项目 brief 的目标线是：基线 AUC-ROC 至少 0.75，优化后 AUC-ROC 至少 0.88、F1 至少 0.80，至少 3 个细分市场表现稳定，最终模拟推荐 ROI 至少 300%。这些是验收目标，不是保证值；不得用泄漏、篡改测试集或反复调阈值来“凑分”。

### 2.1 零基础最低先修

不需要先学完整本数学或 Python 教材。先会下面这些动作就能开始：

| 要会的动作 | 你会用在哪里 |
| --- | --- |
| 变量、列表、函数和 `if` | 写清洗规则和可复用函数 |
| `DataFrame` 的筛选、排序、`groupby`、`merge` | 读取客户和工单数据 |
| 数字、字符串、缺失值和日期 | 修复类型、计算窗口特征 |
| SQL 的 `SELECT`、`WHERE`、`GROUP BY`、`JOIN` | 从数据仓库取数 |

先在 Notebook 运行一个极小例子，确认你理解“输入 -> 处理 -> 输出”：

```python
customers = [{"plan": "月付", "churn": 1}, {"plan": "年付", "churn": 0}]
monthly = [row for row in customers if row["plan"] == "月付"]
print(len(monthly), monthly[0]["churn"])
```

如果使用 SQL 数据源，同一个问题可以写成：

```sql
SELECT Contract, AVG(CASE WHEN Churn = 'Yes' THEN 1.0 ELSE 0.0 END) AS churn_rate
FROM customers
GROUP BY Contract;
```

遇到不懂的语法时，先查这一行的输入类型、输出类型和一条实际样例，不要整段盲目复制。

## 3. 第一步：准备环境

### 3.1 Windows + VS Code

在 PowerShell 中执行以下命令。`py -3.10` 也可以替换为本机已安装的 Python 3.10 或更高版本：

```powershell
mkdir azure-churn-clv
cd azure-churn-clv
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pandas numpy matplotlib seaborn plotly scikit-learn imbalanced-learn jupyterlab joblib
```

确认命令行前面出现 `(.venv)`，再检查版本：

```powershell
python --version
python -c "import pandas, sklearn; print(pandas.__version__, sklearn.__version__)"
```

如果 PowerShell 暂时禁止激活脚本，只对当前窗口放行即可，关闭窗口后设置会恢复：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3.2 可选的进阶库

MVP 跑通后再安装：

```powershell
python -m pip install xgboost lightgbm catboost optuna shap lime scipy statsmodels dowhy lifetimes sqlalchemy
```

如果某个库在你的系统上安装失败，先记录 Python、操作系统和库版本；可以改用 Google Colab 或 GitHub Codespaces。项目 brief 列出的参考下限包括 Python 3.10+、Pandas 2.2+、NumPy 1.26+、Scikit-learn 1.5+ 等，实际应以一组彼此兼容的版本为准。PySpark 只在数据量确实较大时再安装，普通练习不需要它。

### 3.3 让项目可复现

`python -m jupyter lab` 会启动本地 Notebook 页面，浏览器打开终端显示的地址即可。先在 VS Code 中新建名为 `.gitignore` 的文件，再写入下面内容；它至少忽略虚拟环境、原始数据和密钥：

```powershell
python -m jupyter lab
```

```text
.venv/
data/raw/
*.env
__pycache__/
```

如果已安装 Git，并且已经在 VS Code 中新建 `README.md` 和 `.gitignore`，可以在项目根目录运行：

```powershell
git init
git add README.md .gitignore
git commit -m "初始化项目结构"
```

首次提交前检查 `git status`，确认没有把客户数据或 API 密钥加入暂存区。

### 3.4 建议的目录

```text
azure-churn-clv/
├─ data/raw/          # 下载的原始数据，只读
├─ data/processed/    # 清洗和特征后的数据
├─ notebooks/         # 一步一步探索
├─ src/data/          # 读取和质量检查
├─ src/features/      # 特征工程
├─ src/models/        # 训练和评估
├─ src/clv/           # 分群、CLV 和收益模拟
├─ models/            # 保存的模型
├─ reports/           # 图表和报告
├─ dashboard/         # Power BI 导出文件
└─ tests/             # 数据和代码测试
```

不想逐个新建文件夹时，可以在项目根目录执行：

```powershell
New-Item -ItemType Directory -Force -Path "data/raw","data/processed","notebooks","src/data","src/features","src/models","src/clv","models","reports","dashboard","tests"
```

在 README 中记录数据下载日期、运行命令、随机种子、库版本和已知限制。`data/raw` 中如果有个人信息，不要提交到 GitHub。

## 4. 第二步：下载并认识数据

PDF 推荐三个 Kaggle 数据集：

1. [Telco Customer Churn](https://www.kaggle.com/datasets/blastchar/telco-customer-churn)：7,043 个客户，包含基础画像、服务订阅、月费、总费用和 `Churn`。
2. [Customer Support Tickets](https://www.kaggle.com/datasets/suraj520/customer-support-ticket-dataset)：工单明细，可聚合出工单量、解决时长和服务体验。
3. [SaaS Customer Churn](https://www.kaggle.com/datasets/wearetenet/saas-churn-rate-statistics-dataset)：用于对比 SaaS 与云服务的订阅和使用模式。

先手动从 Kaggle 下载第一个 CSV 放入 `data/raw/`，最容易排查权限和文件名问题。Kaggle API 也可以使用，但 API 凭据只能放在用户目录或环境变量中，不能写进仓库。

### 4.1 先写数据字典

打开 CSV 前先回答四件事：一行代表谁？哪一列是客户 ID？哪一列是标签？每个特征在什么时候可知？可以用下面的表格开始：

| 字段 | 类型 | 含义 | 预测时可用吗 | 备注 |
| --- | --- | --- | --- | --- |
| `customerID` | 字符串 | 客户唯一标识 | 仅用于追踪，不直接训练 | 去重键 |
| `tenure` | 数值 | 已服务月数 | 是 | 检查是否非负 |
| `Contract` | 类别 | 合同类型 | 是 | 例如月付/年付 |
| `MonthlyCharges` | 数值 | 月度收费 | 是 | 记录币种 |
| `TotalCharges` | 数值 | 累计收费 | 是，但要注意观察期 | 原始文件可能有空格 |
| `Churn` | Yes/No | 是否流失 | 这是标签 | 不能放入特征 |

Telco 是单个时间截面的公开数据，通常没有 `snapshot_date`、API 次数和云资源消耗等字段。没有日期时可以完成 MVP，但不能假装已经完成严格的时间序列验证。

### 4.2 Telco 到 Azure 的字段映射

| Telco 字段 | 可作为 Azure 练习中的什么代理 | 不能据此推出什么 |
| --- | --- | --- |
| `Contract` | 订阅/合同类型 | 不能代表 Azure 的全部计费方案 |
| `InternetService`、其他服务列 | 服务类型和功能采用 | 不能代表真实云资源架构 |
| `MonthlyCharges`、`TotalCharges` | 月收入和累计收入代理 | 不能直接当作 Azure 毛利 |
| `tenure` | 账号服务年限 | 没有续约日期和快照就不能算真实趋势 |
| 工单数据聚合字段 | 服务体验代理 | 必须有统一客户 ID 和时间窗口 |
| VM 时长、存储量、API 次数、地区、行业 | Telco 原表没有，需要另行获取或模拟 | 模拟字段不能写成真实微软数据 |

合并工单前先按客户和观察窗口聚合，再与客户表连接，并使用 `validate="one_to_one"` 或 `many_to_one` 检查连接关系。直接把每一张工单拼到客户表会让客户行数膨胀，流失率和收入都会被重复计算。

## 5. 第三步：跑通第一个基线

新建 `notebooks/01_baseline.ipynb`，或在 VS Code 的 Python 文件中逐段运行下面的代码。

下面先用一个相对路径跑通流程；到第 3 周整理成脚本时，再用命令行参数或配置文件传入路径，避免把路径写死。

### 5.1 读取、检查和清洗最小内容

```python
from pathlib import Path
import pandas as pd

DATA = Path("data/raw/WA_Fn-UseC_-Telco-Customer-Churn.csv")
if not DATA.exists():
    # 文件名可能略有不同，先列出实际文件名再修改 DATA
    print(list(Path("data/raw").glob("*.csv")))
    raise FileNotFoundError(DATA)

df = pd.read_csv(DATA, encoding="utf-8-sig")
df.columns = df.columns.str.strip()

# TotalCharges 常含空字符串；先转成数值，无法转换的值变成缺失
df["TotalCharges"] = pd.to_numeric(df["TotalCharges"], errors="coerce")

print("行列数:", df.shape)
print(df.head())
print(df.dtypes)
print(df.isna().sum().sort_values(ascending=False).head(10))
print("重复行:", df.duplicated().sum())
print("客户 ID 重复:", df["customerID"].duplicated().sum())
print("流失比例:", df["Churn"].value_counts(normalize=True))
```

先观察再处理。缺失、重复和异常值要分别记录数量、原因和处理方式；不要一看到缺失就整列删除。

### 5.2 做一个不会泄漏的预处理和逻辑回归

下面的 `Pipeline` 会把填补、标准化和独热编码都放在训练流程中。这样测试集不会参与计算中位数或类别映射，是初学者最重要的防泄漏习惯。

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

target = df["Churn"].astype("string").str.strip().map({"Yes": 1, "No": 0})
if target.isna().any():
    raise ValueError("Churn 中有未映射的类别，请先检查取值")

X = df.drop(columns=["Churn", "customerID"])
y = target.astype("int8")

numeric_cols = X.select_dtypes(include="number").columns.tolist()
categorical_cols = X.select_dtypes(exclude="number").columns.tolist()

numeric_pipe = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler()),
])
categorical_pipe = Pipeline([
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("onehot", OneHotEncoder(handle_unknown="ignore")),
])
preprocess = ColumnTransformer([
    ("num", numeric_pipe, numeric_cols),
    ("cat", categorical_pipe, categorical_cols),
])

# Telco 是静态横截面，以下随机分层切分只用于 MVP。
# 有真实事件日期时，必须改成按时间的 train/validation/test 切分。
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, stratify=y, random_state=42
)

baseline = Pipeline([
    ("preprocess", preprocess),
    ("model", LogisticRegression(max_iter=2000, class_weight="balanced")),
])
baseline.fit(X_train, y_train)
prob = baseline.predict_proba(X_test)[:, 1]
pred = (prob >= 0.5).astype("int8")

print("ROC-AUC:", round(roc_auc_score(y_test, prob), 4))
print("PR-AUC:", round(average_precision_score(y_test, prob), 4))
print(confusion_matrix(y_test, pred))
print(classification_report(y_test, pred, digits=3))
```

你应当能看到 ROC-AUC、PR-AUC、Precision、Recall、F1 和混淆矩阵。数值会因数据版本和库版本略有差异；不要直接复制别人的分数。

### 5.3 为什么不能永远用 0.5

如果客服团队每天只能联系 200 个客户，应该按资源容量选择排名最高的 200 个，而不是机械地把概率大于 0.5 的人全部联系。阈值要结合：

```text
一次误联系的成本、漏掉一个流失客户的损失、团队可处理人数、客户体验风险
```

在验证集上测试多个阈值，记录 Precision、Recall、F1、top-k 召回和预计成本；测试集只在方案锁定后使用一次。

## 6. 第四步：数据质量和 EDA

### 6.1 数据质量清单

每次新数据进来都检查：

1. 文件是否完整，列名和类型是否符合数据字典。
2. 客户 ID 是否唯一，是否有重复快照。
3. 缺失率、空字符串、无穷大和异常编码。
4. 数值范围，例如费用不能为负、比例应在 0-1 之间。
5. 类别拼写是否一致，例如 `Monthly` 和 `monthly` 是否其实是同类。
6. 标签比例、标签生成时间和预测窗口是否改变。
7. 任何特征是否在标签发生后才产生。
8. 训练集和上线数据的分布是否明显漂移。

把检查结果输出成 `reports/data_quality.csv` 或 Markdown 表格，并保留原始数据只读副本。PDF 第 1-3 周要求“发现所有缺失、异常和重复值”，这里的“所有”意味着有可审计的规则和日志，而不是简单打印几行。

### 6.2 EDA 的正确顺序

每张图先写一个问题，再写一句结论。例如：

| 问题 | 可用图表 | 可能的行动 |
| --- | --- | --- |
| 总体流失比例是多少？ | 流失计数图、比例图 | 判断类别不平衡和基线 |
| 合同类型是否有差异？ | 合同 × 流失率柱状图 | 设计续约触达 |
| 服务年限是否影响流失？ | `tenure` 箱线图/分箱图 | 识别新客上手阶段 |
| 月费高低是否关联流失？ | 月费直方图、分位数图 | 检查价格敏感度 |
| 哪些服务组合风险更高？ | 热图、堆叠柱状图 | 设计套餐或培训 |
| 工单体验是否相关？ | 工单量 × 流失率、解决时长箱线图 | 优先技术支持 |

为了满足 brief 的第 2 周目标，至少覆盖 15 个不同维度，例如地区、行业、订阅类型、合同、支付方式、服务数量、使用频率、使用深度、月费、累计费用、服务年限、工单量、解决时长、自动续费、人口统计等。图表数量不是目的；每张图都要关联假设、结论和下一步验证。

至少写下 5 个可验证假设：

1. 月付合同的流失率高于年付合同。
2. 最近 30 天使用量下降的客户更容易流失。
3. 高工单量或长解决时长与流失相关。
4. 新客户在上手期的流失风险更高。
5. 高月费但低功能采用的客户具有较高风险。

这些只是待检验假设，不是结论。Power BI 仪表板可以提供地区、行业、订阅类型等筛选器，但筛选器不应改变标签定义或偷偷排除异常客户。

### 6.3 把结果放进 Power BI

初学者不必一开始连接云数据库。先把 Python 导出的 `customer_scores.csv` 或汇总表导入 Power BI Desktop：

1. 选择“获取数据 -> 文本/CSV”，检查字段类型和日期格式。
2. 添加流失客户数、流失率、平均 CLV、预计增量毛利等卡片。
3. 添加合同/订阅、地区、行业、风险等级的切片器；用柱状图、散点图和趋势图回答前面列出的假设。
4. 点击每个筛选器，确认图表、客户明细和总计同步变化，再截图并记录数据版本。

Telco 没有地区和行业列时，不要伪造筛选器；可以改用现有字段，或在取得合法扩展数据后再满足 PDF 的筛选要求。

## 7. 第五步：特征工程

### 7.1 四大类特征

| 类别 | 例子 | 计算时要注意 |
| --- | --- | --- |
| 行为 | 近 7/30/90 日 API 次数、活跃天数、会话深度、采用的功能数、失败部署数 | 必须说明统计窗口 |
| 价值 | 月收入、ARPU、毛利、折扣、增长率、支持成本 | 收入和利润不要混用 |
| 时间 | 服务年限、距最近活跃天数、续约剩余天数、滚动均值/标准差/斜率 | 只使用截止日之前的记录 |
| 人口/合同 | 地区、行业、企业规模、合同类型、支付方式、自动续费 | 类别值要统一编码 |

还可以增加交互和聚合特征，例如“合同类型 × 支付方式”“价格 × 服务年限”“工单数 ÷ 活跃月数”“账号下订阅数”。PDF 要求最终至少 50 个特征，但先做少量、能解释的特征更容易发现错误。

### 7.2 一个可复用的基础函数

```python
import pandas as pd
import numpy as np

def add_basic_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    binary_service_cols = [
        c for c in ["PhoneService", "OnlineSecurity", "OnlineBackup",
                    "DeviceProtection", "TechSupport", "StreamingTV",
                    "StreamingMovies"]
        if c in out.columns
    ]
    if binary_service_cols:
        out["service_count"] = (out[binary_service_cols].eq("Yes")).sum(axis=1)
    if "InternetService" in out.columns:
        out["service_count"] = out.get("service_count", 0) + out["InternetService"].ne("No").astype(int)

    if {"TotalCharges", "tenure"}.issubset(out.columns):
        out["avg_monthly_charge"] = out["TotalCharges"] / out["tenure"].replace(0, np.nan)
        out["avg_monthly_charge"] = out["avg_monthly_charge"].replace([np.inf, -np.inf], np.nan)

    if {"MonthlyCharges", "TotalCharges"}.issubset(out.columns):
        out["total_to_monthly_ratio"] = out["TotalCharges"] / out["MonthlyCharges"].replace(0, np.nan)

    return out

df_features = add_basic_features(df)
```

Telco 没有真正的每日使用记录，因此不能从它凭空计算“近 30 日 API 趋势”。有事件表后再计算滚动统计：

```python
events = events.sort_values(["customer_id", "event_time"])
events["api_30d"] = (
    events.set_index("event_time")
          .groupby("customer_id")["api_calls"]
          .rolling("30D").sum()
          .reset_index(level=0, drop=True)
          .to_numpy()
)
```

实际项目中应把日期时区、重复事件和窗口边界写清楚，并用单元测试验证某个客户的手算结果。

### 7.3 特征选择和共线性

至少比较三种方法：互信息、L1 正则逻辑回归、树模型/Permutation Importance；必要时再用 RFECV 或 PCA。用相关系数矩阵和 VIF 检查高度相关的特征。不要只因为某个特征重要性低就删除它，也不要在全量数据上先选择特征再切分，否则会泄漏测试信息。聚类需要降维时，记录 PCA 的解释方差和可逆性。

## 8. 第六步：正确切分数据和处理不平衡

### 8.1 有日期时的时间切分

流失预测的现实场景是“用过去预测未来”，所以应按时间排序，例如：旧数据 60% 训练、接下来 20% 验证、最新 20% 测试。训练期间可以使用 `TimeSeriesSplit`，但每个折都必须保持时间先后。

Telco 是静态快照，没有可靠日期；MVP 的随机分层切分只是教学妥协，报告里要明确这一限制。不要给每行随意生成日期后声称完成了时间验证。

### 8.2 三种以上不平衡方案

至少做一个可比较的实验表：

| 方案 | 何时使用 | 主要风险 |
| --- | --- | --- |
| `class_weight="balanced"` | 逻辑回归、树模型的快速基线 | 可能牺牲精确率 |
| SMOTE | 训练样本较少且特征为数值/已编码 | 只能在训练折内生成，类别特征要谨慎 |
| ADASYN | 希望更关注难分类的少数类 | 噪声也可能被放大 |
| 随机欠采样/过采样 | 资源有限或作为对照 | 可能丢失信息或过拟合 |

绝不能在切分前对全量数据 SMOTE。使用交叉验证时，采样器必须放在每个训练折内部，例如：

```python
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.linear_model import LogisticRegression

smote_model = ImbPipeline([
    ("preprocess", preprocess),
    ("smote", SMOTE(random_state=42)),
    ("model", LogisticRegression(max_iter=2000)),
])
smote_model.fit(X_train, y_train)
```

Telco 数据规模较小，独热后使用 SMOTE 便于演示；大规模或含大量类别变量时，应研究 `SMOTENC`、类别权重或模型原生处理方式。

### 8.3 不只看 ROC-AUC

流失通常是少数类，报告以下指标：ROC-AUC、PR-AUC、Precision、Recall、F1、混淆矩阵、概率校准/Brier 分数、top-k 召回和不同细分市场的结果。客服容量有限时，top-k 召回往往比整体准确率更有用。

## 9. 第七步：从基线升级到高级模型

建议按这个顺序增加复杂度：

1. 逻辑回归：容易解释，作为基准。
2. 决策树或随机森林：能表示非线性关系。
3. XGBoost、LightGBM、CatBoost：处理复杂交互，比较速度、类别特征支持和稳定性。
4. Stacking 或 Blending：只有当单模型和验证设计已经可靠时再尝试。

例如，用同一套预处理快速建立决策树对照：

```python
from sklearn.tree import DecisionTreeClassifier

tree_baseline = Pipeline([
    ("preprocess", preprocess),
    ("model", DecisionTreeClassifier(
        max_depth=5, class_weight="balanced", random_state=42
    )),
])
tree_baseline.fit(X_train, y_train)
tree_prob = tree_baseline.predict_proba(X_test)[:, 1]
print("Tree ROC-AUC:", round(roc_auc_score(y_test, tree_prob), 4))
```

确认基线和评估函数可靠后，再把最后一层替换成 `XGBClassifier`、`LGBMClassifier` 或 `CatBoostClassifier`。不要同时更换数据切分、特征、阈值和模型，否则无法知道性能变化来自哪里。

用 Optuna 或 Hyperopt 调参时，只使用训练集和验证集；测试集锁定到最后。时间数据使用时间交叉验证，随机数据也要固定随机种子。最终至少按地区、行业、订阅类型中的三个细分市场检查 AUC、Recall、校准和样本量，不能只报告总体平均值。

PDF 的 AUC >= 0.88、F1 >= 0.80 是挑战目标。若公开代理数据达不到，应解释数据、标签、特征和容量限制，保留真实结果。

## 10. 第八步：解释模型并形成风险评分

### 10.1 全局和局部解释

对树模型可用 SHAP：

```python
import shap

# tree_model 是已经训练好的树模型；X_encoded 是按训练流程得到的数值矩阵
explainer = shap.TreeExplainer(tree_model)
shap_values = explainer.shap_values(X_encoded_sample)
shap.summary_plot(shap_values, X_encoded_sample, show=False)
```

报告两类结果：

- 全局前 10 个驱动因素：哪些因素总体上推高或降低风险。
- 单客户解释：例如“近 30 日使用量下降”和“月付合同”把该客户风险推高多少。

LIME 可以作为局部解释的对照。特征名必须还原成人能读懂的业务名称，不能只显示 `x0`、`x17`。解释是模型关联，不等于已经证明原因；策略因果仍需实验。

### 10.2 风险等级

先在验证集校准概率，再根据业务容量和成本定义区间。例如：

```python
scored["risk_band"] = pd.cut(
    scored["churn_probability"],
    bins=[-float("inf"), 0.30, 0.60, float("inf")],
    labels=["低风险", "中风险", "高风险"],
    right=False,
)
```

`0.30` 和 `0.60` 只是示例，不是通用标准。应在报告中写明每个区间的真实流失率、覆盖人数、联系容量、预期成本，并在新月份监控校准是否变差。

## 11. 第九步：客户分群和风险-价值矩阵

### 11.1 RFM 的直觉

对交易或事件表按客户聚合：

- Recency：距最近一次活跃/购买有多久，越近通常越好。
- Frequency：在观察窗口内活跃、购买或调用的次数。
- Monetary：收入、毛利或贡献金额。

订阅云服务不一定有“购买次数”，可以把 Frequency 改成会话/API/活跃天数，把 Recency 改成距最近使用，把 Monetary 改成毛利；名称和替代规则要在报告中说明。Telco 静态快照没有真实交易日期，RFM 只能做代理分群，不能冒充标准 RFM。

### 11.2 K-Means 与 DBSCAN

先对偏态金额/次数做 `log1p`，再标准化。K-Means 用肘部图和 silhouette score 选择 `k`；DBSCAN 调 `eps`、`min_samples`，并检查噪声比例和不同月份的稳定性。至少比较两种算法，并给每个簇起业务名称，例如“高价值高活跃”“低价值沉默”。

### 11.3 四象限

把客户的流失概率和 CLV（或预期利润）分别按业务阈值切分：

| | 低风险 | 高风险 |
| --- | --- | --- |
| 高价值 | 维护关系、发现增购机会 | **优先挽留，通常是核心群** |
| 低价值 | 自动化服务、控制成本 | 低成本触达或观察 |

计算高价值高风险群实际贡献的利润占比。PDF 希望核心群贡献总利润 60% 以上；如果数据不支持这个比例，必须报告实际值和原因，而不是调整分位点直到“达标”。

## 12. 第十步：计算 CLV

### 12.1 先选适合数据的模型

| 数据情况 | 推荐做法 |
| --- | --- |
| 只有 Telco 这类单次静态快照 | 透明的订阅 CLV 简化式，并做敏感性分析 |
| 有每次交易的日期、频次、观察期和正金额 | Lifetimes 的 BG/NBD + Gamma-Gamma |
| 有账号快照和月度留存/流失历史 | 生存分析或按月留存概率预测，再计算折现 CLV |

BG/NBD 需要 `frequency`、`recency`、`T`；Gamma-Gamma 需要重复购买客户的正金额。Telco 静态快照不满足这些条件，不能为了使用库而强套模型。

### 12.2 订阅 CLV 简化式

一个易懂的有限期公式是：

```text
CLV_i = Σ[t=1..H] P(客户 i 在第 t 月仍活跃)
        × 月收入_i,t × 毛利率 / (1 + 月折现率)^t
        - 支持成本_i - 干预成本_i
```

如果只有一个月度流失概率 `p`，可以用 `P(active at t) = (1-p)^t` 做教学假设；正式项目应从历史快照估计每个客户或群体的留存曲线，并做不同 `p`、毛利率和折现率的敏感性分析。

```python
import numpy as np

def simplified_clv(monthly_revenue, gross_margin, monthly_churn,
                   horizon=12, monthly_discount=0.01, intervention_cost=0.0):
    months = np.arange(1, horizon + 1)
    survival = (1 - monthly_churn) ** months
    discounted_margin = (
        survival * monthly_revenue * gross_margin
        / (1 + monthly_discount) ** months
    )
    return float(discounted_margin.sum() - intervention_cost)
```

“高风险客户留存率提升 10%”的收益应按客户逐一计算：

```text
新增留存人数 × 每位客户预期剩余毛利 - 干预总成本
```

不要把历史累计收费当成未来 CLV，也不要把所有被预测为高风险的人都当成一定会流失。

### 12.3 有交易数据时使用 Lifetimes

满足数据条件后，可以按官方文档拟合 BG/NBD 和 Gamma-Gamma，并在留出期回测：

```python
from lifetimes import BetaGeoFitter, GammaGammaFitter

bgf = BetaGeoFitter(penalizer_coef=0.01)
bgf.fit(summary["frequency"], summary["recency"], summary["T"])

repeat = summary[summary["frequency"] > 0].copy()
ggf = GammaGammaFitter(penalizer_coef=0.01)
ggf.fit(repeat["frequency"], repeat["monetary_value"])

repeat["expected_value"] = ggf.customer_lifetime_value(
    bgf,
    repeat["frequency"],
    repeat["recency"],
    repeat["T"],
    repeat["monetary_value"],
    time=12,
    freq="M",
    discount_rate=0.01,
)
```

不同 Lifetimes 版本的方法参数可能略有差异，运行前查对应版本文档。检查金额是否为正、频次是否符合定义，并将预测期与训练期分开回测。

## 13. 第十一步：把预测转成留存行动

预测分数本身不是业务价值。每个策略都要写出“驱动因素 -> 动作 -> 适用客户 -> 成本 -> 预期增量 -> 指标”。下面是可作为起点的五类示例：

| 可能驱动因素 | 动作 | 适用客户 | 可观测指标 |
| --- | --- | --- | --- |
| 新客使用浅、功能采用少 | 上手辅导、架构健康检查 | 新客且高风险 | 30/90 日留存、功能采用 |
| 使用量或 API 调用持续下降 | 主动联系、用量预警和 FinOps 建议 | 高价值且活跃下降 | 活跃恢复、留存、毛利 |
| 工单多、解决时间长 | 技术专员、SLA 升级和问题复盘 | 工单体验差的客户 | 解决时长、投诉、留存 |
| 价格/合同敏感 | 优化资源配置、套餐或续约方案 | 月付、高费用或即将续约 | 续约率、折扣后毛利 |
| 账单或支付失败 | 账单提醒、支付方式协助 | 有支付异常的客户 | 支付成功、流失率 |

这些是建议模板，不是从 Telco 数据已经证明的因果结论。策略数量至少达到 PDF 要求的 5 种，并为每种策略估算人力、折扣、云资源和机会成本。

## 14. 第十二步：设计 A/B 测试与效果模拟

### 14.1 A/B 测试最小方案

1. 明确合格人群，例如预测为高风险且满足联系同意的客户。
2. 以客户账号为随机化单位，随机分 treatment（执行策略）和 control（保持现状）。同一账号下的订阅不要跨组，避免互相影响。
3. 预先注册主指标（30/90 日留存或续约）、次指标（增量毛利、使用量、投诉）和护栏指标（退订、折扣滥用、服务成本）。
4. 在实验开始前根据基线留存率、最小可检测差异（MDE）、显著性水平 `alpha=0.05` 和 power `0.8` 计算样本量。
5. 按意向治疗原则分析，报告置信区间和缺失原因；不要实验中途反复挑选有利窗口。

样本量可用 `statsmodels` 估算两比例差异：

```python
import numpy as np
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

baseline_rate = 0.70   # 示例：历史 90 日留存率，需替换为真实值
target_rate = 0.75     # 示例：希望检测到的最小改善
effect = proportion_effectsize(baseline_rate, target_rate)
n_each = NormalIndPower().solve_power(
    effect_size=effect, alpha=0.05, power=0.80,
    ratio=1.0, alternative="two-sided"
)
print("每组至少", int(np.ceil(n_each)), "个客户")
```

观察数据中的“接受过策略的人更少流失”只能说明相关性。若不能随机化，应使用 DoWhy、倾向得分等因果方法，并把处理分配、无混杂、稳定性等假设写出来，不能直接宣称策略有效。

### 14.2 模拟策略组合和 ROI

对每个客户或群体估算策略带来的**绝对留存概率提升** `uplift`。例如，留存率从 70% 变成 75%，`uplift=0.05`。在这个定义下，不再额外乘原始流失概率：

```python
scored["incremental_margin"] = (
    scored["uplift"] * scored["remaining_margin"]
)
benefit = scored["incremental_margin"].sum()
cost = scored["strategy_cost"].sum()
roi = (benefit - cost) / cost if cost > 0 else np.nan
```

如果 `uplift` 的定义改成“原本会流失的客户中被挽回的条件比例”，才需要使用 `churn_probability * uplift * remaining_margin`；两种定义不能混用。公式是：`ROI = (增量毛利 - 策略成本) / 策略成本`。限制触达人数、策略重叠和概率上限，避免重复计算同一客户收益。枚举至少 10 个组合，并改变 uplift、成本、毛利率和联系容量做敏感性分析；300% 是 brief 的目标值，不是默认结论。

## 15. 第十三步：保存、部署和监控

### 15.1 保存完整 Pipeline

不要只保存模型而丢掉编码器和填补规则：

```python
import joblib

joblib.dump(baseline, "models/churn_baseline.joblib")
loaded = joblib.load("models/churn_baseline.joblib")
new_prob = loaded.predict_proba(new_customers)[:, 1]
```

上线评分表至少包含：`customer_id`、`churn_probability`、`risk_band`、可读的 `reason_codes`、`score_time`、模型版本和数据版本。只把有明确行动路径的客户交给客服团队。

### 15.2 Azure 方向

可把模型文件和处理后数据放到 Azure Blob Storage，用 Azure Machine Learning 或定时任务批量评分，再把结果供 Power BI 展示。初学者先完成本地批处理即可；使用 Free Tier 时设置预算告警、资源过期标签和清理脚本。上线后监控数据漂移、概率校准、实际流失、策略增量、分群表现和公平性。

## 16. 按 PDF 验收的学习清单

完成一项就打勾，并把证据链接放入 README：

- [ ] 写出至少 8 个业务因素、客户粒度、标签定义和预测窗口。
- [ ] 生成数据质量报告，覆盖缺失、异常、重复和标签比例。
- [ ] 完成至少 15 个有问题和结论的 EDA 图表，Power BI 可按地区/行业/订阅筛选。
- [ ] 清洗脚本可复用、一键运行；时间特征至少 10 个（没有日期时披露限制）。
- [ ] 最终特征覆盖行为、价值、时间、人口统计四类，至少 50 个，并比较 3 种选择法。
- [ ] 按时间切分（若数据有日期），比较 class weight、SMOTE、ADASYN 等至少 3 种方案。
- [ ] 训练逻辑回归/决策树基线，再比较 XGBoost、LightGBM、CatBoost；用验证集调参。
- [ ] 报告 ROC-AUC、PR-AUC、Precision、Recall、F1、校准和至少 3 个细分市场结果。
- [ ] 用 SHAP/LIME 给出全局前 10 个驱动因素和单客户解释，风险区间有业务依据。
- [ ] 比较 K-Means 与 DBSCAN，形成风险-价值四象限并计算利润贡献。
- [ ] 数据满足时使用 BG/NBD/Gamma-Gamma；不满足时使用带假设的简化 CLV。
- [ ] 设计至少 5 个策略、成本表、样本量和 A/B 主次指标；模拟至少 10 个组合并做敏感性分析。
- [ ] 交付可复现仓库、技术报告、PPT 和演示；记录代理数据、模拟字段和所有限制。

## 17. 常见问题排查

| 现象 | 常见原因 | 处理方法 |
| --- | --- | --- |
| `FileNotFoundError` | CSV 文件名或工作目录不对 | `Path("data/raw").glob("*.csv")` 列出实际文件，使用相对路径 |
| `TotalCharges` 变成全是缺失 | 原始值含空格或货币符号 | 先清理字符串再 `pd.to_numeric(errors="coerce")`，检查转换比例 |
| 测试分数异常高、上线骤降 | 把 Churn 后信息或全量统计放进特征 | 以观察截止日重算特征，所有预处理放 Pipeline |
| SMOTE 后结果虚高 | 在切分前采样，或把测试集也采样 | 只在训练折内采样，测试集保持原始分布 |
| 训练/预测类别报错 | 新数据有未见过的类别 | `OneHotEncoder(handle_unknown="ignore")`，并监控新类别 |
| 聚类被金额列支配 | 特征尺度和偏态未处理 | `log1p` 后标准化，检查 silhouette 和簇稳定性 |
| Lifetimes 无法拟合 | 没有交易日期/频次，金额为 0 或负数 | 改用订阅简化式，或先构造合法的交易汇总表 |
| ROI 很高但没有实验支持 | 把预测概率当成干预因果效果 | 用 A/B 或因果设计估计 uplift，并报告不确定性 |
| Azure 账单超预算 | 忘记释放资源或超出 Free Tier | 设预算告警、资源标签和定期清理任务 |

## 18. 你可以先完成的 7 天计划

| 天 | 目标 | 当天应留下的证据 |
| --- | --- | --- |
| 1 | 安装环境、下载 Telco、写数据字典 | 可运行的环境检查和字段表 |
| 2 | 清洗、统计缺失/重复/流失比例 | `data_quality` 输出 |
| 3 | 完成 5-8 张 EDA 图并写结论 | Notebook 和假设列表 |
| 4 | 跑通逻辑回归基线 | AUC、PR-AUC、F1、混淆矩阵 |
| 5 | 增加服务数量、费用比率等特征 | 特征说明和训练日志 |
| 6 | 比较 class weight、SMOTE、树模型 | 对比表和阈值讨论 |
| 7 | 输出风险分层和一个简化 CLV 表 | 客户级评分、四象限草图、限制清单 |

完成这 7 天闭环后，再按 PDF 的 12 周计划逐项扩展。每次只增加一个复杂组件，并保留上一版结果作为可比较的基线。

## 19. 学习资料

项目 brief 推荐 Azure 官方文档、Power BI 学习中心、Azure Machine Learning 文档、Kaggle 客户流失案例、SHAP 教程和 Lifetimes 文档。先掌握 Python 函数、异常处理、模块、NumPy 数组、Pandas 的筛选/`groupby`/`merge`，以及 SQL 的 `SELECT`、`WHERE`、`GROUP BY`、`JOIN` 和窗口函数，再学习高级模型和因果推断，会更容易理解每一步为什么存在。
