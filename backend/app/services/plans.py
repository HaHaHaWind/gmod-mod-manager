"""变更计划:预览 → 提交 → 应用 的完整生命周期,是所有写操作的唯一入口。

状态机: DRAFT → STAGED → APPLYING → APPLIED / FAILED / RECOVERY_REQUIRED;DRAFT/STAGED 可取消。
- 创建(DRAFT):校验动作与 ID、去重、逐项预检(阻塞项不落库为可应用项)、生成 diff 预览。
- 提交(STAGED):分配修订号、快照 before 状态、把期望状态置为 PENDING;全局仅允许一个进行中的计划。
- 应用:由任务队列(workers/runner)以单 worker 顺序逐项调用适配器;delete 随后进回收站。
- 中断恢复:启动时把 APPLYING 计划标记 RECOVERY_REQUIRED,可核对实际状态后重放剩余项。

硬边界:只读模式阻止应用;本模块绝不杀进程、绝不自动重启(requires_restart 只是标记)。
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import constants as C
from ..adapters.loaders import AdapterContext, get_adapter
from ..config import Settings, get_settings
from ..errors import (ApiError, bad_request, conflict, not_found,
                      read_only_error, unprocessable)
from ..models.entities import (ChangePlan, KeyValue, Mod, PlanItem, Task,
                               utcnow)
from . import audit, trash

_ACTIVE_PLAN_STATUSES = (C.PlanStatus.STAGED.value, C.PlanStatus.APPLYING.value,
                         C.PlanStatus.RECOVERY_REQUIRED.value)
_VALID_ACTIONS = {C.ModAction.ENABLE.value, C.ModAction.DISABLE.value,
                  C.ModAction.DELETE.value}


# ---------- 预测与 diff ----------

def _predict(mod: Mod, action: str) -> dict:
    to = {
        "inventory": mod.inventory_state,
        "desired": mod.desired_state,
        "apply": mod.apply_state,
    }
    if action == C.ModAction.ENABLE.value:
        to["desired"] = C.DesiredState.ENABLED.value
        to["apply"] = C.ApplyState.SYNCED.value
    elif action == C.ModAction.DISABLE.value:
        to["desired"] = C.DesiredState.DISABLED.value
        to["apply"] = C.ApplyState.SYNCED.value
    elif action == C.ModAction.DELETE.value:
        to["desired"] = C.DesiredState.UNMANAGED.value
        to["apply"] = C.ApplyState.UNMANAGED.value
        to["inventory"] = C.InventoryState.TRASHED.value
    return to


def _normalize_items(items: list[dict], settings: Settings) -> tuple[list[dict], list[dict]]:
    """校验 + 去重(同一 ID 保留最后一个动作)。返回 (规范化列表, 去重警告)。"""
    if not items:
        raise bad_request("计划不能为空", code="empty_plan")
    if len(items) > settings.max_action_ids:
        raise unprocessable(f"单次计划最多 {settings.max_action_ids} 项,请拆分提交",
                            code="too_many_items")
    seen: dict[str, dict] = {}
    dupes: set[str] = set()
    order: list[str] = []
    for it in items:
        action = str(it.get("action", "")).strip().lower()
        wid = str(it.get("workshop_id", "")).strip()
        if action not in _VALID_ACTIONS:
            raise unprocessable(f"未知动作:{action or '(空)'}(允许 enable/disable/delete)",
                                code="bad_action")
        try:
            from .paths import valid_workshop_id
            valid_workshop_id(wid)
        except ApiError:
            raise unprocessable(f"非法 Workshop ID:{wid!r}(必须为十进制整数且 ≤ 2^63-1)",
                                code="bad_workshop_id")
        if wid in seen:
            dupes.add(wid)
        else:
            order.append(wid)
        seen[wid] = {"action": action, "workshop_id": wid,
                     "params": dict(it.get("params") or {})}
    warns = [{"workshop_id": w, "message": "同一计划中重复出现,已保留最后一个动作"} for w in sorted(dupes)]
    return [seen[w] for w in order], warns


def create_plan(session: Session, settings: Settings, actor: str,
                items: list[dict], kind: str = "batch",
                request_id: str = "", ip: str = "") -> ChangePlan:
    norm, dupe_warns = _normalize_items(items, settings)
    ctx = AdapterContext(session, settings, actor)
    adapter = get_adapter(ctx)

    infos: list[dict] = []
    blockers: list[dict] = []
    counts = {"enable": 0, "disable": 0, "delete": 0, "blocked": 0}
    plan_items: list[PlanItem] = []

    for it in norm:
        wid, action = it["workshop_id"], it["action"]
        mod = session.get(Mod, wid)
        title = (mod.title_remote or mod.title_local) if mod else ""
        info = {
            "workshop_id": wid,
            "action": action,
            "title": title,
            "from": ({k: getattr(mod, k) for k in
                      ("inventory_state", "desired_state", "apply_state")} if mod else None),
            "to": _predict(mod, action) if mod else None,
            "warnings": [],
            "blocked": False,
            "block_reason": "",
        }
        for w in dupe_warns:
            if w["workshop_id"] == wid:
                info["warnings"].append(w["message"])
        if mod is None:
            info["blocked"] = True
            info["block_reason"] = "该 ID 未登记,请先执行扫描"
        else:
            try:
                info["warnings"].extend(w.get("message", "") for w in adapter.check(action, wid))
            except ApiError as e:
                info["blocked"] = True
                info["block_reason"] = e.message
        if info["blocked"]:
            counts["blocked"] += 1
            blockers.append({"workshop_id": wid, "action": action, "reason": info["block_reason"]})
        else:
            counts[action] += 1
        plan_items.append(PlanItem(plan_id="", workshop_id=wid, action=action,
                                   status=C.PlanItemStatus.PENDING.value,
                                   params=it["params"]))
        infos.append(info)

    plan = ChangePlan(
        id=uuid.uuid4().hex,
        kind=kind[:32],
        status=C.PlanStatus.DRAFT.value,
        payload=[{"action": p.action, "workshop_id": p.workshop_id, "params": p.params}
                 for p in plan_items],
        diff={"per_item": infos,
              "blockers": blockers, "summary": counts,
              "mode": settings.management_mode, "strategy": settings.local_managed_strategy},
        created_by=actor[:64],
        expires_at=utcnow() + timedelta(minutes=settings.plan_ttl_minutes),
    )
    session.add(plan)
    session.flush()  # 取得 plan.id 供 items 外键使用
    for p in plan_items:
        p.plan_id = plan.id
        session.add(p)

    audit.log(session, actor=actor, action="plan.create", target_type="plan",
              target_id=plan.id, request_id=request_id, ip=ip,
              detail={"kind": kind, "summary": counts})
    return plan


def get_plan(session: Session, plan_id: str) -> ChangePlan:
    p = session.get(ChangePlan, plan_id)
    if p is None:
        raise not_found("变更计划不存在")
    return p


def plan_items(session: Session, plan_id: str) -> list[PlanItem]:
    q = select(PlanItem).where(PlanItem.plan_id == plan_id).order_by(PlanItem.id)
    return list(session.execute(q).scalars())


# ---------- 提交 ----------

def _next_revision(session: Session) -> int:
    kv = session.get(KeyValue, "plan:revision")
    n = int((kv.value or {}).get("n", 0)) + 1 if kv else 1
    if kv is None:
        kv = KeyValue(key="plan:revision", value={"n": n})
    else:
        kv.value = {"n": n}
    session.add(kv)
    return n


def submit_plan(session: Session, settings: Settings, plan_id: str,
                actor: str, request_id: str = "", ip: str = "") -> ChangePlan:
    plan = get_plan(session, plan_id)
    if plan.status not in (C.PlanStatus.DRAFT.value,):
        raise conflict(f"计划当前状态为 {plan.status},只有草稿可以提交", code="bad_plan_status")
    if plan.expires_at and plan.expires_at < utcnow():
        raise conflict("计划已过期,请重新创建", code="plan_expired")
    items = plan_items(session, plan_id)
    blocked = [p for p in items if _blocked_of(plan, p)]
    if blocked:
        raise unprocessable(f"计划包含 {len(blocked)} 个阻塞项,请移除后重新创建计划",
                            code="plan_has_blockers",
                            details=[{"workshop_id": p.workshop_id, "action": p.action}
                                     for p in blocked])

    active = session.execute(select(ChangePlan).where(
        ChangePlan.status.in_(_ACTIVE_PLAN_STATUSES))).scalars().first()
    if active is not None and active.id != plan.id:
        raise conflict(f"已有进行中的计划({active.id[:8]}…),请先完成或取消", code="active_plan_exists")

    plan.revision = _next_revision(session)
    plan.status = C.PlanStatus.STAGED.value
    for p in items:
        mod = session.get(Mod, p.workshop_id)
        if mod is None:
            continue
        p.params = {**(p.params or {}), "before": {
            "desired": mod.desired_state, "apply": mod.apply_state}}
        # 期望状态立即更新;apply_state 置 PENDING 表示"配置尚未落盘"
        if p.action == C.ModAction.ENABLE.value:
            mod.desired_state = C.DesiredState.ENABLED.value
        elif p.action == C.ModAction.DISABLE.value:
            mod.desired_state = C.DesiredState.DISABLED.value
        elif p.action == C.ModAction.DELETE.value:
            mod.desired_state = C.DesiredState.UNMANAGED.value
        mod.apply_state = C.ApplyState.PENDING.value
        session.add(mod)
        p.status = C.PlanItemStatus.STAGED.value
        session.add(p)
    session.add(plan)
    audit.log(session, actor=actor, action="plan.submit", target_type="plan",
              target_id=plan.id, request_id=request_id, ip=ip,
              detail={"revision": plan.revision})
    return plan


def _blocked_of(plan: ChangePlan, item: PlanItem) -> bool:
    for d in (plan.diff or {}).get("per_item", []):
        if d.get("workshop_id") == item.workshop_id and d.get("action") == item.action:
            return bool(d.get("blocked"))
    return False


# ---------- 应用(由任务队列调用) ----------

def enqueue_apply(session: Session, settings: Settings, plan_id: str,
                  actor: str, request_id: str = "", ip: str = "") -> Task:
    if settings.read_only:
        raise read_only_error()
    plan = get_plan(session, plan_id)
    if plan.status not in (C.PlanStatus.STAGED.value,
                           C.PlanStatus.RECOVERY_REQUIRED.value):
        raise conflict(f"计划当前状态为 {plan.status},不能应用", code="bad_plan_status")
    items = plan_items(session, plan_id)
    task = Task(id=uuid.uuid4().hex, kind="apply_plan",
                status=C.TaskStatus.QUEUED.value,
                payload={"plan_id": plan.id, "actor": actor},
                total=len(items), plan_id=plan.id)
    session.add(task)
    audit.log(session, actor=actor, action="plan.enqueue", target_type="plan",
              target_id=plan.id, request_id=request_id, ip=ip,
              detail={"task": task.id})
    return task


def run_apply_plan(session: Session, task: Task, settings: Settings | None = None) -> None:
    """任务 worker 入口:顺序执行计划内各项;每项独立提交粒度,失败不阻断后续项。"""
    settings = settings or get_settings()
    plan = get_plan(session, task.payload.get("plan_id", ""))
    if settings.read_only:
        _fail_task(task, plan, "只读模式阻止了应用")
        return
    items = plan_items(session, plan.id)
    todo = [p for p in items if p.status in (C.PlanItemStatus.PENDING.value,
                                             C.PlanItemStatus.STAGED.value)]
    plan.status = C.PlanStatus.APPLYING.value
    task.status = C.TaskStatus.RUNNING.value
    task.started_at = utcnow()
    session.add(plan)
    session.add(task)
    session.commit()

    ctx = AdapterContext(session, settings, task.payload.get("actor", "system"))
    adapter = get_adapter(ctx)
    done = failed = 0
    errors: list[dict] = []

    for p in todo:
        wid, action = p.workshop_id, p.action
        try:
            result = adapter.apply(action, wid, p.params or {})
            note = ""
            if action == C.ModAction.DELETE.value:
                result, note = _after_delete(session, settings, wid, result, ctx.actor)
            mod = session.get(Mod, wid)
            if mod is not None:
                if action != C.ModAction.DELETE.value:
                    adapter._post_apply(mod, action, result)
                elif note:
                    # 无缓存可进回收站:仅加载入口已移除,状态直接落到已同步
                    mod.desired_state = C.DesiredState.UNMANAGED.value
                    mod.apply_state = C.ApplyState.SYNCED.value
                    mod.requires_restart = True
                    session.add(mod)
            p.status = C.PlanItemStatus.DONE.value
            p.result = {**result, "note": note} if note else result
            p.error = ""
            done += 1
        except ApiError as e:
            p.status = C.PlanItemStatus.FAILED.value
            p.error = e.message[:2000]
            p.result = {"code": e.code}
            mod = session.get(Mod, wid)
            if mod is not None:
                adapter._post_failed(mod, e.message)
            failed += 1
            errors.append({"workshop_id": wid, "action": action,
                           "code": e.code, "message": e.message})
        except Exception as e:  # 兜底:任何异常都不得让 worker 崩溃
            p.status = C.PlanItemStatus.FAILED.value
            p.error = f"内部错误:{e}"[:2000]
            failed += 1
            errors.append({"workshop_id": wid, "action": action, "code": "internal",
                           "message": str(e)[:300]})
        session.add(p)
        task.progress = int((done + failed) * 100 / max(1, len(todo)))
        session.add(task)
        session.commit()

    plan.applied_at = utcnow()
    if failed:
        plan.status = C.PlanStatus.FAILED.value
        plan.error = f"{failed} 项失败:" + "; ".join(
            f"{e['workshop_id']}({e['code']})" for e in errors[:10])
        task.status = C.TaskStatus.FAILED.value
        task.error = plan.error
    else:
        plan.status = C.PlanStatus.APPLIED.value
        plan.error = ""
        task.status = C.TaskStatus.SUCCEEDED.value
    task.result = {"done": done, "failed": failed, "errors": errors[:50]}
    task.finished_at = utcnow()
    session.add(plan)
    session.add(task)
    audit.log(session, actor=task.payload.get("actor", "system"), action="plan.apply",
              target_type="plan", target_id=plan.id,
              outcome="ok" if not failed else "fail",
              detail={"done": done, "failed": failed})
    session.commit()


def _after_delete(session: Session, settings: Settings, wid: str, result: dict,
                  actor: str) -> tuple[dict, str]:
    """delete 动作:加载入口已移除,再把缓存移入回收站。"""
    try:
        entry = trash.move_to_trash(session, settings, wid, actor=actor)
        result = {**result, "trash_entry": entry.id, "trash_path": entry.trash_path}
        return result, ""
    except ApiError as e:
        if e.code == "nothing_to_trash":
            return result, "无本地缓存,仅移除了加载入口"
        raise


def _fail_task(task: Task, plan: ChangePlan, msg: str) -> None:
    task.status = C.TaskStatus.FAILED.value
    task.error = msg
    task.finished_at = utcnow()
    plan.status = C.PlanStatus.FAILED.value
    plan.error = msg


# ---------- 取消 / 过期 / 恢复 ----------

def cancel_plan(session: Session, settings: Settings, plan_id: str,
                actor: str, request_id: str = "", ip: str = "") -> ChangePlan:
    plan = get_plan(session, plan_id)
    if plan.status not in (C.PlanStatus.DRAFT.value, C.PlanStatus.STAGED.value):
        raise conflict(f"计划当前状态为 {plan.status},不能取消", code="bad_plan_status")
    if plan.status == C.PlanStatus.STAGED.value:
        _revert_desired(session, plan)
    plan.status = C.PlanStatus.CANCELLED.value
    for p in plan_items(session, plan_id):
        if p.status in (C.PlanItemStatus.PENDING.value, C.PlanItemStatus.STAGED.value):
            p.status = C.PlanItemStatus.SKIPPED.value
            session.add(p)
    session.add(plan)
    audit.log(session, actor=actor, action="plan.cancel", target_type="plan",
              target_id=plan.id, request_id=request_id, ip=ip)
    return plan


def _revert_desired(session: Session, plan: ChangePlan) -> None:
    """取消已提交计划:按 before 快照恢复 desired/apply,撤销 PENDING 标记。"""
    for p in plan_items(session, plan.id):
        before = (p.params or {}).get("before") or {}
        if not before:
            continue
        mod = session.get(Mod, p.workshop_id)
        if mod is None:
            continue
        mod.desired_state = before.get("desired", mod.desired_state)
        mod.apply_state = before.get("apply", mod.apply_state)
        session.add(mod)


def expire_plans(session: Session, settings: Settings) -> int:
    """把过期的 DRAFT/STAGED 计划取消(含期望状态回滚)。返回处理数量。"""
    rows = session.execute(select(ChangePlan).where(
        ChangePlan.status.in_([C.PlanStatus.DRAFT.value, C.PlanStatus.STAGED.value]),
        ChangePlan.expires_at != None,  # noqa: E711
        ChangePlan.expires_at < utcnow())).scalars().all()
    n = 0
    for plan in rows:
        try:
            cancel_plan(session, settings, plan.id, actor="system")
            n += 1
        except ApiError:
            continue
    return n


def mark_interrupted(session: Session) -> list[str]:
    """启动时调用:把 APPLYING 计划标记为 RECOVERY_REQUIRED(对应的 RUNNING 任务由 runner 处理)。"""
    rows = session.execute(select(ChangePlan).where(
        ChangePlan.status == C.PlanStatus.APPLYING.value)).scalars().all()
    ids = []
    for plan in rows:
        plan.status = C.PlanStatus.RECOVERY_REQUIRED.value
        session.add(plan)
        ids.append(plan.id)
    return ids


def verify_done_items(session: Session, settings: Settings, plan: ChangePlan) -> list[dict]:
    """恢复前核对已应用项的真实状态;不一致的项退回 PENDING。返回核对报告。"""
    report: list[dict] = []
    ctx = AdapterContext(session, settings, "system")
    adapter = get_adapter(ctx)
    ids_now: set[str] | None = None
    if settings.management_mode == "native_ids":
        try:
            from .idsfile import parse_ids_file
            if settings.ids_file and settings.ids_file.exists():
                ids_now = set(parse_ids_file(settings.ids_file))
        except Exception:
            ids_now = None
    for p in plan_items(session, plan.id):
        if p.status != C.PlanItemStatus.DONE.value:
            continue
        ok, how = True, "assumed"
        mod = session.get(Mod, p.workshop_id)
        if settings.management_mode == "native_ids" and ids_now is not None:
            inside = p.workshop_id in ids_now
            if p.action == C.ModAction.ENABLE.value:
                ok = inside
            else:
                ok = not inside
            how = "ids_file"
        elif settings.management_mode == "local_managed" and mod is not None \
                and hasattr(adapter, "verify_actual"):
            actual = adapter.verify_actual(mod)
            if p.action == C.ModAction.ENABLE.value:
                ok = actual == "deployed"
            elif p.action == C.ModAction.DISABLE.value:
                ok = actual in ("absent", "unknown")
            how = f"managed:{actual}"
        if not ok:
            p.status = C.PlanItemStatus.PENDING.value
            p.error = "恢复核对:实际状态与记录不符,已重新排队"
            session.add(p)
        report.append({"workshop_id": p.workshop_id, "action": p.action,
                       "ok": ok, "how": how})
    return report


def retry_plan(session: Session, settings: Settings, plan_id: str, actor: str) -> Task:
    """对 RECOVERY_REQUIRED 计划:先核对已应用项,再重新排队剩余项。"""
    if settings.read_only:
        raise read_only_error()
    plan = get_plan(session, plan_id)
    if plan.status != C.PlanStatus.RECOVERY_REQUIRED.value:
        raise conflict(f"计划当前状态为 {plan.status},只有待恢复计划可以重试", code="bad_plan_status")
    report = verify_done_items(session, settings, plan)
    items = plan_items(session, plan_id)
    task = Task(id=uuid.uuid4().hex, kind="apply_plan",
                status=C.TaskStatus.QUEUED.value,
                payload={"plan_id": plan.id, "actor": actor, "recovery": True,
                         "verify": report},
                total=sum(1 for p in items if p.status in
                          (C.PlanItemStatus.PENDING.value, C.PlanItemStatus.STAGED.value)),
                plan_id=plan.id)
    session.add(task)
    audit.log(session, actor=actor, action="plan.retry", target_type="plan",
              target_id=plan.id, detail={"verify": report})
    return task
