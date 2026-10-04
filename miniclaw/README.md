# 峰云运行环境

本目录包含通用 Agent 运行时、Web 工作台和渠道基础设施，售后扩展的范围见 [项目说明](../README.md)。第三方代码版权及许可声明保留在 [LICENSE](LICENSE)。

## 启动

需要 Node.js 20+；在本目录、web/ 和 container/agent-runner/ 下分别运行 npm ci。配置 ACS_AGENT_PYTHON 和 ACS_AGENT_ROOT 指向售后业务引擎，再执行 npm run build:all 和 npm start。默认服务地址为 http://127.0.0.1:3000。首次登录完成管理员和模型配置。

开发模式使用 npm run dev:all。仅预览售后界面时在 web/ 下运行 npm run dev，访问 http://localhost:5173/service-preview；该页面使用内存演示数据。

Backend 类型检查：npm run typecheck；Web 构建：npm --prefix web run build；通用回归：npm test -- --run。API 与授权边界详见 docs/API.md、docs/ACL-MATRIX.md 和 SECURITY.md。

数据库、会话、凭证与工作区文件保存在本地运行目录，不得提交。容器执行模式需要 Docker，并应单独配置镜像和挂载权限。
