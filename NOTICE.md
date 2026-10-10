# 代码来源与改动范围

本仓库包含售后业务扩展与第三方运行时快照。目录拆分用于明确模块职责，不改变原代码的来源或版权。

| 位置 | 职责与来源 |
| --- | --- |
| `backend/acs/` | 售后领域工具、企业绑定、PostgreSQL、状态路由及上下文装配 |
| `apps/service-console/` | 从原工作台抽出的售后页面、任务交互、示例数据与样式；独立入口和精简依赖，保留合成演示标识 |
| `evals/`、`examples/`、`scripts/` | 售后评估集、真实业务演示及统一运行入口 |
| `vendor/miniclaw/` | 既有 Miniclaw 通用运行时代码快照，包含 Host、渠道、工作区、Web 管理台和 Pi Runner；本仓库在其上接入售后工具与可信消息上下文 |

第三方运行时的版权和 MIT 授权全文保留于 [vendor/miniclaw/LICENSE](vendor/miniclaw/LICENSE)，根目录 [LICENSE](LICENSE) 也保留该声明。所使用的 npm/Python 依赖适用其各自许可证。本项目不将通用运行时声明为独立原创实现。

公开数据为示例企业、DEMO 设备与合成工单。客户材料、凭证、运行数据库和会话日志不随仓库发布。
