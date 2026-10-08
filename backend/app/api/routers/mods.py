"""Mod 路由:列表/详情/扫描/元数据刷新/本地预览图。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...errors import not_found
from ...models import Mod, ModFile
from ...schemas.api import MetaRefreshIn, ScanIn
from ...services import audit, preview_store, scan, steam
from ...workers.runner import enqueue_task, get_worker
from ..deps import request_ip, require_user, require_user_csrf
from ..views import mod_detail, mod_view, task_view

router = APIRouter(prefix="/api/mods", tags=["mods"])


@router.get("")
def list_mods(db: Session = Depends(get_db),
              _=Depends(require_user),
              q: str = Query(default="", max_length=128),
              inventory_state: str = Query(default=""),
              desired_state: str = Query(default=""),
              apply_state: str = Query(default=""),
              page: int = Query(default=1, ge=1),
              page_size: int = Query(default=50, ge=1, le=200)):
    query = db.query(Mod)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Mod.workshop_id.like(like),
                                 Mod.title_remote.like(like),
                                 Mod.title_local.like(like),
                                 Mod.folder_name.like(like),
                                 Mod.author_name.like(like)))
    if inventory_state:
        query = query.filter(Mod.inventory_state == inventory_state)
    if desired_state:
        query = query.filter(Mod.desired_state == desired_state)
    if apply_state:
        query = query.filter(Mod.apply_state == apply_state)
    total = query.count()
    rows = (query.order_by(Mod.title_remote, Mod.workshop_id)
            .offset((page - 1) * page_size).limit(page_size).all())
    return {"items": [mod_view(m) for m in rows], "total": total,
            "page": page, "page_size": page_size}


@router.get("/{wid}/preview")
def mod_preview(wid: str, db: Session = Depends(get_db), _=Depends(require_user)):
    """本地预览图:扫描时已下载的封面直接回文件;无本地图时回退在线代理。"""
    m = db.get(Mod, wid)
    if m is None:
        raise not_found(f"Mod {wid} 未登记")
    p = preview_store.find_preview(get_settings(), wid)
    if p is not None:
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})
    if (m.preview_url or "").strip():
        # 尚未落盘:重定向到安全代理即时拉取,不阻塞列表显示
        return RedirectResponse("/api/preview?url=" + quote(m.preview_url, safe=""),
                                status_code=302)
    raise not_found("暂无本地预览图,且该 Mod 没有可用的远程封面地址")


@router.get("/{wid}")
def get_mod(wid: str, db: Session = Depends(get_db), _=Depends(require_user)):
    m = db.get(Mod, wid)
    if m is None:
        raise not_found(f"Mod {wid} 未登记")
    files = (db.query(ModFile).filter(ModFile.workshop_id == wid)
             .order_by(ModFile.rel_path).limit(1000).all())
    return mod_detail(m, files)


@router.post("/scan")
def start_scan(body: ScanIn, request: Request,
               s_user: tuple = Depends(require_user_csrf),
               db: Session = Depends(get_db)):
    _, user = s_user
    task = enqueue_task(db, "scan", {"deep": body.deep})
    audit.log(db, actor=user.username, action="scan.start",
              detail={"deep": body.deep}, ip=request_ip(request))
    db.commit()
    get_worker().wakeup()
    return {"task": task_view(task)}


@router.post("/metadata/refresh")
def refresh_meta(body: MetaRefreshIn, request: Request,
                 s_user: tuple = Depends(require_user_csrf),
                 db: Session = Depends(get_db)):
    _, user = s_user
    settings = get_settings()
    ids = body.ids
    if not ids:
        rows = db.query(Mod).filter(
            Mod.inventory_state == "present").all()
        ids = [m.workshop_id for m in rows if not steam.is_fresh(m, settings)]
    task = enqueue_task(db, "metadata_refresh", {"ids": ids}, total=len(ids))
    audit.log(db, actor=user.username, action="metadata.refresh",
              detail={"count": len(ids)}, ip=request_ip(request))
    db.commit()
    get_worker().wakeup()
    return {"task": task_view(task), "ids": ids}
