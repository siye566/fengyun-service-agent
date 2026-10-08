"""工具结果的统一信封。

沿用第四板斧的纪律：错误 = 人话 + 原因 + 下一步（action），
调用方（模型或人）拿到失败也知道该干什么。
"""
from typing import Any


def ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data}


def err(code: str, message: str, action: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message, "action": action}}
