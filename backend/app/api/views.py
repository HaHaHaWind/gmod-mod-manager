"""响应序列化:统一附加中文状态标签,日期转 ISO 字符串。"""
from __future__ import annotations

from datetime import datetime

from .. import constants as C
from ..models import (AuditLog, ChangePlan, Mod, ModFile, PlanItem, Task,
                      TrashEntry)


def dt(v: datetime | None) -> str | None:
    # 库内统一 naive UTC,序列化补 Z 让前端按 UTC 解析(避免本地时区偏移)
    if not v:
        return None
    return v.isoformat() + ("Z" if v.tzinfo is None else "")


def mod_view(m: Mod) -> dict:
    return {
        "workshop_id": m.workshop_id,
        "folder_name": m.folder_name,
        "title": m.title_remote or m.title_local or m.folder_name or m.workshop_id,
        "title_remote": m.title_remote,
        "title_local": m.title_local,
        "author_name": m.author_name,
        "author_steamid": m.author_steamid,
        "tags": m.tags or [],
        "preview_url": m.preview_url,
        "size_bytes": m.size_bytes,
        "file_count": m.file_count,
        "inventory_state": m.inventory_state,
        "inventory_zh": C.INVENTORY_ZH.get(m.inventory_state, m.inventory_state),
        "desired_state": m.desired_state,
        "desired_zh": C.DESIRED_ZH.get(m.desired_state, m.desired_state),
        "apply_state": m.apply_state,
        "apply_zh": C.APPLY_ZH.get(m.apply_state, m.apply_state),
        "runtime_state": m.runtime_state,
        "runtime_zh": C.RUNTIME_ZH.get(m.runtime_state, m.runtime_state),
        "requires_restart": m.requires_restart,
        "load_source": m.load_source,
        "load_sources": m.load_sources or [],
        "protected": m.protected,
        "protected_reason": m.protected_reason,
        "metadata_state": m.metadata_state,
        "metadata_error": m.metadata_error,
        "time_updated": m.time_updated,
        "remote_file_size": m.remote_file_size,
        "inventory_detail": m.inventory_detail or {},
    }


def mod_detail(m: Mod, files: list[ModFile]) -> dict:
    view = mod_view(m)
    view.update({
        "description": m.description or "",
        "deploy": {
            "version": m.deploy_version,
            "path": m.deploy_path,
            "size": m.deploy_size,
            "deployed_at": dt(m.deployed_at),
            "source_changed": m.source_changed,
        },
        "cache_path": m.cache_path,
        "cache_mtime": m.cache_mtime,
        "last_scan_at": dt(m.last_scan_at),
        "metadata_fetched_at": dt(m.metadata_fetched_at),
        "metadata_source": m.metadata_source,
        "time_published": m.time_published,
        "remote_visibility": m.remote_visibility,
        "files": [{"rel_path": f.rel_path, "size": f.size, "note": f.note}
                  for f in files],
    })
    return view


def plan_item_view(p: PlanItem) -> dict:
    return {"id": p.id, "workshop_id": p.workshop_id, "action": p.action,
            "status": p.status, "params": p.params or {}, "error": p.error,
            "result": p.result or {}}


def plan_view(p: ChangePlan, items: list[PlanItem] | None = None) -> dict:
    out = {
        "id": p.id, "kind": p.kind, "status": p.status,
        "payload": p.payload or [], "diff": p.diff or {},
        "base_revision": p.base_revision, "revision": p.revision,
        "created_by": p.created_by, "created_at": dt(p.created_at),
        "expires_at": dt(p.expires_at), "applied_at": dt(p.applied_at),
        "error": p.error,
    }
    if items is not None:
        out["items"] = [plan_item_view(i) for i in items]
    return out


def task_view(t: Task) -> dict:
    return {"id": t.id, "kind": t.kind, "status": t.status,
            "progress": t.progress, "total": t.total, "error": t.error,
            "result": t.result or {}, "plan_id": t.plan_id,
            "created_at": dt(t.created_at), "started_at": dt(t.started_at),
            "finished_at": dt(t.finished_at)}


def trash_view(e: TrashEntry) -> dict:
    info = e.info or {}
    return {"id": e.id, "workshop_id": e.workshop_id,
            "title": info.get("title", ""), "folder_name": e.folder_name,
            "original_path": e.original_path, "trash_path": e.trash_path,
            "status": e.status, "original_desired_state": e.original_desired_state,
            "size_bytes": e.size_bytes, "file_count": e.file_count,
            "deleted_at": dt(e.deleted_at), "deleted_by": e.deleted_by,
            "note": info.get("note", ""),
            "restore_info": e.restore_info or {}}


def audit_view(a: AuditLog) -> dict:
    return {"id": a.id, "ts": dt(a.ts), "actor": a.actor, "action": a.action,
            "target_type": a.target_type, "target_id": a.target_id,
            "outcome": a.outcome, "detail": a.detail or {},
            "request_id": a.request_id}
