# 本地模型

模型二进制由 Git 忽略，不包含在公开发布 ZIP 中。本机整理副本已放入以下原有模型，字节保持不变：

| 文件 | 用途 |
|---|---|
| `w7/churn_runtime.zip` | 冻结 XGBoost 推理，内含 UBJ、预处理参数和校验清单 |
| `w8/segmentation.joblib` | 冻结分群、训练预处理参数和月费规则 |

克隆仓库后可从可信的原项目目录恢复：

```powershell
python scripts/restore_local_artifacts.py --source "<原项目目录>"
```

恢复脚本只复制 `configs/artifacts.json` 列出的两个文件，逐一核对 SHA-256，不覆盖内容不同的现有文件。分群文件含拟合状态和训练核心点，只在本地使用。`joblib`/`pickle` 只能加载可信来源，不能用于导入任意外部模型。

若没有原项目或获授权提供的工件，仍可运行默认测试、阅读聚合成果和执行风险分层示例；冻结模型推理需要先取得这些工件。
