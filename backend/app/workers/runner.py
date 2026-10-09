"""后台任务队列:SQLite 持久化,单 worker 顺序执行(设计约束:面板单实例写入)。

- API 层只负责入库(QUEUED)并唤醒 worker;执行统一在这里,保证同一时刻只有一个任务在跑。
- 启动恢复:上次运行中未完成的任务标记 INTERRUPTED(可见、不可自动续跑),
  关联计划进入 RECOVERY_REQUIRED,由管理员在界面上核对后显式重试。
- 例行维护:过期计划取消、回收站到期清理(每轮循环间隔执行)。
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from .. import constants as C
from ..adapters.loaders import cleanup_work_dirs
from ..config import Settings, get_settings
from ..db import get_session_factory
from ..models.entities import ChangePlan, Task, utcnow
from ..services import audit, plans, preview_store, runtime, scan, steam, trash

log = logging.getLogger("gmm.worker")


def enqueue_task(session, kind: str, payload: dict | None = None,
                 total: int = 0, plan_id: str = "") -> Task:
    task = Task(id=uuid.uuid4().hex, kind=kind[:32],
                status=C.TaskStatus.QUEUED.value,
                payload=payload or {}, total=total, plan_id=plan_id)
    session.add(task)
    return task


# ---------- 任务处理器 ----------

def _run_scan(session, task: Task, settings: Settings) -> dict:
    deep = bool(task.payload.get("deep", True))
    report = scan.run_full_scan(session, settings, deep=deep)
    result: dict = {"summary": report.summary(), "duration_ms": report.duration_ms}
    if settings.auto_fetch_previews:
        # 扫描后自动补齐封面图:缺远程地址的先刷新元数据,再统一下载落盘(内部全容错)
        result["previews"] = preview_store.sync_after_scan(session, settings)
    return result


def _run_metadata_refresh(session, task: Task, settings: Settings) -> dict:
    ids = [str(x) for x in task.payload.get("ids", [])]
    stats = steam.refresh_metadata(session, settings, ids)
    if settings.auto_fetch_previews:
        stats["previews"] = preview_store.ensure_previews(session, settings, ids)
    return stats


def _run_collection_snapshot(session, task: Task, settings: Settings) -> dict:
    cid = str(task.payload.get("collection_id", ""))
    snap = steam.snapshot_collection(session, settings, cid)
    return {"collection_id": snap.collection_id, "items": len(snap.items or []),
            "sub_collections": len(snap.sub_collections or []),
            "inaccessible": len(snap.inaccessible or []), "status": snap.status}


def _run_apply_plan(session, task: Task, settings: Settings) -> dict:
    plans.run_apply_plan(session, task, settings)
    return task.result or {}


HANDLERS = {
    "scan": _run_scan,
    "metadata_refresh": _run_metadata_refresh,
    "collection_snapshot": _run_collection_snapshot,
    "apply_plan": _run_apply_plan,
}


# ---------- worker ----------

class TaskWorker(threading.Thread):
    def __init__(self, settings: Settings | None = None,
                 poll_interval: float = 1.0, housekeeping_seconds: float = 60.0):
        super().__init__(name="gmm-task-worker", daemon=True)
        self.settings = settings or get_settings()
        self.poll_interval = poll_interval
        self.housekeeping_seconds = housekeeping_seconds
        self._stop_evt = threading.Event()
        self._wake_evt = threading.Event()
        self._last_hk = 0.0

    def wakeup(self) -> None:
        self._wake_evt.set()

    def stop(self) -> None:
        self._stop_evt.set()
        self._wake_evt.set()

    def run(self) -> None:
        Session = get_session_factory()
        while not self._stop_evt.is_set():
            try:
                session = Session()
                try:
                    self._tick(session)
                finally:
                    session.close()
            except Exception:
                log.exception("worker 循环异常")
            self._wake_evt.wait(timeout=self.poll_interval)
            self._wake_evt.clear()

    def _tick(self, session) -> None:
        task = self._claim_next(session)
        if task is not None:
            self._execute(session, task)
            return  # 有任务时不做维护,尽快处理下一个
        now = datetime.now(timezone.utc).timestamp()
        if now - self._last_hk >= self.housekeeping_seconds:
            self._last_hk = now
            self._housekeeping(session)

    def _claim_next(self, session) -> Task | None:
        task = session.execute(select(Task).where(Task.status == C.TaskStatus.QUEUED.value)
                               .order_by(Task.created_at, Task.id).limit(1)).scalars().first()
        if task is None:
            return None
        task.status = C.TaskStatus.RUNNING.value
        task.started_at = utcnow()
        session.add(task)
        session.commit()
        return task

    def _execute(self, session, task: Task) -> None:
        handler = HANDLERS.get(task.kind)
        if handler is None:
            task.status = C.TaskStatus.FAILED.value
            task.error = f"未知任务类型:{task.kind}"
            task.finished_at = utcnow()
            session.add(task)
            session.commit()
            return
        try:
            result = handler(session, task, self.settings)
            if task.kind != "apply_plan":  # apply_plan 的状态由 plans 自己落库
                task.status = C.TaskStatus.SUCCEEDED.value
                task.result = result or {}
                task.progress = 100
                task.finished_at = utcnow()
                session.add(task)
                audit.log(session, actor="worker", action=f"task.{task.kind}",
                          target_type="task", target_id=task.id,
                          detail={"result": result if isinstance(result, dict) else {}})
            session.commit()
        except Exception as e:
            session.rollback()
            task.status = C.TaskStatus.FAILED.value
            task.error = str(e)[:2000]
            task.finished_at = utcnow()
            if task.kind == "apply_plan":
                pid = task.payload.get("plan_id", "")
                plan = session.get(ChangePlan, pid) if pid else None
                if plan is not None:
                    plan.status = C.PlanStatus.FAILED.value
                    plan.error = task.error
                    session.add(plan)
            session.add(task)
            audit.log(session, actor="worker", action=f"task.{task.kind}",
                      target_type="task", target_id=task.id, outcome="fail",
                      detail={"error": str(e)[:300]})
            session.commit()
            log.exception("任务 %s(%s) 执行失败", task.id[:8], task.kind)

    def _housekeeping(self, session) -> None:
        try:
            plans.expire_plans(session, self.settings)
            trash.auto_purge_expired(session, self.settings)
            # 服务器重启后自动清除"待重启"标记(依据 srcds 进程启动时刻,见 services.runtime)
            runtime.reconcile_restart_flags(session, self.settings)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("例行维护失败")


_worker: TaskWorker | None = None
_worker_lock = threading.Lock()


def get_worker() -> TaskWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = TaskWorker()
        return _worker


def startup_recovery(settings: Settings | None = None) -> dict:
    """应用启动时调用:中断任务标记、计划恢复标记、过期清理、工作目录清理。"""
    settings = settings or get_settings()
    Session = get_session_factory()
    session = Session()
    try:
        running = session.execute(select(Task).where(
            Task.status == C.TaskStatus.RUNNING.value)).scalars().all()
        interrupted = []
        for t in running:
            t.status = C.TaskStatus.INTERRUPTED.value
            t.finished_at = utcnow()
            t.error = "面板重启时任务仍在执行,状态未知;请人工核对后在计划页重试"
            session.add(t)
            interrupted.append(t.id)
        recovery_plans = plans.mark_interrupted(session)
        expired = plans.expire_plans(session, settings)
        purged = trash.auto_purge_expired(session, settings)
        cleaned = cleanup_work_dirs(settings)
        session.commit()
        out = {"interrupted_tasks": interrupted,
               "recovery_plans": recovery_plans,
               "expired_plans": expired, "purged_trash": purged,
               "cleaned_tmp": cleaned}
        if interrupted or recovery_plans:
            log.warning("启动恢复:中断任务 %s,待恢复计划 %s", interrupted, recovery_plans)
        return out
    finally:
        session.close()
