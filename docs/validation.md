# 验证记录

## 2026-10-14：网页领域 API 与 Docker 部署

代码版本 `4f47dad`；使用合成访客空间，不调用模型或飞书。

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| PostgreSQL Python 回归 | 59 项通过（55 项领域 + 4 项 HTTP 集成） | [业务 CI](https://github.com/siye566/fengyun-service-agent/actions/runs/38508222292) |
| 原前端样例 | 桌面/手机共 12 项通过 | 同上；本地 Chrome 亦通过 |
| 实际部署镜像 | Docker 构建并启动 Web + PostgreSQL，健康检查通过 | [容器 CI](https://github.com/siye566/fengyun-service-agent/actions/runs/38508222279) |
| 网页实际流程 | 桌面/手机 2 项通过：确认前不建单、查询保留报修、刷新恢复、另一访客隔离 | `apps/service-console/tests/live.spec.ts` |
| 容器重启恢复 | 同一个 Cookie、企业、任务完成状态和实际工单在 Web 重启后恢复 | `scripts/verify-web-restart.mjs` |
| 构建与工具桥 | TypeScript/Vite、Pi Runner 与原工具桥检查通过 | 业务 CI |

HTTP 回归包括请求去重、不同请求复用事件拒绝、跨访客设备拒绝、Cookie/Origin/CSRF、分块请求大小限制及过期体验空间清理。容器运行设置 Web 512MB / PostgreSQL 384MB 内存上限；没有进行用户阿里云实例容量测试。截图与来源见 [截图说明](screenshots/README.md)。

## 2026-10-10：PostgreSQL 业务库

真实 PostgreSQL 17.11、Python 3.10、psycopg 3。测试与评估通过独立临时 schema 隔离，没有使用模型或渠道凭证。

| 验证 | 结果 | 范围 |
| --- | --- | --- |
| `python -m pytest -q` | 55 项通过 | 原有业务契约及新增回滚、schema 隔离、并发编号、重复审批 |
| `python evals/run_service_eval.py` | 16/16 通过 | 真实 PostgreSQL 状态、工具许可及实际工单数 |
| `python examples/demo_service.py` | 三轮通过 | 等待确认 → 查询保留报修 → 确认建单 |
| `npm run test:bridge` | 1 项通过 | 真实子进程共享 PostgreSQL，可信文本与重复回执 |
| 后端执行记录图 | 已重新生成 | 本次 PostgreSQL 示例的真实 stdout；没有调用模型或渠道 |

公开报告与复现步骤见 [verification/README.md](verification/README.md)。CI 启动真实 PostgreSQL 17 服务复验，并上传评估报告。

## 2026-10-08：目录迁移历史基线

以下为换库之前的历史基线，不代表 PostgreSQL 验证结果。目录迁移后，使用脱敏示例与临时数据库重新验证，没有使用模型或渠道凭证。

| 命令（仓库根目录） | 结果 | 证明范围 |
| --- | --- | --- |
| `npm test` | 50 项通过 | 领域工具、路由、恢复、并发去重、企业重新绑定和上下文预算 |
| `npm run eval` | 16/16 场景通过 | 真实业务引擎的意图契约、澄清、允许工具、目标状态与工单数 |
| `npm run demo` | 三轮流程通过 | 待确认 → 查询保留报修 → 明确确认后建单 |
| `npm run test:ui` | 12 项通过 | 独立前端的桌面/移动端流程、确认门禁、范围切换和无后端写入 |
| `npm run build` | 通过 | 独立工作台的 TypeScript 检查与 Vite 生产构建 |
| `npm run test:bridge` | 1 项通过 | 真实 Python 子进程、可信原文确认、动态作用域和重复回执 |
| `npm run build:runner` | 通过 | Pi Runner 类型及模块连接 |
| `npm --prefix vendor/miniclaw/web run build` | 通过 | 迁移后可选运行时管理台构建；原有大分包警告仍存在 |

UI 回归使用本地 Chrome；CI 使用 Playwright Chromium。前端 npm 依赖由根目录锁文件固定，通用运行时依赖由各自锁文件固定。

上述历史检查不覆盖真实模型解析质量、飞书收发、生产部署或财务角色细分。当时工作台使用内存合成数据；新版根路径领域 API 的验证见本页 2026-10-14 节。

CI 复验业务测试、离线 Benchmark、独立前端构建与交互、Runner 构建和工具桥，并上传评估报告。实际 CI 状态以 [Actions](https://github.com/siye566/fengyun-service-agent/actions/workflows/verify.yml) 为准。
