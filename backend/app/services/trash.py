"""回收站:删除 = 缓存移入 trash/<时间>_<ID>/,可恢复 / 永久删除 / 到期自动清理。

设计要点:
- 移动走 fsops.move_item(跨文件系统安全:暂存复制+校验+原子提交)。
- 每次删除生成独立目录并保留原始文件名,恢复时不重命名。
- 恢复目标路径已存在时拒绝(409),由人工处理,绝不覆盖。
- 永久删除后保留 TrashEntry(PURGED)行作为审计线索,Mod 行随之移除。
"""
from __future__ import annotations

import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import constants as C
from ..config import Settings
from ..errors import ApiError, conflict, not_found, unprocessable
from ..models.entities import (Exclusion, Mod, ModFile, TrashEntry, utcnow)
from . import audit, preview_store
from .fsops import move_item
from .paths import valid_workshop_id


def _entry_dir(settings: Settings, wid: str) -> Path:
    trash_root = settings.trash_path
    if trash_root is None:
        raise ApiError(400, "trash_unconfigured", "未配置 TRASH_ROOT,无法使用回收站")
    ts = utcnow().strftime("%Y%m%d-%H%M%S")
    d = trash_root / f"{ts}_{wid}_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def move_to_trash(session: Session, settings: Settings, wid: str, actor: str = "system",
                  note: str = "") -> TrashEntry:
    """把该 ID 的本地缓存移入回收站,并更新 Mod 状态;返回回收站条目。"""
    valid_workshop_id(wid)
    mod = session.get(Mod, wid)
    if mod is None:
        raise not_found(f"Mod {wid} 未登记")
    if mod.protected:
        raise forbidden_like(f"Mod {wid} 受保护,禁止删除:{mod.protected_reason or '未说明原因'}")
    src = Path(mod.cache_path) if mod.cache_path else None
    if src is None or not src.exists():
        raise unprocessable(f"Mod {wid} 没有可移入回收站的本地缓存", code="nothing_to_trash")

    entry_dir = _entry_dir(settings, wid)
    dst = move_item(src, entry_dir, src.name)
    size = _tree_size(dst)
    files = _tree_count(dst)

    entry = TrashEntry(
        id=uuid.uuid4().hex,
        workshop_id=wid,
        folder_name=mod.folder_name or src.name,
        original_path=str(src),
        trash_path=str(dst),
        status=C.TrashStatus.IN_TRASH.value,
        original_desired_state=mod.desired_state,
        size_bytes=size,
        file_count=files,
        deleted_by=actor,
        info={
            "title": mod.title_remote or mod.title_local,
            "load_sources": list(mod.load_sources or []),
            "note": note,
        },
    )
    session.add(entry)

    # Mod 行保留为 TRASHED 占位(元数据可用于恢复后展示),缓存指针清空
    mod.inventory_state = C.InventoryState.TRASHED.value
    mod.cache_path = ""
    mod.size_bytes = 0
    mod.file_count = 0
    mod.cache_mtime = 0
    mod.source_fingerprint = ""
    mod.missing_since = None
    mod.desired_state = C.DesiredState.UNMANAGED.value
    mod.apply_state = C.ApplyState.UNMANAGED.value
    mod.apply_error = ""
    mod.deploy_version = 0
    mod.deploy_path = ""
    mod.deploy_size = 0
    mod.deployed_fingerprint = ""
    mod.requires_restart = True
    mod.updated_at = utcnow()
    session.add(mod)

    # 排除记录:防止外部工具重新下载后被自动重新启用
    session.add(Exclusion(workshop_id=wid, reason=C.ExclusionReason.DELETED.value,
                          active=True, note=note[:512]))
    audit.log(session, actor=actor, action="mod.trash", target_type="mod", target_id=wid,
              detail={"trash_path": str(dst), "size": size, "note": note})
    return entry


def forbidden_like(msg: str) -> ApiError:
    return ApiError(403, "protected", msg)


def get_entry(session: Session, entry_id: str) -> TrashEntry:
    e = session.get(TrashEntry, entry_id)
    if e is None:
        raise not_found("回收站条目不存在")
    return e


def list_entries(session: Session, status: str = C.TrashStatus.IN_TRASH.value) -> list[TrashEntry]:
    q = select(TrashEntry).order_by(TrashEntry.deleted_at.desc())
    if status:
        q = q.where(TrashEntry.status == status)
    return list(session.execute(q).scalars())


def restore(session: Session, settings: Settings, entry_id: str, actor: str = "system") -> dict:
    e = get_entry(session, entry_id)
    if e.status != C.TrashStatus.IN_TRASH.value:
        raise conflict(f"条目当前状态为 {e.status},不能恢复", code="not_in_trash")
    original = Path(e.original_path)
    dst_dir = original.parent
    if original.exists():
        raise conflict(f"原位置已存在同名内容:{original},请先人工处理", code="restore_target_exists")
    if not dst_dir.is_dir():
        dst_dir.mkdir(parents=True, exist_ok=True)

    src = Path(e.trash_path)
    if not src.exists():
        raise conflict("回收站中的文件已丢失,无法恢复", code="trash_item_missing")

    # 回收站条目目录内是原始文件;move_item 直接移回原位置
    restored = move_item(src, dst_dir, original.name)
    # 清掉空的条目目录
    try:
        src.parent.rmdir()
    except OSError:
        pass

    e.status = C.TrashStatus.RESTORED.value
    e.restore_info = {"restored_at": utcnow().isoformat(), "by": actor, "path": str(restored)}

    mod = session.get(Mod, e.workshop_id)
    if mod is not None:
        mod.inventory_state = C.InventoryState.PRESENT.value
        mod.cache_path = str(restored)
        mod.size_bytes = e.size_bytes
        mod.file_count = e.file_count
        try:
            mod.cache_mtime = restored.stat().st_mtime
        except OSError:
            mod.cache_mtime = 0
        mod.source_fingerprint = ""  # 留空,下次扫描重算
        mod.desired_state = C.DesiredState.UNMANAGED.value  # 恢复≠重新启用,需显式操作
        mod.apply_state = C.ApplyState.UNMANAGED.value
        mod.requires_restart = True
        mod.updated_at = utcnow()
        session.add(mod)
        session.execute(sa_delete(ModFile).where(ModFile.workshop_id == e.workshop_id))

    # 停用"已删除"排除;"已禁用"排除保留(那是另一次显式操作的结果)
    for ex in session.execute(select(Exclusion).where(
            Exclusion.workshop_id == e.workshop_id,
            Exclusion.reason == C.ExclusionReason.DELETED.value,
            Exclusion.active == True)).scalars():  # noqa: E712
        ex.active = False
        session.add(ex)

    audit.log(session, actor=actor, action="mod.restore", target_type="mod",
              target_id=e.workshop_id, detail={"entry": entry_id, "path": str(restored)})
    return {"workshop_id": e.workshop_id, "path": str(restored)}


def purge(session: Session, settings: Settings, entry_id: str, actor: str = "system") -> dict:
    e = get_entry(session, entry_id)
    if e.status != C.TrashStatus.IN_TRASH.value:
        raise conflict(f"条目当前状态为 {e.status},不能永久删除", code="not_in_trash")
    p = Path(e.trash_path)
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p)
    elif p.exists() or p.is_symlink():
        p.unlink()
    try:
        p.parent.rmdir()
    except OSError:
        pass

    e.status = C.TrashStatus.PURGED.value
    wid = e.workshop_id
    session.execute(sa_delete(ModFile).where(ModFile.workshop_id == wid))
    preview_store.delete_preview(settings, wid)  # 本地封面图一并清理
    mod = session.get(Mod, wid)
    if mod is not None:
        session.delete(mod)  # 永久删除后不再保留占位行;重新下载会由扫描重新登记
    audit.log(session, actor=actor, action="mod.purge", target_type="mod", target_id=wid,
              detail={"entry": entry_id})
    return {"workshop_id": wid, "purged": True}


def auto_purge_expired(session: Session, settings: Settings) -> int:
    """按 TRASH_RETENTION_DAYS 清理过期条目;由启动/定时任务调用,actor=system。"""
    days = getattr(settings, "trash_retention_days", 30)
    cutoff = utcnow() - timedelta(days=days)
    rows = session.execute(select(TrashEntry).where(
        TrashEntry.status == C.TrashStatus.IN_TRASH.value,
        TrashEntry.deleted_at < cutoff)).scalars().all()
    n = 0
    for e in rows:
        try:
            purge(session, settings, e.id, actor="system")
            n += 1
        except ApiError:
            continue
    return n


def _tree_size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def _tree_count(p: Path) -> int:
    if p.is_file():
        return 1
    n = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                n += 1
        except OSError:
            continue
    return n
