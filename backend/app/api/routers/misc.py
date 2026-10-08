"""任务与回收站路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...models import Task
from ...services import audit, trash
from ..deps import request_ip, require_user, require_user_csrf
from ..views import task_view, trash_view

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
def list_tasks(db: Session = Depends(get_db), _=Depends(require_user),
               limit: int = Query(default=30, ge=1, le=200)):
    rows = db.execute(select(Task).order_by(Task.created_at.desc())
                      .limit(limit)).scalars().all()
    return {"items": [task_view(t) for t in rows]}


@router.get("/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db),
             _=Depends(require_user)):
    t = db.get(Task, task_id)
    if t is None:
        from ...errors import not_found
        raise not_found("任务不存在")
    return task_view(t)


trash_router = APIRouter(prefix="/api/trash", tags=["trash"])


@trash_router.get("")
def list_trash(db: Session = Depends(get_db), _=Depends(require_user)):
    return {"items": [trash_view(e) for e in trash.list_entries(db)]}


@trash_router.post("/{entry_id}/restore")
def restore(entry_id: str, request: Request,
            s_user: tuple = Depends(require_user_csrf),
            db: Session = Depends(get_db)):
    _, user = s_user
    out = trash.restore(db, get_settings(), entry_id, actor=user.username)
    db.commit()
    return out


@trash_router.post("/{entry_id}/purge")
def purge(entry_id: str, request: Request,
          s_user: tuple = Depends(require_user_csrf),
          db: Session = Depends(get_db)):
    _, user = s_user
    out = trash.purge(db, get_settings(), entry_id, actor=user.username)
    audit.log(db, actor=user.username, action="trash.purge_api",
              target_type="trash", target_id=entry_id, ip=request_ip(request))
    db.commit()
    return out
