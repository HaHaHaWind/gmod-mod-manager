"""请求体模型(pydantic v2)。响应统一手工序列化,便于附加中文状态标签。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PlanItemIn(BaseModel):
    action: str = Field(min_length=1, max_length=16)
    workshop_id: str = Field(min_length=1, max_length=24)
    params: dict = Field(default_factory=dict)


class PlanCreateIn(BaseModel):
    items: list[PlanItemIn] = Field(min_length=1)
    kind: str = Field(default="batch", max_length=32)


class ScanIn(BaseModel):
    deep: bool = True


class MetaRefreshIn(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=500)


class CollectionIn(BaseModel):
    collection_id: str = Field(min_length=1, max_length=24)
