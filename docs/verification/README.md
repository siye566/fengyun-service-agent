# 可复现验证记录

公开验证使用合成企业、设备和工单，不连接客户系统。每个业务场景运行在独立临时 SQLite 中，检查阶段、工具许可、错误码及实际工单数量。

## 2026-10-10：离线业务场景复验

- 结果：**16/16 通过**，各场景失败列表均为空。
- 原始结果：[service-benchmark.json](service-benchmark.json)。
- 输入与断言：[service_cases.json](../../evals/service_cases.json)。
- 执行器：[run_service_eval.py](../../evals/run_service_eval.py)。
- 业务源码基线：[`e07a65f`](https://github.com/siye566/fengyun-service-agent/commit/e07a65f8200a73a500024672ca4d6abd57b3c668)。本次页面与文档更新没有修改业务实现。

| 场景 ID | 验证内容 | 结果 |
| --- | --- | --- |
| repair-confirm | 信息齐全后等待确认，确认后建一张工单 | 通过 |
| missing-device | 缺设备时澄清，补充后等待确认 | 通过 |
| missing-symptom | 缺故障时澄清，补充后等待确认 | 通过 |
| confirmation-too-early | 无待确认任务时拒绝确认 | 通过 |
| unknown-device | 未知设备不能直接建单 | 通过 |
| cross-company | 拒绝访问其他企业设备 | 通过 |
| unbound | 未绑定会话身份时拒绝业务请求 | 通过 |
| maintenance | 已知设备的只读保养查询 | 通过 |
| maintenance-missing-device | 保养查询缺设备时澄清 | 通过 |
| progress | 查询当前企业工单进度 | 通过 |
| compound-detour | 报修期间独立查询保留原任务，随后确认建单 | 通过 |
| cancel | 取消待处理报修，不建单 | 通过 |
| negation | 否定报修输入不触发写操作 | 通过 |
| duplicate-confirm | 同一事件重复确认只建一张工单 | 通过 |
| model-extraction-contract | 合法结构化候选进入业务状态机 | 通过 |
| invalid-model-schema | 非法候选 Schema 被拒绝 | 通过 |

复现时在仓库根目录运行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe evals/run_service_eval.py --output evals/reports/service.json
```

macOS / Linux 使用 `.venv/bin/python`。生成报告位于本地忽略目录；可与本页公开 JSON 的场景 ID、通过数量及失败列表比较。

**该结果验证业务契约，不衡量模型意图准确率、真实渠道投递或生产可用性。** 结构化候选场景使用固定输入；没有调用在线模型。并发、中断恢复和上下文预算等更细的路径由 Python 回归测试覆盖，不包含在上述 16 个场景数量中。

## 回归与持续验证

2026-10-08 的本地验证基线为 50 项 Python 测试、12 项桌面/移动端交互测试，以及真实 Node → Python 子进程集成；记录见 [validation.md](../validation.md)。

[GitHub Actions](https://github.com/siye566/fengyun-service-agent/actions/workflows/verify.yml) 在 push / PR 时运行业务回归、离线场景、工作台构建与交互、Pi Runner 构建和工具桥集成。每次提交的结果以对应 Actions 运行记录为准，历史基线不能代替最新 CI 状态。

界面截图及复现方式见 [截图说明](../screenshots/README.md)，集成边界见 [交付范围](../roadmap.md)。
