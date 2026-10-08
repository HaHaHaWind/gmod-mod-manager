"""变更计划路由:创建预览/提交/应用/取消/恢复重试。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...db import get_db
from ...errors import read_only_error
from ...models import ChangePlan
from ...schemas.api import PlanCreateIn
from ...services import audit, plans
from ...workers.runner import enqueue_task, get_worker
from ..deps import request_ip, require_user, require_user_csrf
from ..views import plan_view, task_view

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("")
def list_plans(db: Session = Depends(get_db), _=Depends(require_user),
               status: str = Query(default=""),
               limit: int = Query(default=20, ge=1, le=100)):
    q = db.query(ChangePlan).order_by(ChangePlan.created_at.desc())
    if status:
        q = q.filter(ChangePlan.status == status)
    rows = q.limit(limit).all()
    return {"items": [plan_view(p) for p in rows]}


@router.post("")
def create_plan(body: PlanCreateIn, request: Request,
                s_user: tuple = Depends(require_user_csrf),
                db: Session = Depends(get_db)):
    _, user = s_user
    settings = get_settings()
    plan = plans.create_plan(
        db, settings, actor=user.username,
        items=[i.model_dump() for i in body.items], kind=body.kind,
        request_id=request.headers.get("x-request-id", ""),
        ip=request_ip(request))
    db.commit()
    items = plans.plan_items(db, plan.id)
    return plan_view(plan, items)


@router.get("/{plan_id}")
def get_plan(plan_id: str, db: Session = Depends(get_db),
             _=Depends(require_user)):
    plan = plans.get_plan(db, plan_id)
    return plan_view(plan, plans.plan_items(db, plan_id))


@router.post("/{plan_id}/submit")
def submit(plan_id: str, request: Request,
           s_user: tuple = Depends(require_user_csrf),
           db: Session = Depends(get_db)):
    _, user = s_user
    plan = plans.submit_plan(db, get_settings(), plan_id, actor=user.username,
                             request_id=request.headers.get("x-request-id", ""),
                             ip=request_ip(request))
    db.commit()
    return plan_view(plan, plans.plan_items(db, plan_id))


@router.post("/{plan_id}/apply")
def apply(plan_id: str, request: Request,
          s_user: tuple = Depends(require_user_csrf),
          db: Session = Depends(get_db)):
    _, user = s_user
    settings = get_settings()
    task = plans.enqueue_apply(db, settings, plan_id, actor=user.username,
                               request_id=request.headers.get("x-request-id", ""),
                               ip=request_ip(request))
    db.commit()
    get_worker().wakeup()
    return {"task": task_view(task)}


@router.post("/{plan_id}/cancel")
def cancel(plan_id: str, request: Request,
           s_user: tuple = Depends(require_user_csrf),
           db: Session = Depends(get_db)):
    _, user = s_user
    plan = plans.cancel_plan(db, get_settings(), plan_id, actor=user.username,
                             request_id=request.headers.get("x-request-id", ""),
                             ip=request_ip(request))
    db.commit()
    return plan_view(plan, plans.plan_items(db, plan_id))


@router.post("/{plan_id}/retry")
def retry(plan_id: str, request: Request,
          s_user: tuple = Depends(require_user_csrf),
          db: Session = Depends(get_db)):
    if get_settings().read_only:
        raise read_only_error()
    _, user = s_user
    task = plans.retry_plan(db, get_settings(), plan_id, actor=user.username)
    audit.log(db, actor=user.username, action="plan.retry_api",
              target_type="plan", target_id=plan_id, ip=request_ip(request))
    db.commit()
    get_worker().wakeup()
    return {"task": task_view(task)}


@router.get("/active/current")
def active_plan(db: Session = Depends(get_db), _=Depends(require_user)):
    row = db.execute(select(ChangePlan).where(
        ChangePlan.status.in_(plans._ACTIVE_PLAN_STATUSES))
        .order_by(ChangePlan.created_at.desc()).limit(1)).scalars().first()
    if row is None:
        return {"plan": None}
    return {"plan": plan_view(row)}
