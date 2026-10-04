# 截图来源与复现

截图日期：2026-10-04。浏览器：Chromium，桌面视口。前端来源为本仓库 `/service-preview`，数据为示例企业、DEMO 设备与内存工单；不是客户生产画面。

`backend-workflow.png` 从真实 `python scripts/demo_service.py` stdout 生成可读 HTML 后截图，未修改运行结果。它不代表存在额外的后台产品页面，也不证明模型、飞书或生产环境验收。

在 `miniclaw/web` 下安装依赖并运行 `npm run dev -- --host 127.0.0.1 --port 5187 --strictPort`；另开终端执行 `node scripts/capture-service.mjs`。

脚本默认使用 Playwright Chromium 和 PATH 中的 Python。可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 指定本地 Chrome/Chromium，`ACS_CAPTURE_PYTHON` 指定解释器，`SERVICE_PREVIEW_URL` 指定本地预览地址。无需模型或渠道凭证。

前端预览没有后端 WebSocket 服务，可能记录 `WebSocket closed without opened.` 警告；脚本只单独记录此已知预览警告，其他页面错误会使捕获失败。截图中保留原有演示与规划状态说明。
