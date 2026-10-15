# 截图来源与复现

`admin-conversations.png` 和 `admin-feishu-settings.png` 来自 2026-10-15 的 [真实 Docker 管理台验证](https://github.com/siye566/fengyun-service-agent/actions/runs/38687277124)，代码版本 `fe68da3`。测试从独立客户浏览器发起报修，再以管理员登录查看该合成企业会话和待确认任务，并打开飞书接入配置。图片明确显示网页客户来源、飞书尚未配置，没有真实飞书凭证或消息。桌面/移动端合计 4 项实际部署浏览器用例通过。

`web-postgresql-confirmation.png` 和 `web-postgresql-mobile-ticket.png` 来自 2026-10-14 的 [真实 Docker 网页验证](https://github.com/siye566/fengyun-service-agent/actions/runs/38508222279)，代码版本 `4f47dad`。Linux CI 实际启动 PostgreSQL + Python API + 构建后的 React 页面，截图使用访客独立合成空间；没有调用模型或飞书。这些图片证明网页业务流程，不能当作用户阿里云实例上线记录。

工作台截图复验日期：2026-10-08；PostgreSQL 后端运行记录复验日期：2026-10-10。企业、设备及工单均为合成样例，不是客户生产画面。

`backend-postgresql-workflow.png` 来自本次真实 PostgreSQL 运行的 Python stdout，整理为 HTML 后截图，浏览器页面错误为 0。没有修改运行结果；它是执行记录视图，不证明模型、飞书或生产验收。旧 `backend-workflow.png` 为换库前的历史截图，首页已切换到新图。

仓库根目录安装依赖，启动 `npm run dev -- --port 5187 --strictPort`，另开终端执行：

```bash
npm run screenshots --workspace @service-agent/console
```

脚本默认使用 Playwright Chromium 和 PATH 中 Python。可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`、`ACS_CAPTURE_PYTHON`、`SERVICE_PREVIEW_URL` 指定浏览器、解释器和预览地址。后端记录需先完成 [PostgreSQL 配置](../database.md)，不需要模型或渠道凭证。运行记录来自 `examples/demo_service.py`；输出写入本目录。设置 `SERVICE_CAPTURE_BACKEND_ONLY=1` 可只生成后端记录图，无需启动工作台。截图保留演示与规划状态说明。
