"""变更计划全生命周期:创建预览/阻塞判定/提交/应用/取消/单工失败隔离。"""
import pytest

import app.adapters.loaders as loaders_mod
from app.models import ChangePlan, Mod, PlanItem
from app.services import plans
from app.services.idsfile import IdsFileError, parse_ids_file
from tests.conftest import WID_A, WID_B, make_mod_present, wait_task


def _get_mod(db, wid):
    db.expire_all()
    return db.get(Mod, wid)


def _get_plan(db, pid):
    db.expire_all()
    return db.get(ChangePlan, pid)


def _new_plan(auth, items, kind="batch"):
    r = auth.post("/api/plans", json={"items": items, "kind": kind})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 创建(预览) ----------

def test_create_plan_builds_diff(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    assert body["status"] == "draft"
    assert body["diff"]["summary"]["enable"] == 1
    item = body["diff"]["per_item"][0]
    assert item["workshop_id"] == WID_A and item["action"] == "enable"
    assert item["blocked"] is False and item["block_reason"] == ""
    assert body["diff"]["blockers"] == []
    # to 预测:enable → desired=enabled / apply=synced
    assert item["to"]["desired"] == "enabled"
    assert item["to"]["apply"] == "synced"


def test_create_plan_blocks_unregistered_id(auth, db, dirs):
    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    assert body["diff"]["blockers"], "未登记 ID 应进阻塞列表"
    assert "未登记" in body["diff"]["per_item"][0]["block_reason"]
    # 提交包含阻塞项的计划 → 422
    r = auth.post(f"/api/plans/{body['id']}/submit")
    assert r.status_code == 422
    assert r.json()["code"] == "plan_has_blockers"


def test_create_plan_rejects_bad_action_and_empty(auth, db, dirs):
    r = auth.post("/api/plans", json={"items": [{"action": "frobnicate", "workshop_id": WID_A}]})
    assert r.status_code == 422
    assert r.json()["code"] == "bad_action"
    r = auth.post("/api/plans", json={"items": []})
    assert r.status_code == 422  # pydantic min_length=1


# ---------- 提交 / 取消 ----------

def test_submit_stages_desired_with_before_snapshot(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    r = auth.post(f"/api/plans/{body['id']}/submit")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "staged"
    mod = _get_mod(db, WID_A)
    assert mod.desired_state == "enabled"
    assert mod.apply_state == "pending"          # 配置尚未落盘
    item = db.query(PlanItem).filter(PlanItem.plan_id == body["id"]).one()
    assert item.params["before"] == {"desired": "unmanaged", "apply": "unmanaged"}
    assert item.status == "staged"


def test_cancel_reverts_desired_to_before(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    auth.post(f"/api/plans/{body['id']}/submit")
    r = auth.post(f"/api/plans/{body['id']}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    mod = _get_mod(db, WID_A)
    assert mod.desired_state == "unmanaged"      # 回滚到 before 快照
    assert mod.apply_state == "unmanaged"
    item = db.query(PlanItem).filter(PlanItem.plan_id == body["id"]).one()
    assert item.status == "skipped"


def test_only_one_active_plan_allowed(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    make_mod_present(db, settings, WID_B)
    p1 = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    r = auth.post(f"/api/plans/{p1['id']}/submit")
    assert r.status_code == 200
    p2 = _new_plan(auth, [{"action": "enable", "workshop_id": WID_B}])
    r = auth.post(f"/api/plans/{p2['id']}/submit")
    assert r.status_code == 409
    assert r.json()["code"] == "active_plan_exists"


# ---------- 应用 ----------

def test_apply_rejected_in_read_only(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    auth.post(f"/api/plans/{body['id']}/submit")
    r = auth.post(f"/api/plans/{body['id']}/apply")
    assert r.status_code == 403
    assert r.json()["code"] == "read_only"


def test_full_apply_native_ids_end_to_end(auth, db, dirs, settings):
    settings.management_mode = "native_ids"
    settings.read_only = False
    make_mod_present(db, settings, WID_A)
    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A}])
    auth.post(f"/api/plans/{body['id']}/submit")
    r = auth.post(f"/api/plans/{body['id']}/apply")
    assert r.status_code == 200, r.text
    task_id = r.json()["task"]["id"]
    assert wait_task(auth, task_id) == "succeeded"

    plan = _get_plan(db, body["id"])
    assert plan.status == "applied"
    assert parse_ids_file(settings.ids_file) == [WID_A]
    mod = _get_mod(db, WID_A)
    assert mod.desired_state == "enabled"
    assert mod.apply_state == "synced"
    assert mod.requires_restart is True          # 只标记,绝不自动重启


def test_apply_item_failure_isolates_items(auth, db, dirs, settings, monkeypatch):
    """单项失败不阻断后续项;计划整体 FAILED,成功项保持 synced。"""
    settings.management_mode = "native_ids"
    settings.read_only = False
    make_mod_present(db, settings, WID_A)
    make_mod_present(db, settings, WID_B)

    real_write = loaders_mod.write_ids_file

    def flaky_write(path, ids):
        if WID_B in ids:
            raise IdsFileError("模拟写入失败")
        real_write(path, ids)

    monkeypatch.setattr(loaders_mod, "write_ids_file", flaky_write)

    body = _new_plan(auth, [{"action": "enable", "workshop_id": WID_A},
                            {"action": "enable", "workshop_id": WID_B}])
    auth.post(f"/api/plans/{body['id']}/submit")
    r = auth.post(f"/api/plans/{body['id']}/apply")
    assert r.status_code == 200
    assert wait_task(auth, r.json()["task"]["id"]) == "failed"

    plan = _get_plan(db, body["id"])
    assert plan.status == "failed"
    assert "1 项失败" in plan.error
    items = {p.workshop_id: p for p in db.query(PlanItem).filter(
        PlanItem.plan_id == body["id"]).all()}
    assert items[WID_A].status == "done"
    assert items[WID_B].status == "failed"
    assert parse_ids_file(settings.ids_file) == [WID_A]
    mod_a, mod_b = _get_mod(db, WID_A), _get_mod(db, WID_B)
    assert mod_a.apply_state == "synced"
    assert mod_b.apply_state == "failed"


def test_delete_apply_moves_cache_to_trash(auth, db, dirs, settings):
    settings.management_mode = "native_ids"
    settings.read_only = False
    make_mod_present(db, settings, WID_A)
    body = _new_plan(auth, [{"action": "delete", "workshop_id": WID_A}])
    auth.post(f"/api/plans/{body['id']}/submit")
    r = auth.post(f"/api/plans/{body['id']}/apply")
    assert r.status_code == 200
    assert wait_task(auth, r.json()["task"]["id"]) == "succeeded"

    mod = _get_mod(db, WID_A)
    assert mod.inventory_state == "trashed"
    assert mod.cache_path == ""
    # 缓存文件确实离开原位置,且出现在回收站列表中
    from pathlib import Path
    from app.services import trash
    entries = trash.list_entries(db)
    assert len(entries) == 1
    assert entries[0].workshop_id == WID_A
    assert not Path(entries[0].original_path).exists()
    # 加载入口(native_ids 清单)保持不含该 ID
    assert parse_ids_file(settings.ids_file) == []
