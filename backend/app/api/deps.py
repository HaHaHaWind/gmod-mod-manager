"""路由依赖:会话鉴权、CSRF 校验、登录限速、请求上下文。"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..errors import forbidden, too_many, unauthorized
from ..models import User, UserSession
from ..security import sessions as sess
from ..security.ratelimit import SlidingWindowLimiter

_settings = get_settings()
_n, _w = SlidingWindowLimiter.parse(_settings.login_rate_limit)
login_limiter = SlidingWindowLimiter(_n, _w)


def request_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _bearer_or_cookie(request: Request) -> str | None:
    return request.cookies.get(sess.COOKIE_NAME)


def current_auth(request: Request, db: Session = Depends(get_db)
                 ) -> tuple[UserSession | None, User | None]:
    return sess.get_session_user(db, _bearer_or_cookie(request))


def require_user(request: Request, db: Session = Depends(get_db)
                 ) -> tuple[UserSession, User]:
    s, u = current_auth(request, db)
    if s is None or u is None:
        raise unauthorized()
    return s, u


def require_user_csrf(request: Request, db: Session = Depends(get_db)
                      ) -> tuple[UserSession, User]:
    s, u = require_user(request, db)
    token = request.headers.get(sess.CSRF_HEADER, "")
    if not token or token != s.csrf_token:
        raise forbidden("CSRF 校验失败,请刷新页面后重试", code="csrf_failed")
    return s, u


def check_login_rate(request: Request, username: str) -> None:
    key = f"{request_ip(request)}|{username}"
    if not login_limiter.allow(key):
        raise too_many()
    login_limiter.hit(key)


def login_rate_reset(request: Request, username: str) -> None:
    login_limiter.reset(f"{request_ip(request)}|{username}")
