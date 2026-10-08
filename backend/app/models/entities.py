"""SQLAlchemy 实体。Workshop ID 一律使用十进制字符串(避免 JS 大整数精度问题)。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, ForeignKey, Index, Integer,
                        String, Text, BigInteger)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .. import constants as C


def utcnow() -> datetime:
    """统一使用 naive UTC:SQLite DateTime 列不保留 tzinfo,读回即 naive,
    写入也用 naive 才能保证比较/排序一致。展示层由 views.dt() 补 Z 后缀。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(256), default="")


class Mod(Base):
    """一个 Workshop ID 一行:清单状态、元数据缓存、期望/应用/运行状态与部署信息。"""
    __tablename__ = "mods"
    workshop_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    folder_name: Mapped[str] = mapped_column(String(64), default="")

    # 清单(inventory)
    inventory_state: Mapped[str] = mapped_column(String(16), default=C.InventoryState.PRESENT.value)
    inventory_detail: Mapped[dict] = mapped_column(JSON, default=dict)  # 扫描诊断:包格式/多文件/损坏原因等
    cache_path: Mapped[str] = mapped_column(String(1024), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    cache_mtime: Mapped[float] = mapped_column(BigInteger, default=0)
    source_fingerprint: Mapped[str] = mapped_column(String(128), default="")
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 元数据缓存(Steam 或本地 GMA 回退)
    title_local: Mapped[str] = mapped_column(String(512), default="")
    title_remote: Mapped[str] = mapped_column(String(512), default="")
    author_name: Mapped[str] = mapped_column(String(256), default="")
    author_steamid: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    preview_url: Mapped[str] = mapped_column(String(1024), default="")
    remote_file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    time_published: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    time_updated: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    remote_visibility: Mapped[str] = mapped_column(String(32), default="")
    metadata_state: Mapped[str] = mapped_column(String(16), default="none")  # fresh/stale/error/unavailable/none
    metadata_source: Mapped[str] = mapped_column(String(32), default="")
    metadata_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_error: Mapped[str] = mapped_column(String(512), default="")

    # 状态模型
    desired_state: Mapped[str] = mapped_column(String(16), default=C.DesiredState.UNMANAGED.value)
    apply_state: Mapped[str] = mapped_column(String(16), default=C.ApplyState.UNMANAGED.value)
    apply_error: Mapped[str] = mapped_column(String(1024), default="")
    load_source: Mapped[str] = mapped_column(String(32), default=C.LoadSource.UNMANAGED_CACHE.value)
    load_sources: Mapped[list] = mapped_column(JSON, default=list)  # 全部已知来源(冲突识别)
    runtime_state: Mapped[str] = mapped_column(String(16), default=C.RuntimeState.UNKNOWN.value)
    requires_restart: Mapped[bool] = mapped_column(Boolean, default=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    protected_reason: Mapped[str] = mapped_column(String(256), default="")

    # 部署副本(本地受管模式)
    deploy_version: Mapped[int] = mapped_column(Integer, default=0)
    deploy_path: Mapped[str] = mapped_column(String(1024), default="")
    deploy_size: Mapped[int] = mapped_column(BigInteger, default=0)
    deployed_fingerprint: Mapped[str] = mapped_column(String(128), default="")
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_changed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_mods_desired", "desired_state"),
                      Index("ix_mods_apply", "apply_state"),)


class ModFile(Base):
    """扫描时的文件清单快照,详情页分页展示。"""
    __tablename__ = "mod_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workshop_id: Mapped[str] = mapped_column(ForeignKey("mods.workshop_id"), nullable=False)
    rel_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    mtime: Mapped[int] = mapped_column(BigInteger, default=0)
    note: Mapped[str] = mapped_column(String(256), default="")

    __table_args__ = (Index("ix_modfiles_wid", "workshop_id"),)


class ChangePlan(Base):
    __tablename__ = "change_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), default="batch")  # enable/disable/delete/restore/purge/mode_switch
    status: Mapped[str] = mapped_column(String(24), default=C.PlanStatus.DRAFT.value)
    payload: Mapped[list] = mapped_column(JSON, default=list)   # [{action, workshop_id, params}]
    diff: Mapped[dict] = mapped_column(JSON, default=dict)      # 展示用 diff 与影响
    base_revision: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)   # 提交时分配
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")


class PlanItem(Base):
    __tablename__ = "plan_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("change_plans.id"), nullable=False)
    workshop_id: Mapped[str] = mapped_column(String(24), default="")
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=C.PlanItemStatus.PENDING.value)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (Index("ix_planitems_plan", "plan_id"),)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=C.TaskStatus.QUEUED.value)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    plan_id: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrashEntry(Base):
    __tablename__ = "trash_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # 操作 ID
    workshop_id: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    folder_name: Mapped[str] = mapped_column(String(64), default="")
    original_path: Mapped[str] = mapped_column(String(1024), default="")
    trash_path: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(16), default=C.TrashStatus.IN_TRASH.value)
    original_desired_state: Mapped[str] = mapped_column(String(16), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_by: Mapped[str] = mapped_column(String(64), default="")
    info: Mapped[dict] = mapped_column(JSON, default=dict)  # 原状态/包信息,供恢复展示
    restore_info: Mapped[dict] = mapped_column(JSON, default=dict)


class Exclusion(Base):
    """已禁用/已删除 ID 的排除记录:防止外部重新下载后被自动重新启用。"""
    __tablename__ = "exclusions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workshop_id: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(16), default=C.ExclusionReason.DISABLED.value)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), default="")
    target_id: Mapped[str] = mapped_column(String(128), default="")
    outcome: Mapped[str] = mapped_column(String(16), default="ok")  # ok/fail/blocked
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    request_id: Mapped[str] = mapped_column(String(36), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")


class CollectionSnapshot(Base):
    __tablename__ = "collection_snapshots"
    collection_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list] = mapped_column(JSON, default=list)         # 展开后的普通物品 ID
    sub_collections: Mapped[list] = mapped_column(JSON, default=list)
    inaccessible: Mapped[list] = mapped_column(JSON, default=list)  # 不可访问/查询失败项
    status: Mapped[str] = mapped_column(String(16), default="ok")


class KeyValue(Base):
    """模式接管状态、配置指纹、修订号等应用级状态。"""
    __tablename__ = "kv"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
