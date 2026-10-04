# 接入当前 Pi 运行链路

此模式适用于 Host 执行环境。容器中需要另行提供 Python、引擎目录和持久化数据库挂载；本说明不声称容器配置已完成。

1. 在 `acs-agent` 下创建虚拟环境并安装 `requirements.txt`；执行 `python -m acs.seed` 初始化示例数据库。
2. 根据服务端实际的 chatJid 绑定企业身份：`python -m acs.bind '<实际会话键>' '示例企业甲'`。它是管理命令，不能让模型自行选择或修改绑定。默认示例 `web:main` 是 internal，企业隔离演示请另外创建 company 绑定。
3. 启动 Backend 前设置 `ACS_SERVICE_MODE=1`、`ACS_AGENT_PYTHON`（虚拟环境解释器绝对路径）、`ACS_AGENT_ROOT`（引擎绝对路径）。可用 `ACS_DB_PATH` 指定演示数据库，初始化时使用同一个路径。
4. 在项目设置中选择 Host 执行模式并配置模型。`miniclaw/container/agent-runner` 执行 `npm run build`，再按运行说明启动 Backend。

Host 子进程继承以上环境变量。每次 Pi 会话调用先获取售后上下文，未绑定或超出必需段预算时失败。模型通过 `route_service_turn` 提交结构化候选；桥接层注入当前 chatJid、线程标识及宿主消息 ID，Python 完成业务校验和执行。

第一次报修返回设备、故障与确认提示；用户下一轮明确回复“确认报修”后才创建工单。独立进度查询返回后，原报修仍保持等待。取消当前报修使用“取消报修”。确认用语目前采用白名单，不宣称自然语言确认覆盖率。

前端 `/service-preview` 和 `/service` 的新售后工作台仍是内存演示。上述真实业务链路通过现有 `/chat`、Host/Pi 和工具桥运行；本次没有将演示界面的按钮接入业务 API。

所有运行数据库、会话和日志都应保存在 Git 忽略目录。环境变量文件中不得放置可提交的凭证。
