# 测试目录

用于保存数据质量规则、清洗逻辑、特征公式、Pipeline 输入输出和指标计算测试。

测试应优先覆盖主键唯一性、标签映射、类型/范围、逻辑冲突、特征泄漏和训练/测试处理边界。

W3 核心测试在 [test_w3_cleaning.py](test_w3_cleaning.py)和[test_w3_workflow.py](test_w3_workflow.py)。推荐从主项目根目录使用留证入口：

```powershell
& .\.venv\Scripts\python.exe .\scripts\test_week3.py
```

该入口发现全部 `test_w3*.py`，运行测试后生成 `reports/w3_test_results.json` 与 `.log`，记录实际用例数、通过/失败/跳过、运行时间和代码/测试指纹。需要直接查看 unittest 输出时，也可运行：

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_w3*.py" -v
```

重点包括空白金额及零年限保留、结构性服务状态、重复/空主键、未知标签/类别、非法数值、输入不变、重复转换、额外字段拒绝、防标签混入、训练内拟合、无标签22列X转换、保存/加载、输出重叠、目录链接与硬链接等边界。实际用例数和结果以 [w3_test_results.json](../reports/w3_test_results.json)及[详细日志](../reports/w3_test_results.log) 为准。

2026-09-16 最终验收执行52项，51项通过、1项因Windows权限无法创建单文件符号链接而跳过；目录junction与hardlink实际测试通过。跳过项不是通过项，不将结果简写为“52项全通过”。

真实数据全流程另运行：

```powershell
& .\.venv\Scripts\python.exe .\scripts\run_week3.py --verify-reproducibility
```

该命令运行质量约束、两次业务 CSV 对账及 Notebook，不等于运行上述所有单元测试。只有核心依赖时可加 `--skip-notebook`。运行范围见 [w3_verification.json](../reports/w3_verification.json)，从重新安装依赖的隔离环境核验见 [w3_clean_environment_verification.json](../reports/w3_clean_environment_verification.json)。不要把“新进程”与“干净依赖环境”混写。
