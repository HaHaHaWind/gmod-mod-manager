"""服务端会话:随机 token 仅存哈希;HttpOnly Cookie;退出撤销。CSRF 令牌与会话绑定。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User, UserSession, utcnow

COOKIE_NAME = "gmm_session"
CSRF_HEADER = "x-csrf-token"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, ip: str = "", ua: str = "") -> tuple[str, str]:
    """返回 (token, csrf_token)。"""
    s = get_settings()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = utcnow()
    sess = UserSession(
        id=_hash_token(token), user_id=user.id, csrf_token=csrf,
        created_at=now, expires_at=now + timedelta(hours=s.session_ttl_hours),
        ip=ip[:64], user_agent=ua[:256],
    )
    db.add(sess)
    db.flush()
    return token, csrf


def get_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    sess = db.get(UserSession, _hash_token(token))
    if sess is None or sess.revoked_at is not None:
        return None
    if sess.expires_at < utcnow():
        return None
    return sess


def get_session_user(db: Session, token: str | None) -> tuple[UserSession | None, User | None]:
    sess = get_session(db, token)
    if sess is None:
        return None, None
    user = db.get(User, sess.user_id)
    return sess, user


def revoke_session(db: Session, token: str | None) -> bool:
    sess = get_session(db, token)
    if sess is None:
        return False
    sess.revoked_at = utcnow()
    db.flush()
    return True


def active_session_count(db: Session, user_id: int) -> int:
    q = select(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None),
        UserSession.expires_at > utcnow())
    return len(db.scalars(q).all())
