"""绑定管理命令（管理员在服务器本地执行，任务书第七节的身份绑定入口）。

用法：
    python -m acs.bind <scope_key> <企业名称>    # 把会话绑成企业客户
    python -m acs.bind <scope_key> --internal    # 把会话绑成内部角色（全量视图）
    python -m acs.bind --list                    # 列出全部绑定

scope_key = Miniclaw 的 chatJid（如 web:main、feishu:ou_xxx）。
未绑定的会话调用工具会收到 caller_unbound 错误，错误信息里自带这条绑定命令。
"""
import sys
from datetime import datetime

from .db import connect

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def bind(scope_key: str, company_name: str = "", internal: bool = False,
         db_path: str | None = None) -> dict:
    if not scope_key.strip():
        return {"bound": False, "reason": "scope_key 不能为空"}
    if not internal and not company_name.strip():
        return {"bound": False, "reason": "企业客户绑定需要企业名称（或用 --internal）"}
    role = "internal" if internal else "company"
    conn = connect(db_path)
    try:
        if role == "company":
            device = conn.execute(
                "SELECT COUNT(*) AS n FROM devices WHERE company_name = ?",
                (company_name.strip(),),
            ).fetchone()["n"]
            if device == 0:
                print(f"提示：台账中没有企业 {company_name.strip()} 的设备，绑定仍会生效")
        conn.execute(
            "INSERT OR REPLACE INTO company_bindings"
            " (scope_key, company_name, role, bound_at) VALUES (?, ?, ?, ?)",
            (scope_key.strip(), "" if internal else company_name.strip(), role,
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return {"bound": True, "scope_key": scope_key.strip(), "role": role,
                "company_name": "" if internal else company_name.strip()}
    finally:
        conn.close()


def main(argv: list[str]) -> int:
    if not argv[1:] or argv[1] == "--list":
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT scope_key, role, company_name, bound_at FROM company_bindings"
                " ORDER BY bound_at"
            ).fetchall()
            print(f"共 {len(rows)} 条绑定：")
            for row in rows:
                print(f"  {row['scope_key']}  →  {row['role']}"
                      + (f" ({row['company_name']})" if row["company_name"] else ""))
            return 0
        finally:
            conn.close()
    scope_key = argv[1]
    internal = "--internal" in argv[2:]
    company_name = next((a for a in argv[2:] if not a.startswith("--")), "")
    result = bind(scope_key, company_name, internal)
    print(result)
    return 0 if result["bound"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
