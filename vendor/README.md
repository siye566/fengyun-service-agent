# 可选运行时集成

`miniclaw/` 保存现有通用 Agent 运行时快照及其许可声明，提供 Host/Pi、渠道和管理界面。售后扩展的工具桥位于 `miniclaw/container/agent-runner/src/acs-tools.ts`。

体验售后界面、运行 Python demo 和离线评估均不需要安装此目录的依赖。由根目录 [启动说明](../README.md#快速体验) 开始。

只有需要模型及真实会话链路时，才按 [Pi 接入指南](../docs/run-service-mode.md) 配置运行时、可信会话身份、Python 引擎和数据库。来源与改动范围见 [NOTICE](../NOTICE.md)。
