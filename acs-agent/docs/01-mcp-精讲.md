# MCP 精讲：把工具递到模型手里（第 2 轮第一课）

> 对象：已会 FastAPI 的你。读完能回答：MCP 是什么、stdio 和 HTTP 差在哪、
> Miniclaw 怎么吃下我们的工具、docstring 为什么是给模型看的说明书。

---

## 1. 一句话 + 对照你已有的知识

**MCP（Model Context Protocol）= 工具界的 HTTP API 标准**：把"一个程序能提供哪些工具"规范化，
任何 MCP 宿主（Miniclaw、Claude Code、pi……）都能即插即用地调用，不用为每个宿主写一遍适配。

| 你已经会的（FastAPI） | MCP 世界里的对应物 |
|---|---|
| 你写 FastAPI 服务，暴露 `POST /tickets` | 你写 MCP 服务器，暴露 `create_repair_ticket` 工具 |
| 前端/调用方拿着 OpenAPI 文档发 HTTP 请求 | 模型宿主拿着工具清单发 tool call |
| 参数校验靠 Pydantic | 参数说明靠类型注解 + docstring |
| 返回 JSON | 返回 dict（我们套了信封） |

**区别在传输层**：FastAPI 是"你起服务、监听端口、等请求上门"（HTTP）；
MCP 最常用的是 **stdio**——宿主把你的脚本**当子进程拉起**，通过 stdin/stdout 管道一问一答。
生命周期归宿主管：Miniclaw 启动会话时拉起它，会话结束/闲置时收掉。

```
Miniclaw（宿主）                        acs-server（我们的子进程）
    │  拉起：python -m acs.server           │
    │ ──────────── stdin ──────────────→    │  收到 list_tools → 回工具清单
    │ ←──────────── stdout ─────────────    │  收到 tools/call create_repair_ticket
    │  把结果转给模型，模型继续说话           │  → 查库、落库 → 回信封 JSON
```

## 2. 模型怎么"看到"并"用上"工具（四步）

1. **list_tools**：宿主向服务器要工具清单——函数名 + 类型注解 + **docstring** 打包成模型可读的描述；
2. 模型在对话中决定调用：发出结构化参数（`{"company_name": "...", "device_serial": "..."}`）；
3. 宿主把参数转发给我们的服务器，**真正的 Python 代码在 SQLite 上执行**；
4. 信封结果回传给模型 → 模型把 `advice`/`status_text` 转成人话给客户。

**推论（重要）**：docstring 就是工具的"产品说明书"，读者是模型。
写得含糊，模型就用错时机、漏传参数；写清"什么时候用、需要什么、失败长什么样"，模型就稳。
我们四个工具的 docstring 都按这个标准写的，你可以回头对照 `acs/server.py`。

## 3. 注册三要素：命令 / 参数 / 环境变量

Miniclaw 能力库里"添加 MCP 服务器"（stdio 类型）要填的就是一条**启动命令**。
我们的填法（照抄）：

| 表单项 | 填什么 | 为什么 |
|---|---|---|
| 名称 | `acs-after-sales` | 随意，识别用 |
| 类型 | `stdio` | 我们是子进程型服务器 |
| 命令 | `C:/path/to/acs-agent\.venv\Scripts\python.exe` | **绝对路径**——宿主拉起子进程时不认你的 venv 激活状态 |
| 参数 | `-m` 和 `acs.server`（两行） | `python -m acs.server` = 以模块方式启动，server.py 里的 `mcp.run()` 才会执行 |
| 环境变量 | `PYTHONPATH` = `C:/path/to/acs-agent` | **坑位说明**见下 |
| 描述 | 空压机售后服务工具（报修/保养/工单进度） | 给管理界面看的 |

**为什么必须设 PYTHONPATH**：`python -m acs.server` 要求 Python 能"找到" `acs` 这个包。
找包的范围 = 当前工作目录 + PYTHONPATH。Miniclaw 在哪个目录下拉起子进程是我们控制不了的
（宿主的 CWD 是它自己的项目目录），所以把项目根写进 PYTHONPATH 兜底——
这和"数据库路径用 `__file__` 推导而不是相对路径"（`acs/db.py`）是同一个防御思想：
**不依赖调用方的工作目录**。

## 4. 动手清单（第 2 轮闸门的第 1 格）

1. 启动 Miniclaw（`npm run dev:all`，浏览器开 http://localhost:5173）；
2. **能力库 → MCP 服务器 → 添加**，按上表填（命令里有空格才需要引号，我们没有）；
3. 保存后进入该 MCP 服务器的详情页，确认工具清单里出现 4 个工具：
   `create_repair_ticket / query_maintenance / query_ticket_status / list_company_tickets`；
4. 新建会话测试（真实模型 deepseek-flash[1m]）：
   - "我是示例企业甲，我们的 DEMO-GR75-0001 机器有异响，比较急" → 预期建单、回工单号；
   - "DEMO-GR75-0002 该保养了吗" → 预期报过期状态；
   - "我上次报的工单怎么样了" → 预期按企业列出工单；
   - "我想退货"（意图外）→ 预期不硬答，转人工话术。

## 5. 自测三问（答得上来这课就过了）

1. Miniclaw 重启后，我们的 MCP 服务器进程为什么不需要你手动再启动？（提示：谁拉起的）
2. 如果把命令填成 `python`（不带绝对路径），会在哪种机器状态下失败？为什么？
3. 模型幻觉出"AC-XXXX-9999"去调用工具，我们返回什么？模型拿到后该说什么？（提示：信封的 action 字段 + 系统提示词里怎么规定的）
