# 峰云空压机售后 Agent · 脱敏演示版

空压机售后服务智能体原型，用于展示领域工具、权限约束和工作台交互。不包含客户数据、生产配置或原仓库提交历史。

## 实现与边界

- `acs-agent/`：Python + SQLite 业务引擎，提供报修、保养查询与扫描、零件申领/审批、进度查询等工具。会话绑定决定企业或内部角色，未绑定时拒绝访问。
- `miniclaw/container/agent-runner/src/acs-tools.ts`：Pi Runtime 到 Python CLI 的工具桥，将会话身份传入业务层。
- `miniclaw/web/`：峰云售后工作台。`/service-preview` 使用组件内存中的演示数据，刷新后重置；确认、任务与执行记录不能视为真实后台动作。详见 [前端说明](miniclaw/web/SERVICE-FRONTEND.md)。
- 不声明生产上线、真实客户收益或模型评测成绩。企业隔离在 Python 工具层实现，前端企业筛选仅作展示。

## 本地运行

需要 Node.js 20+、npm、Python 3.10+。在 `acs-agent` 下创建虚拟环境，执行 `pip install -r requirements.txt` 和 `python -m pytest -q`，再执行 `python -m acs.seed` 生成示例数据库。

在 `miniclaw`、`miniclaw/web` 和 `miniclaw/container/agent-runner` 下分别运行 `npm ci`。仅预览前端时，在 `miniclaw/web` 下运行 `npm run dev`，打开 `http://localhost:5173/service-preview`。

接入工具前，设置 `ACS_AGENT_PYTHON` 为虚拟环境 Python 的绝对路径、`ACS_AGENT_ROOT` 为 `acs-agent` 的绝对路径，再按 [运行说明](miniclaw/README.md) 构建和启动。模型与渠道凭证仅通过本地配置提供。

## 脱敏与许可

企业统一为“示例企业甲/乙/丙”，设备编号使用 `DEMO-` 前缀。个人路径、凭证、数据库、日志、历史评测报告、截图和本地工具元数据不随仓库发布。规则和价格仅作软件演示。

售后领域扩展位于业务引擎、工具桥与售后前端中；通用运行时、工作区与渠道基础设施属于底座能力。第三方代码的版权及许可声明见 [LICENSE](LICENSE)。
