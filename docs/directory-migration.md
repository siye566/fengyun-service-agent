# 目录迁移（2026-10-08）

| 原路径 | 当前路径 |
| --- | --- |
| `acs-agent/acs/` | `backend/acs/` |
| `acs-agent/tests/` | `backend/tests/` |
| `acs-agent/evals/` | `evals/` |
| `acs-agent/scripts/demo_service.py` | `examples/demo_service.py` |
| `miniclaw/web/src/pages/ServicePage.tsx` | `apps/service-console/src/pages/ServicePage.tsx` |
| `miniclaw/web/src/features/service/` | `apps/service-console/src/features/service/` |
| `miniclaw/web/src/styles/service.css` | `apps/service-console/src/styles/service.css` |
| `miniclaw/` 其余通用运行时代码 | `vendor/miniclaw/` |

售后界面改为独立 Vite 应用，从仓库根目录 `npm ci`、`npm run dev` 启动。`/` 和 `/service-preview` 均可访问工作台。运行时管理台恢复以 `/chat` 为默认入口，不再嵌入演示售后页面。

手工设置过 `ACS_AGENT_ROOT` 的环境需改为当前 `backend` 的绝对路径；`ACS_AGENT_PYTHON` 保持指向所用解释器。Python demo/测试/评估可在根目录执行，不要求安装通用运行时。目录迁移没有移动任何客户数据。2026-10-10 起售后业务引擎使用 PostgreSQL，旧的 `ACS_DB_PATH` 不再生效，改用 `ACS_DATABASE_URL`；旧业务数据需单独导入和对账，详见 [数据库配置](database.md)。

旧文件路径在历史 commit 中仍可查看。未改写提交历史或删除许可信息。
