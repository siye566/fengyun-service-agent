# 截图来源与复现

截图复验日期：2026-10-08。全部图片从迁移后的独立工作台与实际 Python 演示重新生成，浏览器页面错误为 0。企业、设备及工单均为合成演示数据，不是客户生产画面。

`backend-workflow.png` 来自真实 Python demo 的 stdout，整理为 HTML 后截图，没有修改运行结果；它不是额外的后台产品页面，也不证明模型、飞书或生产验收。

仓库根目录安装依赖，启动 `npm run dev -- --port 5187 --strictPort`，另开终端执行：

```bash
npm run screenshots --workspace @service-agent/console
```

脚本默认使用 Playwright Chromium 和 PATH 中 Python。可通过 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`、`ACS_CAPTURE_PYTHON`、`SERVICE_PREVIEW_URL` 指定浏览器、解释器和预览地址。不需要模型或渠道凭证。运行记录来自 `examples/demo_service.py`；输出写入本目录。截图保留演示与规划状态说明。
