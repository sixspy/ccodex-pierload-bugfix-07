"""地磅校准状态：全站唯一口径源。

判定期只读 ``weigh_bridges.calibration_valid_until``（校准有效期截止日），
不得拿 ``calibration_date``（上次检定日）冒充，也不得两种口径混用。
五页（车道、总览、对账、过磅、地磅）一律经本模块取值。
"""
from __future__ import annotations

from fastapi import HTTPException

from db import today_iso


def _valid_until(bridge) -> str:
    try:
        value = bridge["calibration_valid_until"]
    except (KeyError, IndexError, TypeError):
        value = (
            bridge.get("calibration_valid_until")
            if isinstance(bridge, dict)
            else None
        )
    return (value or "").strip()


def bridge_calibration_state(bridge, as_of: str | None = None) -> dict:
    """按有效期判定地磅校准状态；仅比较 calibration_valid_until。"""
    today = as_of or today_iso()
    valid_until = _valid_until(bridge)
    if not valid_until:
        state = "未登记"
        ok = False
    elif valid_until < today:
        state = "过期"
        ok = False
    else:
        state = "有效"
        ok = True
    try:
        calibration_date = bridge["calibration_date"]
    except (KeyError, IndexError, TypeError):
        calibration_date = (
            bridge.get("calibration_date") if isinstance(bridge, dict) else None
        )
    return {
        "calibration_date": calibration_date,
        "calibration_valid_until": valid_until or None,
        "calibration_ok": ok,
        "calibration_state": state,
    }


def ensure_bridge_calibrated(bridge, as_of: str | None = None) -> dict:
    """过期/未登记地磅禁止建票：正式册零增拒写。"""
    state = bridge_calibration_state(bridge, as_of)
    if not state["calibration_ok"]:
        valid_until = state["calibration_valid_until"] or "未登记"
        raise HTTPException(
            409,
            f"地磅校准{state['calibration_state']}（有效期 {valid_until}），禁止建票",
        )
    return state


def ticket_calibration_state(ticket, as_of: str | None = None) -> tuple[bool, str]:
    """票是否落在地磅校准有效期内；用于对账剔除过期期间的票。"""
    valid_until = _valid_until(ticket)
    created = (ticket["created_at"] or "")[:10] if ticket["created_at"] else ""
    if not valid_until:
        return False, "地磅校准有效期未登记"
    if created and created > valid_until:
        return False, f"建票日 {created} 晚于校准有效期 {valid_until}"
    return True, ""
