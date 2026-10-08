# 通用运行时快照

本目录提供既有 Miniclaw Host/Pi、渠道、工作区和 Web 管理台，售后扩展通过 `container/agent-runner/src/acs-tools.ts` 调用独立 Python 引擎。来源与改动范围见 [NOTICE](../../NOTICE.md)，版权及 MIT 授权保留于 [LICENSE](LICENSE)。

售后页面已迁至 `apps/service-console`，不再与本目录的通用管理台一起构建。体验业务请从 [根目录说明](../../README.md) 开始。

## 运行

需要 Node.js 20+。分别在本目录、`web/` 和 `container/agent-runner/` 执行 `npm ci`。配置 Python 引擎、企业绑定和模型后，执行 `npm run build:all` 与 `npm start`；默认 `http://127.0.0.1:3000`，会话入口 `/chat`。完整配置见 [Pi 接入](../../docs/run-service-mode.md)。

开发用 `npm run dev:all`。类型检查 `npm run typecheck`；Web 构建 `npm --prefix web run build`；Runner 构建 `npm --prefix container/agent-runner run build`。

API 与授权边界详见 `docs/API.md`、`docs/ACL-MATRIX.md` 与 `SECURITY.md`。数据库、会话、凭证和工作区不得提交。容器执行需另行配置镜像和挂载。
