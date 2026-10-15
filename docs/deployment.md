# Linux / 阿里云轻量服务器部署

首页是需要登录的管理员工作台，提供全企业会话、工单、设备和飞书接入配置。客户使用飞书机器人私聊报修；`/experience` 保留原 PostgreSQL 网页报修体验。默认规则处理，不调用模型。飞书需填写自建应用凭证、配置长连接及消息权限后启用，详见 [飞书与管理台](feishu-admin.md)。

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

脚本生成随机数据库密码、管理员密码 `ACS_ADMIN_PASSWORD` 和渠道加密密钥 `ACS_CHANNEL_KEY`，存入仓库 `.env`（权限 600）。已有文件只补充缺失管理设置，保留数据库密码。数据库保存到 `compressor-service-web_web-postgres` 卷中，重启和重建应用保留数据；启动不执行 `seed --reset`。仅构建独立前端和 Python 飞书适配，不构建通用 Host/Pi。

默认只监听服务器自身 `127.0.0.1:8080`，健康检查返回 `status: ok`、`storage: postgresql`。初次安装需下载 Node、Python 和 PostgreSQL 官方镜像；若下载超时，检查镜像仓库网络，保留证书验证。

### Docker Hub 超时时使用离线包

在 [Releases](https://github.com/siye566/fengyun-service-agent/releases) 下载本项目 `Linux 离线部署包` 的 `acs-web-linux-amd64.tar.gz`、`SHA256SUMS` 和 `images.txt`。该包由手动运行的 `Verify web deployment` 工作流生成，只在导出/导入镜像、实际网页流程与重启检查通过后发布。原始 Docker 镜像的许可仍保留，`images.txt` 记录镜像 ID 与源码提交。镜像包不包含运行时 `.env`、访客 Cookie 或 PostgreSQL 数据卷。

在包文件所在目录校验，随后从仓库目录启动（把路径换成下载包实际路径）：

```bash
sha256sum -c SHA256SUMS
git pull --ff-only
sudo bash scripts/deploy-web.sh /完整路径/acs-web-linux-amd64.tar.gz
curl -f http://127.0.0.1:8080/healthz
```

离线模式只支持 Linux x86_64，使用 `docker load` 后 `--no-build --pull never` 启动，不再拉取 Docker Hub，也不在服务器下载 npm/Python 依赖。已有 `.env`、数据库卷仍保留。升级离线版本时导入新包；不要用不带包参数的普通构建命令，否则又会访问基础镜像仓库。

已安装 PostgreSQL 17 的服务器可只下载 `acs-web-update-linux-amd64.tar.gz` 和 `SHA256SUMS-update`，放在同一目录，执行 `sudo bash scripts/deploy-web.sh /完整路径/acs-web-update-linux-amd64.tar.gz`。升级包只包含 Web 镜像，避免重复下载 PostgreSQL；不存在 `postgres:17` 时脚本拒绝并提示使用完整包。不同版本放在各自的新目录，避免把旧文件误当成新版本续传。

自己的电脑可用 SSH 隧道预览（使用阿里云实际登录用户名）：

```bash
ssh -L 8080:127.0.0.1:8080 <登录用户>@<服务器公网IP>
```

打开 `http://127.0.0.1:8080` 进入管理员登录。在服务器仓库目录执行 `sudo grep '^ACS_ADMIN_PASSWORD=' .env` 查看密码，只填写等号后的值，请勿公开。客户网页体验入口是 `/experience`。此方式不开放服务器业务端口；飞书长连接为出站连接，可在管理台仍通过 SSH 预览时使用。

## 公开入口

广州等中国内地节点对外提供网站服务需按要求办理备案，参见[阿里云使用须知](https://help.aliyun.com/zh/simple-application-server/product-overview/usage-notes)。上线前确定域名和备案、配置 HTTPS，再把 `.env` 中 `ACS_WEB_ORIGIN` 改成用户实际访问的源站地址，包含协议和端口、结尾不带路径。

反向代理转发到 `127.0.0.1:8080` 并保留原始 Host；HTTPS 时设置 `ACS_WEB_ORIGIN=https://你的域名`，Cookie 自动带 Secure 标记。只开放实际网站入口 80/443，数据库不发布公网端口。当前 Compose 不自动签发证书或修改阿里云防火墙。

修改后执行：

```bash
sudo docker compose --env-file .env -f deploy/compose.yaml up -d --wait
```

Origin 必须匹配浏览器地址，错误时返回 403，不回退成浏览器模拟工单。

## 2GB 内存范围

构建时 Node 堆上限 512MB；运行时 Web 及其飞书子进程合计上限 512MB、PostgreSQL 上限 384MB，单 Web 进程与有界请求并发。用于低并发体验，真实飞书接入后需在目标服务器实测，不能据此宣称并发人数。

每个空间最多 200 次操作；每来源地址 API 每分钟最多 120 次请求；最多 500 个有效体验空间。数据固定保留 24 小时，新访客进入时清理过期体验数据，保留种子台账与其他访客数据。每容器日志轮转总量约 30MB。

`/experience` Cookie 是合成企业体验会话，不能读取管理 API；删除或保留期结束后分配新空间。管理员 Cookie 独立鉴权，管理台提供跨企业视图、飞书配置及身份绑定。财务审批、自动派单和人工代回复尚未接入此管理台。飞书记录不按网页体验策略自动删除；实际使用前制定数据保留与备份策略。

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

开发需另外设置至少 16 字符的 `ACS_ADMIN_PASSWORD` 和 64 位十六进制 `ACS_CHANNEL_KEY`。根路径 `/` 是管理台；`/experience` 连接原报修 API；`/service-preview` 保留原独立前端样例，不能把样例结果作为后端写入证据。

`backend/tests/test_web.py` 验证 PostgreSQL 恢复、重试去重、事件冲突、跨访客隔离、Cookie/Origin/CSRF、请求大小与过期清理。`Verify web deployment` 在 Linux CI 构建实际 Docker 镜像，启动 PostgreSQL + Web，执行桌面/移动浏览器流程。这些检查不等于已部署到用户阿里云实例，也不验证外部模型或飞书。
