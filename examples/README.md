# 可复现业务演示

先完成 [PostgreSQL 配置](../docs/database.md)，安装 Python 依赖并设置数据库连接。

在仓库根目录执行 `npm run demo`，或 `python examples/demo_service.py`。

该脚本使用真实业务引擎和PostgreSQL 独立临时 schema，依次执行报修、独立工单查询和确认报修。确认前没有建单；只读查询保留待确认报修；确认后生成工单回执。独立 schema 退出后清理，不调用模型、飞书或生产 API。
