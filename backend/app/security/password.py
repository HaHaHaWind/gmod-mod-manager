from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

_hasher = PasswordHasher()  # Argon2id 默认参数


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def check_password_strength(password: str) -> str | None:
    """返回错误信息;None 表示可用。管理员密码至少 10 位且含字母与数字。"""
    if len(password) < 10:
        return "密码至少 10 位"
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        return "密码必须同时包含字母和数字"
    return None
