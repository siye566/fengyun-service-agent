# 关键工程设计

本页说明已落实到业务代码的设计，以及取舍。验证使用公开合成样例与PostgreSQL 独立临时 schema，生产接入范围见 [实现对照](implementation-map.md)。

## 1. 用程序控制写操作

报修属于有副作用的业务动作。模型可提供 `intents`、`device_serial` 和 `symptom` 等结构化候选，程序负责候选 Schema、可信身份、设备归属、缺字段与确认条件。

`route_service_turn` 先读任务状态，再处理本轮输入。报修信息齐全进入 `awaiting_confirmation`；建单仅接受宿主传入的可信原文“确认报修”或“确认提交”。模型参数不能代替用户确认。设备改变需取消当前报修后开始新任务。

- 源码：[service.py](../backend/acs/service.py)、[工具桥](../vendor/miniclaw/container/agent-runner/src/acs-tools.ts)。
- 验证：确认过早、非法候选、跨企业设备、否定输入和模型伪造确认均有失败路径。
- 取舍：确认白名单容易验证，但没有覆盖任意自然语言确认；每个线程只保持一个待处理报修。

## 2. 保留挂起任务，允许独立查询

用户等待报修确认时，仍可能查询工单进度。只读查询使用本次输入的设备/工单字段，查询后重新加载状态，不覆盖原报修的设备、故障或阶段。

源码中的 `service_sessions` 保存任务状态，`service_turns` 保存事件结果。重启进程后可从 PostgreSQL 读取待确认任务；相同事件重试返回已有结果。

- 源码：[状态路由](../backend/acs/service.py)、[数据结构](../backend/acs/db.py)。
- 验证：[test_service.py](../backend/tests/test_service.py) 覆盖状态恢复、独立查询与重复事件。
- 取舍：这是受限业务状态机；通用多任务队列、消息 Outbox 和完整 Trace Replay 尚未纳入领域引擎。

## 3. 将企业身份绑定到可信会话

客户端与模型不能任意指定企业。Host 提供会话键，`company_bindings` 决定企业客户或内部身份；未绑定默认拒绝。领域工具再次校验设备、工单和零件申请的归属。

任务作用域同时包含会话及身份绑定指纹，重新绑定后不会读取旧企业的待确认任务。管理员绑定命令和业务路由分开。

- 源码：[identity.py](../backend/acs/identity.py)、[bind.py](../backend/acs/bind.py)、[tools.py](../backend/acs/tools.py)。
- 验证：未绑定、跨企业、绑定变更和内部角色的路径均有回归。
- 取舍：隔离发生在应用层；内部权限仍是合并角色，没有细分财务、工程师或管理员 RBAC。

## 4. 为写操作设置稳定业务键

消息去重无法独自覆盖“建单成功、回执保存前进程退出”的窗口。报修任务保存稳定 `task_key`，建单使用它作为幂等键，并通过唯一约束和事务限制重复写入。写事务还取得当前 schema 的 PostgreSQL advisory lock，保护编号生成与库存检查。提交状态保留为 `confirming`，用户重试同一确认可恢复原任务结果。

- 源码：[create_repair_ticket](../backend/acs/tools.py)、[数据库约束](../backend/acs/db.py)。
- 验证：重复确认、并发确认与中断后恢复均有回归。
- 取舍：写事务按 schema 串行，没有附加吞吐量主张；这保证了所测 PostgreSQL 建单路径的业务去重，没有宣称外部渠道发送“恰好一次”。

## 5. 对上下文做分段预算与来源审计

上下文按规则、身份、任务、设备、历史工单和故障知识六段装配。选定设备后才检索该设备历史；检索记录按预算缩减，身份与任务等必需段超限则拒绝进入模型。各段记录来源、摘要、SHA-256 与预算结果。

- 源码：[context.py](../backend/acs/context.py)、[Pi 接入](run-service-mode.md)。
- 验证：正常预算、接近阈值告警、必需段超限阻断和越权数据检索均有回归。
- 取舍：计量单位是 UTF-8 bytes；这不是模型整个会话窗口的精确 token 计量，也不是向量检索系统。

## 6. 将工作台与领域引擎分开验证

React 工作台验证报修交互、待处理任务、工单筛选与设备入口。Python 测试与场景评估验证真实状态、数据库、权限和写操作。两层通过各自明确的契约验证，避免把页面反馈当成后端成功回执。

当前工作台仍为合成数据模式，未连接领域 API；真实 Host/Pi 业务链路通过工具桥接入。后续集成须增加服务端鉴权、API 错误处理与状态一致性验证。

验证记录见 [validation.md](validation.md)，自动复验入口见 [GitHub Actions](https://github.com/siye566/fengyun-service-agent/actions/workflows/verify.yml)。

数据库启动、事务和导入边界见 [PostgreSQL 配置](database.md)。
