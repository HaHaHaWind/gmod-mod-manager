"""启动恢复:中断任务标记 / APPLYING 计划转待恢复 / 过期计划清理 / 暂存残留。"""
from datetime import timedelta

from app.models import ChangePlan, Task, utcnow
from app.services import plans
from app.services.idsfile import parse_ids_file
from app.workers.runner import cleanup_work_dirs, startup_recovery
from tests.conftest import WID_A, make_mod_present, wait_task

_ONE_MIN = timedelta(minutes=1)


def _crash_scene(db, settings, wid=WID_A):
    """构造"应用中途断电"现场:APPLYING 计划 + RUNNING 任务。"""
    make_mod_present(db, settings, wid)
    plan = plans.create_plan(db, settings, actor="tester",
                             items=[{"action": "enable", "workshop_id": wid}])
    plans.submit_plan(db, settings, plan.id, actor="tester")
    plan.status = "applying"                       # 模拟执行中崩溃
    task = Task(id="crashtask0001", kind="apply_plan", status="running",
                payload={"plan_id": plan.id, "actor": "tester"},
                total=1, plan_id=plan.id)
    db.add(task)
    db.commit()
    return plan, task


def test_startup_recovery_marks_interrupted(db, dirs, settings):
    plan, task = _crash_scene(db, settings)
    out = startup_recovery(settings)
    assert task.id in out["interrupted_tasks"]
    assert plan.id in out["recovery_plans"]
    db.expire_all()
    t = db.get(Task, task.id)
    p = db.get(ChangePlan, plan.id)
    assert t.status == "interrupted"
    assert "人工核对" in t.error
    assert p.status == "recovery_required"


def test_retry_recovery_plan_reruns_and_applies(auth, db, dirs, settings):
    settings.management_mode = "native_ids"
    settings.read_only = False
    plan, _task = _crash_scene(db, settings)
    startup_recovery(settings)

    r = auth.post(f"/api/plans/{plan.id}/retry")
    assert r.status_code == 200, r.text
    task_id = r.json()["task"]["id"]
    assert wait_task(auth, task_id) == "succeeded"

    db.expire_all()
    p = db.get(ChangePlan, plan.id)
    assert p.status == "applied"
    assert parse_ids_file(settings.ids_file) == [WID_A]


def test_retry_rejects_non_recovery_plan(auth, db, dirs, settings):
    settings.read_only = False
    make_mod_present(db, settings, WID_A)
    plan = plans.create_plan(db, settings, actor="tester",
                             items=[{"action": "enable", "workshop_id": WID_A}])
    db.commit()
    r = auth.post(f"/api/plans/{plan.id}/retry")
    assert r.status_code == 409
    assert r.json()["code"] == "bad_plan_status"


def test_retry_rejected_in_read_only(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    plan = plans.create_plan(db, settings, actor="tester",
                             items=[{"action": "enable", "workshop_id": WID_A}])
    plan.status = "recovery_required"
    db.commit()
    r = auth.post(f"/api/plans/{plan.id}/retry")
    assert r.status_code == 403
    assert r.json()["code"] == "read_only"


def test_expire_plans_cancels_stale_draft(db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    plan = plans.create_plan(db, settings, actor="tester",
                             items=[{"action": "enable", "workshop_id": WID_A}])
    plan.expires_at = utcnow() - _ONE_MIN
    db.commit()
    n = plans.expire_plans(db, settings)
    db.commit()
    assert n == 1
    db.expire_all()
    assert db.get(ChangePlan, plan.id).status == "cancelled"


def test_cleanup_work_dirs_removes_tmp_residue(dirs, settings):
    tmp = settings.addons_root / ".gmm-move-abcd1234"
    tmp.mkdir(parents=True)
    (tmp / "x.tmp").write_bytes(b"1")
    n = cleanup_work_dirs(settings)
    assert n >= 1
    assert not tmp.exists()
