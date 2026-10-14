# Linux / 阿里云轻量服务器部署

网页版调用真实 Python 领域引擎和 PostgreSQL，不调用模型或飞书。支持核对报修、确认建单、查进度和保养，刷新及服务重启后恢复状态。每个浏览器使用服务器分配的合成企业、设备和 HttpOnly Cookie，会话请求不能指定角色或企业作用域。

## 首次部署

需要 Git、Docker Engine 与 Docker Compose。Ubuntu 22.04/24.04 可用。在服务器终端执行：

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/siye566/fengyun-service-agent.git
cd fengyun-service-agent
sudo bash scripts/deploy-web.sh
curl -f http://127.0.0.1:8080/healthz
```

脚本生成随机数据库密码，存入仓库 `.env`（权限 600），已有文件不覆盖。数据库保存到 `compressor-service-web_web-postgres` 卷中，重启和重建应用保留数据；启动不执行 `seed --reset`。仅构建独立前端和 Python，不构建通用 Host/Pi 桌面与渠道运行时。

默认只监听服务器自身 `127.0.0.1:8080`，健康检查返回 `status: ok`、`storage: postgresql`。初次安装需下载 Node、Python 和 PostgreSQL 官方镜像；若下载超时，检查镜像仓库网络，保留证书验证。

自己的电脑可用 SSH 隧道预览（使用阿里云实际登录用户名）：

```bash
ssh -L 8080:127.0.0.1:8080 <登录用户>@<服务器公网IP>
```

打开 `http://127.0.0.1:8080`。此方式不开放服务器业务端口。

## 公开入口

广州等中国内地节点对外提供网站服务需按要求办理备案，参见[阿里云使用须知](https://help.aliyun.com/zh/simple-application-server/product-overview/usage-notes)。上线前确定域名和备案、配置 HTTPS，再把 `.env` 中 `ACS_WEB_ORIGIN` 改成用户实际访问的源站地址，包含协议和端口、结尾不带路径。

反向代理转发到 `127.0.0.1:8080` 并保留原始 Host；HTTPS 时设置 `ACS_WEB_ORIGIN=https://你的域名`，Cookie 自动带 Secure 标记。只开放实际网站入口 80/443，数据库不发布公网端口。当前 Compose 不自动签发证书或修改阿里云防火墙。

修改后执行：

```bash
sudo docker compose --env-file .env -f deploy/compose.yaml up -d --wait
```

Origin 必须匹配浏览器地址，错误时返回 403，不回退成浏览器模拟工单。

## 2GB 内存范围

构建时 Node 堆上限 512MB；运行时 Web 上限 512MB、PostgreSQL 上限 384MB，单 Web 进程与有界请求并发。用于低并发体验，需在目标服务器实测，不能据此宣称并发人数。

每个空间最多 200 次操作；每来源地址 API 每分钟最多 120 次请求；最多 500 个有效体验空间。数据固定保留 24 小时，新访客进入时清理过期体验数据，保留种子台账与其他访客数据。每容器日志轮转总量约 30MB。

Cookie 是合成企业体验会话，不是生产账号。此入口不开放管理员、财务审批、自动派单或真实渠道发送；仅使用合成资料。Cookie 删除或保留期结束后分配新空间。

## 更新与排查

```bash
git pull --ff-only
sudo bash scripts/deploy-web.sh
sudo docker compose --env-file .env -f deploy/compose.yaml ps
sudo docker compose --env-file .env -f deploy/compose.yaml logs --tail 80 web
sudo docker compose --env-file .env -f deploy/compose.yaml exec -T postgres pg_dump -U acs_web acs_web > acs-web-backup.sql
```

备份保存在私人目录，不提交公开仓库。普通更新不使用 `down -v` 或删除数据卷。已有数据库修改密码时需同步修改 PostgreSQL 用户密码，不能只改 `.env`。

## 开发与验证

先设置 `ACS_DATABASE_URL`（见 [数据库配置](database.md)）：

```bash
python -m pip install -r requirements-dev.txt
ACS_WEB_ORIGIN=http://127.0.0.1:5173 PYTHONPATH=backend python -m uvicorn acs.web:app --port 8080
# 另一个终端：
npm ci
npm run dev
```

根路径 `/` 连接后端；`/service-preview` 保留原独立前端样例，不能把样例结果作为后端写入证据。

`backend/tests/test_web.py` 验证 PostgreSQL 恢复、重试去重、事件冲突、跨访客隔离、Cookie/Origin/CSRF、请求大小与过期清理。`Verify web deployment` 在 Linux CI 构建实际 Docker 镜像，启动 PostgreSQL + Web，执行桌面/移动浏览器流程。这些检查不等于已部署到用户阿里云实例，也不验证外部模型或飞书。
