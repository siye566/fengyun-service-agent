# PostgreSQL 业务数据库

售后领域引擎使用 **PostgreSQL + psycopg 3**。设备、知识、库存、企业绑定、报修工单、零件申领、待处理状态和事件回执均写入 PostgreSQL；不存在文件数据库回退。

## 启动与初始化

需要 Python 3.10+ 和 PostgreSQL 17。本地已有数据库时可直接配置连接；没有数据库时使用仓库的 Docker Compose：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，将 `ACS_POSTGRES_PASSWORD` 与 `ACS_DATABASE_URL` 中的示例口令一起替换。URL 中的特殊字符需 URL 编码。Compose 只将数据库端口绑定到 `127.0.0.1`，数据保存在命名卷中。

```powershell
docker compose up -d --wait postgres
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\backend"
.venv\Scripts\python.exe -m acs.seed
.venv\Scripts\python.exe -m acs.bind 'web:service-company-a' '示例企业甲'
```

Python 自动读取仓库根目录 `.env`，已经设置的环境变量优先。`acs.seed` 只在空台账中写入合成样例；已有设备时跳过，不要在实际业务库运行 `--reset`。仅建表可执行 `python -m acs.db`。

环境变量：

| 变量 | 用途 |
| --- | --- |
| `ACS_DATABASE_URL` | PostgreSQL 连接 URL，必需；不要提交真实连接凭证 |
| `ACS_DB_SCHEMA` | 可选的可信 schema 名，用于隔离工具桥测试等场景；默认使用数据库连接的 search path |
| `ACS_POSTGRES_PASSWORD` | 仅供本地 Compose 初始化数据库角色，修改已有卷中的口令需另行管理 |

生产接入应由管理员先执行建表，再为运行角色配置所需表和序列权限。`connect()` 不执行 DDL；种子及临时 schema 工具是开发入口，不要求运行角色持有建表权限。

## 事务和迁移边界

SQL 使用 psycopg 的 `%s` 参数绑定；身份、状态的更新使用 `ON CONFLICT`。工单的业务幂等键与回执的 `(session_key, event_id)` 均有唯一约束。

领域写事务获取当前 schema 的 `pg_advisory_xact_lock`，保护工单/申领编号与库存审批。提交、回滚或连接关闭时释放；状态机在调用另一连接的工具前提交，恢复写操作时重新获取锁。这是串行写事务的实现取舍，没有附加吞吐量主张。

此变更只迁移售后业务库；可选 Host 运行时自有的会话元数据存储沿用其上游实现，并未改造。旧版本地数据文件不会自动导入 PostgreSQL，当前仓库也没有客户数据迁移结果。需要保留旧业务数据时，应单独设计导入、对账和回滚步骤。

## 复验

配置开发/测试数据库后，在根目录运行：

```powershell
npm test
npm run eval
npm run demo
```

测试、演示和离线评估会创建随机 `acs_test_*` schema，在退出时只清理自己创建的 schema。测试角色需要 `CREATE` 权限，请使用独立的开发/测试数据库。工具桥回归使用 `acs_bridge_*` schema，验证跨进程共享同一个数据库状态。

当前验证记录见 [验证结果](verification/README.md)。驱动和锁的行为参考 [psycopg 参数与事务文档](https://www.psycopg.org/psycopg3/docs/basic/usage.html) 与 [PostgreSQL 锁文档](https://www.postgresql.org/docs/17/explicit-locking.html)。
