# 截图来源与复现

工作台截图复验日期：2026-10-08；PostgreSQL 后端运行记录复验日期：2026-10-10。企业、设备及工单均为合成样例，不是客户生产画面。

`backend-postgresql-workflow.png` 来自本次真实 PostgreSQL 运行的 Python stdout，整理为 HTML 后截图，浏览器页面错误为 0。没有修改运行结果；它是执行记录视图，不证明模型、飞书或生产验收。旧 `backend-workflow.png` 为换库前的历史截图，首页已切换到新图。

仓库根目录安装依赖，启动 `npm run dev -- --port 5187 --strictPort`，另开终端执行：

```bash
npm run screenshots --workspace @service-agent/console
```

脚本默认使用 Playwright Chromium 和 PATH 中 Python。可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`、`ACS_CAPTURE_PYTHON`、`SERVICE_PREVIEW_URL` 指定浏览器、解释器和预览地址。后端记录需先完成 [PostgreSQL 配置](../database.md)，不需要模型或渠道凭证。运行记录来自 `examples/demo_service.py`；输出写入本目录。设置 `SERVICE_CAPTURE_BACKEND_ONLY=1` 可只生成后端记录图，无需启动工作台。截图保留演示与规划状态说明。
