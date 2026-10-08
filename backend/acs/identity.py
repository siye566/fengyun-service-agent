"""调用者身份解析与隔离策略（任务书第七节）。

绑定表 company_bindings 是唯一权威：scope_key（Miniclaw chatJid）→ 企业名或
internal 角色。**默认拒绝**：未绑定的会话调任何工具都拿 caller_unbound 错误，
错误里带自己的 scope_key，方便管理员照着绑定。

角色权限：
- internal（售后工程师/财务/管理员）：全量视图，可跨企业查询与代客建单；
- company（企业客户）：只能看到绑定企业的设备与工单；建单强制落到绑定企业；
  列表工具无视传入的企业名（按构造防越权，不靠模型自觉）。
"""
import sqlite3
from datetime import datetime

from .results import err

ROLE_INTERNAL = "internal"
ROLE_COMPANY = "company"
ROLE_UNBOUND = "unbound"


def resolve_caller(conn: sqlite3.Connection, scope_key: str | None) -> dict:
    if not scope_key or not str(scope_key).strip():
        return {"role": ROLE_UNBOUND, "scope_key": scope_key}
    key = scope_key.strip()
    row = conn.execute(
        "SELECT role, company_name FROM company_bindings WHERE scope_key = ?",
        (key,),
    ).fetchone()
    if row is None and "#" in key:
        # 复合键（chat#agent）回退到工作区基础键：绑定一次工作区，
        # 其中所有会话/定时任务自动继承（精确键仍优先，可做更细的覆盖）
        base = key.split("#", 1)[0]
        row = conn.execute(
            "SELECT role, company_name FROM company_bindings WHERE scope_key = ?",
            (base,),
        ).fetchone()
    if row is None:
        return {"role": ROLE_UNBOUND, "scope_key": key}
    if row["role"] == ROLE_INTERNAL:
        return {"role": ROLE_INTERNAL, "scope_key": key}
    return {
        "role": ROLE_COMPANY,
        "scope_key": key,
        "company_name": row["company_name"],
    }


def unbound_error(scope_key: str | None) -> dict:
    shown = scope_key or "(空)"
    return err(
        "caller_unbound",
        f"当前会话未绑定企业身份（标识 {shown}），按安全边界拒绝访问业务数据",
        f"管理员执行：python -m acs.bind {shown} <企业名称> 或 python -m acs.bind {shown} --internal",
    )


def cross_company_error(kind: str, identifier: str) -> dict:
    return err(
        "cross_company_denied",
        f"该{kind}（{identifier}）不属于贵司台账，跨企业数据严格不可见",
        "如需代维跨企业设备，请走内部渠道由售后人员操作",
    )
