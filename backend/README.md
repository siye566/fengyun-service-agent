# 空压机售后业务引擎

项目结构、运行步骤及边界见 [仓库说明](../README.md)。

`acs/` 为业务引擎，`tests/` 验证业务规则及企业隔离。评估集移至根目录 `evals/`，三轮实际运行示例移至 `examples/`。历史报告不随仓库发布。企业及设备均使用示例标识，凭证仅通过本地配置提供。

从仓库根目录执行 `python -m pytest -q`、`python examples/demo_service.py` 和 `python evals/run_service_eval.py`。可用 `npm test`、`npm run demo` 和 `npm run eval` 调用同一流程。

模型/MCP 接入需安装本目录 `requirements.txt`；独立 demo、pytest 和离线 Benchmark 不需要模型密钥。
