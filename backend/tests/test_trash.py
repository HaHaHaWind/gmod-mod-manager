"""回收站:移入/恢复/永久删除/到期自动清理/API 端点。"""
from datetime import timedelta
from pathlib import Path

import pytest

from app.models import TrashEntry
from app.services import trash
from tests.conftest import WID_A, WID_B, make_cache_mod, make_mod_present


def _move(db, settings, wid, actor="tester"):
    return trash.move_to_trash(db, settings, wid, actor=actor)


def test_move_and_restore_roundtrip(db, dirs, settings):
    mod = make_mod_present(db, settings, WID_A)
    original = Path(mod.cache_path)
    assert original.exists()

    entry = _move(db, settings, WID_A)
    db.commit()
    assert entry.status == "in_trash"
    assert not original.exists()                       # 原位置已空
    assert Path(entry.trash_path).exists()
    db.expire_all()
    mod = db.get(mod.__class__, WID_A)
    assert mod.inventory_state == "trashed"
    assert mod.cache_path == ""

    info = trash.restore(db, settings, entry.id, actor="tester")
    db.commit()
    assert Path(info["path"]) == original              # 回到原位置
    assert original.exists()
    db.expire_all()
    mod = db.get(mod.__class__, WID_A)
    assert mod.inventory_state == "present"
    # 恢复 ≠ 重新启用:期望状态回到未纳管,需显式操作
    assert mod.desired_state == "unmanaged"
    assert mod.apply_state == "unmanaged"
    assert mod.requires_restart is True


def test_restore_blocked_when_target_occupied(db, dirs, settings):
    mod = make_mod_present(db, settings, WID_A)
    entry = _move(db, settings, WID_A)
    db.commit()
    make_cache_mod(settings, WID_A)                    # 磁盘原位置重新出现同名文件
    with pytest.raises(Exception) as ei:
        trash.restore(db, settings, entry.id, actor="tester")
    assert getattr(ei.value, "code", "") == "restore_target_exists"
    assert getattr(ei.value, "status", 0) == 409


def test_purge_removes_files_and_mod_row(db, dirs, settings):
    mod = make_mod_present(db, settings, WID_A)
    entry = _move(db, settings, WID_A)
    db.commit()
    out = trash.purge(db, settings, entry.id, actor="tester")
    db.commit()
    assert not Path(entry.trash_path).exists()         # 磁盘真删
    db.expire_all()
    assert db.get(mod.__class__, WID_A) is None        # Mod 占位行删除
    e = db.get(TrashEntry, entry.id)
    assert e.status == "purged"


def test_auto_purge_expired_by_retention(db, dirs, settings):
    settings.trash_retention_days = 7
    mod = make_mod_present(db, settings, WID_A)
    entry = _move(db, settings, WID_A)
    db.commit()
    # 未到期:不清理
    assert trash.auto_purge_expired(db, settings) == 0
    # 人为把删除时间拨到 8 天前 → 到期清理
    db.expire_all()
    e = db.get(TrashEntry, entry.id)
    from app.models import utcnow
    e.deleted_at = utcnow() - timedelta(days=8)
    db.commit()
    n = trash.auto_purge_expired(db, settings)
    db.commit()
    assert n == 1
    db.expire_all()
    assert db.get(TrashEntry, entry.id).status == "purged"


def test_trash_api_list_restore_purge(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    make_mod_present(db, settings, WID_B)
    e1 = _move(db, settings, WID_A)
    e2 = _move(db, settings, WID_B)
    db.commit()

    r = auth.get("/api/trash")
    assert r.status_code == 200
    items = {x["id"]: x for x in r.json()["items"]}
    assert items[e1.id]["workshop_id"] == WID_A

    r = auth.post(f"/api/trash/{e1.id}/restore")
    assert r.status_code == 200, r.text

    r = auth.post(f"/api/trash/{e2.id}/purge")
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(TrashEntry, e2.id).status == "purged"


def test_purge_non_in_trash_entry_conflicts(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    e1 = _move(db, settings, WID_A)
    db.commit()
    trash.restore(db, settings, e1.id, actor="tester")
    db.commit()
    r = auth.post(f"/api/trash/{e1.id}/purge")
    assert r.status_code == 409
    assert r.json()["code"] == "not_in_trash"
