"""合集展开 / 系统状态 / 审计查询 / 预览代理。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ... import constants as C
from ...config import get_settings
from ...db import check_db, get_db
from ...models import AuditLog, ChangePlan, Mod, Task, TrashEntry
from ...schemas.api import CollectionIn
from ...services import audit, preview, plans, steam
from ...workers.runner import enqueue_task, get_worker
from ..deps import require_user, require_user_csrf, request_ip
from ..views import audit_view, task_view

router = APIRouter(prefix="/api", tags=["system"])


@router.post("/collections/snapshot")
def collection_snapshot(body: CollectionIn, request: Request,
                        s_user: tuple = Depends(require_user_csrf),
                        db: Session = Depends(get_db)):
    _, user = s_user
    task = enqueue_task(db, "collection_snapshot",
                        {"collection_id": body.collection_id})
    audit.log(db, actor=user.username, action="collection.snapshot",
              target_type="collection", target_id=body.collection_id,
              ip=request_ip(request))
    db.commit()
    get_worker().wakeup()
    return {"task": task_view(task)}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db), _=Depends(require_user)):
    s = get_settings()
    active = db.execute(select(ChangePlan).where(
        ChangePlan.status.in_(plans._ACTIVE_PLAN_STATUSES))
        .limit(1)).scalars().first()
    counts = {
        "mods": db.query(func.count(Mod.workshop_id)).scalar() or 0,
        "trashed": db.query(func.count(TrashEntry.id)).filter(
            TrashEntry.status == C.TrashStatus.IN_TRASH.value).scalar() or 0,
        "queued_tasks": db.query(func.count(Task.id)).filter(
            Task.status.in_([C.TaskStatus.QUEUED.value,
                             C.TaskStatus.RUNNING.value])).scalar() or 0,
        "requires_restart": db.query(func.count(Mod.workshop_id)).filter(
            Mod.requires_restart == True).scalar() or 0,  # noqa: E712
    }
    return {
        "management_mode": s.management_mode,
        "local_managed_strategy": s.local_managed_strategy,
        "server_control_mode": s.server_control_mode,
        "read_only": s.read_only,
        "db_ok": check_db(),
        "worker_alive": get_worker().is_alive() if get_worker()._started else None,
        "active_plan_id": active.id if active else None,
        "counts": counts,
        "paths_configured": {
            "gmod_server_root": bool(s.gmod_server_root),
            "workshop_cache_root": bool(s.workshop_cache_root),
            "gmod_addons_root": bool(s.gmod_addons_root),
            "workshop_ids_file": bool(s.workshop_ids_file),
            "trash_root": bool(s.trash_root),
        },
    }


@router.get("/system/audit")
def audit_list(db: Session = Depends(get_db), _=Depends(require_user),
               page: int = Query(default=1, ge=1),
               page_size: int = Query(default=50, ge=1, le=200)):
    q = db.query(AuditLog).order_by(AuditLog.ts.desc(), AuditLog.id.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [audit_view(a) for a in rows], "total": total,
            "page": page, "page_size": page_size}


@router.get("/preview")
def preview_image(url: str = Query(min_length=1, max_length=2048),
                  _=Depends(require_user)):
    settings = get_settings()
    # 整图缓冲后返回:Content-Length 由框架按实际字节生成,
    # 上游断流/超限时抛 ApiError 得到规整 4xx,而非半途断流
    ctype, data = preview.fetch_preview(settings, url)
    return Response(content=data, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=86400"})
