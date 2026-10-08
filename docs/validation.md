# 本地验证记录

复验日期：2026-10-08。目录迁移后，使用脱敏示例与临时数据库重新验证，没有使用模型或渠道凭证。

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

这些检查不覆盖真实模型解析质量、飞书收发、生产部署或财务角色细分。工作台继续使用内存合成数据，尚未接入业务 API。

CI 复验业务测试、离线 Benchmark、独立前端构建与交互、Runner 构建和工具桥，并上传评估报告。实际 CI 状态以 [Actions](https://github.com/siye566/fengyun-service-agent/actions/workflows/verify.yml) 为准。
