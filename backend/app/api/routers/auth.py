"""鉴权路由:登录(限速+审计)/ 登出 / 当前用户。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...errors import unauthorized
from ...models import User
from ...schemas.api import LoginIn
from ...security import sessions as sess
from ...services import audit
from ..deps import (check_login_rate, login_rate_reset, request_ip,
                    require_user)
from ..views import dt

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        sess.COOKIE_NAME, token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True, samesite="lax",
        secure=s.public_origin.startswith("https://"), path="/",
    )


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response,
          db: Session = Depends(get_db)):
    ip = request_ip(request)
    check_login_rate(request, body.username)
    from ...security.password import verify_password
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(user.password_hash, body.password):
        audit.log(db, actor=body.username, action="auth.login",
                  outcome="fail", detail={"ip": ip}, ip=ip)
        db.commit()
        raise unauthorized("用户名或密码错误")
    login_rate_reset(request, body.username)
    token, csrf = sess.create_session(db, user, ip=ip,
                                      ua=request.headers.get("user-agent", ""))
    audit.log(db, actor=user.username, action="auth.login",
              detail={"ip": ip}, ip=ip)
    db.commit()
    _set_cookie(response, token)
    return {"username": user.username, "is_admin": user.is_admin,
            "csrf_token": csrf, "expires_at": None}


@router.post("/logout")
def logout(request: Request, response: Response,
           s_user: tuple = Depends(require_user), db: Session = Depends(get_db)):
    s, user = s_user
    token = request.cookies.get(sess.COOKIE_NAME)
    sess.revoke_session(db, token)
    audit.log(db, actor=user.username, action="auth.logout", ip=request_ip(request))
    db.commit()
    response.delete_cookie(sess.COOKIE_NAME, path="/")
    return {"ok": True, "logged_out_at": dt(None)}


@router.get("/me")
def me(s_user: tuple = Depends(require_user)):
    s, user = s_user
    return {"username": user.username, "is_admin": user.is_admin,
            "csrf_token": s.csrf_token, "expires_at": dt(s.expires_at)}
