# 独立售后工作台

本应用首页是需要登录的售后管理员工作台，提供客户会话、全企业工单、设备台账及飞书接入配置。独立 Python 后端负责管理员鉴权、企业绑定、官方 SDK 飞书长连接与 PostgreSQL，不依赖通用 Host。

从仓库根目录执行：

```bash
npm ci
npm run dev
```

根路径 `http://127.0.0.1:5173/` 是管理员入口，开发时还需启动 Python 后端并设置管理员密码与渠道加密密钥，见 [部署指南](../../docs/deployment.md)。`/experience` 是网页报修体验；`/service-preview` 为可独立运行的旧前端样例。`npm run build` 检查 TypeScript 并生成独立产物。

## 前端样例交互（/service-preview）

- 复合报修与进度拆为本地任务；只读查询先返回，报修停在设备确认。
- 设备确认 → 补充故障 → 核对提交；确认前不生成工单。
- 等待补充时独立查询不覆盖报修的设备、故障和阶段；切页保留，切企业及刷新重置。
- 人工接手保留交接摘要，只冻结该任务；保养查询需确认设备。
- 否定、条件或不支持的表达进入人工核实，不自动写入业务。
- 搜索、状态筛选、工单详情、重复报修检查及设备入口可用。

## 数据与接入边界

旧前端样例来自合成数据，新建和确认只保存在组件内存，刷新重置；企业选择只是样例筛选。

管理员使用独立 HttpOnly Cookie 登录，能查看各客户会话和工单；客户 Cookie 不授予管理权限。飞书配置仅允许管理员修改，密钥不会返回浏览器；接收由官方 SDK 子进程执行，客户企业身份由管理员绑定。`/experience` 使用独立合成企业与设备，确认后写入 PostgreSQL；API 保留 Origin/CSRF、去重和过期清理。当前默认业务规则处理，未接入模型、审批或派单。详见 [飞书与管理台](../../docs/feishu-admin.md)。

真实业务能力在 [backend](../../backend/README.md)，网页适配见 [web.py](../../backend/acs/web.py)，实际 Pi 会话接入见 [运行指南](../../docs/run-service-mode.md)。生产客户账号与模型链路仍需独立接入。

## 交互回归

仓库根目录安装依赖后，执行 `npx playwright install chromium`，再执行 `npm run test:ui`。也可用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` 指向本地 Chrome。6 个场景分别在桌面和移动端运行，覆盖确认门禁、复合任务、查询保留报修、人工接手、企业切换、否定输入与重复建单。

真实网页流程使用 `playwright.live.config.ts`，必须先运行 Web + PostgreSQL 部署栈；桌面和手机检查确认、只读查询、刷新与访客隔离。Linux CI 另外验证应用容器重启后的实际工单恢复。
