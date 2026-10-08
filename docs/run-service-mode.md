# 接入 Host/Pi 真实会话链路

此模式适用于 Host 执行环境。容器中需另行提供 Python、引擎目录与持久化数据库挂载；本说明不声称容器部署已完成。独立工作台不需要以下依赖。

1. 在仓库根目录创建 `.venv`，安装 `backend/requirements.txt`。设置 `PYTHONPATH` 为 `backend` 的绝对路径，执行 `python -m acs.seed` 初始化示例数据库。
2. 根据服务端实际的 chatJid 绑定身份：`python -m acs.bind '<实际会话键>' '示例企业甲'`。这是管理员命令，不能由模型选择或修改绑定；默认示例 `web:main` 是 internal，企业演示需另建 company 绑定。
3. 设置 `ACS_SERVICE_MODE=1`、`ACS_AGENT_PYTHON`（解释器绝对路径）、`ACS_AGENT_ROOT`（`backend` 的绝对路径）。可用 `ACS_DB_PATH` 指定数据库，初始化和运行使用同一路径。
4. 在 `vendor/miniclaw`、其 `web`、其 `container/agent-runner` 下分别执行 `npm ci`，在 `vendor/miniclaw` 下运行 `npm run build:all` 与 `npm start`。默认管理台地址为 `http://127.0.0.1:3000`。
5. 初次登录完成管理员和模型配置，在设置中选择 Host 执行模式，通过 `/chat` 使用真实会话。

Host 子进程继承以上环境变量。每次 Pi 会话调用先获取售后上下文，未绑定或必需段超限时失败。模型通过 `route_service_turn` 提交结构化候选；工具桥注入可信 chatJid、线程和宿主消息 ID，由 Python 完成校验与执行。

首次报修返回设备、故障和确认提示；下一轮用户明确回复“确认报修”才建单。独立进度查询返回后原报修继续等待；取消使用“取消报修”。确认采用白名单，不声明自然语言确认覆盖率。

售后工作台已独立到 `apps/service-console`，根目录 `npm run dev` 后打开 `http://127.0.0.1:5173/`。它使用内存合成数据，未接业务 API；页面“接入指南”链接说明如何运行本节真实链路。通用管理台默认进入 `/chat`，不再嵌入售后演示。

所有运行数据库、会话、日志与凭证保存在 Git 忽略目录。第三方代码来源与许可见 [NOTICE](../NOTICE.md)。
