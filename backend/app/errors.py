"""统一错误结构:{code, message(中文), request_id, details}。禁止泄露堆栈与机密。"""
from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 details: Any = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def bad_request(msg: str, code: str = "bad_request", details: Any = None) -> ApiError:
    return ApiError(400, code, msg, details)


def unauthorized(msg: str = "未登录或会话已失效", code: str = "unauthorized") -> ApiError:
    return ApiError(401, code, msg)


def forbidden(msg: str = "权限不足", code: str = "forbidden", details: Any = None) -> ApiError:
    return ApiError(403, code, msg, details)


def not_found(msg: str = "资源不存在", code: str = "not_found") -> ApiError:
    return ApiError(404, code, msg)


def conflict(msg: str, code: str = "conflict", details: Any = None) -> ApiError:
    return ApiError(409, code, msg, details)


def unprocessable(msg: str, code: str = "validation_error", details: Any = None) -> ApiError:
    return ApiError(422, code, msg, details)


def too_many(msg: str = "请求过于频繁,请稍后再试", code: str = "rate_limited") -> ApiError:
    return ApiError(429, code, msg)


def read_only_error() -> ApiError:
    return ApiError(403, "read_only", "当前处于只读模式(READ_ONLY=true),已阻止影响游戏服务器的变更")
