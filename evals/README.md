# 售后流程评估

在仓库根目录运行 `npm run eval`，或 `python evals/run_service_eval.py --output evals/reports/service.json`。

- `service_cases.json`：16 个离线场景，覆盖正常报修、澄清、确认、独立查询、企业隔离、作用域变更和重复事件。
- `run_service_eval.py`：运行真实业务引擎与临时 SQLite，核对工具、状态和工单数量。报告保存在忽略目录，不包含客户数据。
- `intent_cases.json` / `run_intent_eval.py`：单独的模型意图实验；`--dry-run` 只核对样例。实际模型调用需自行配置凭证，费用和模型质量没有包含在上述离线通过率中。

16/16 表示业务契约通过率，不代表模型意图准确率或渠道端到端可用率。
