"""审计日志辅助:统一写入 AuditLog,敏感字段脱敏。"""
from __future__ import annotations

from ..models.entities import AuditLog

_SENSITIVE_KEYS = {"password", "token", "secret", "csrf", "cookie", "authorization"}


def redact(detail: dict | None) -> dict:
    """浅层+一层嵌套脱敏:键名含敏感词的值替换为 ***。"""
    if not isinstance(detail, dict):
        return {}
    out: dict = {}
    for k, v in detail.items():
        kl = str(k).lower()
        if any(s in kl for s in _SENSITIVE_KEYS):
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def log(session, *, actor: str, action: str, target_type: str = "",
        target_id: str = "", outcome: str = "ok", detail: dict | None = None,
        request_id: str = "", ip: str = "") -> AuditLog:
    row = AuditLog(
        actor=(actor or "system")[:64],
        action=action[:64],
        target_type=target_type[:32],
        target_id=target_id[:128],
        outcome=outcome[:16],
        detail=redact(detail),
        request_id=request_id[:36],
        ip=ip[:64],
    )
    session.add(row)
    return row
