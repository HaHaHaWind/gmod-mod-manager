"""srcds 进程探测与"待重启"标记调和。

/proc 相关用例通过伪造 _PROC 目录实现,保证在非 Linux 平台也能跑。
"""
from __future__ import annotations

import time
from pathlib import Path

from app.models import Mod
from app.services import runtime
from tests.conftest import WID_A, WID_B


def _fake_proc(root: Path, entries: dict[str, tuple[str, int]]) -> Path:
    """构造伪 /proc:entries = {pid: (comm, start_ticks)}。"""
    proc = root / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "uptime").write_text("100.0 200.0\n", encoding="utf-8")
    for pid, (comm, ticks) in entries.items():
        d = proc / pid
        d.mkdir(parents=True, exist_ok=True)
        (d / "comm").write_text(comm + "\n", encoding="utf-8")
        fields = ["S"] + ["0"] * 18 + [str(ticks)]  # fields[19] = starttime
        (d / "stat").write_text(f"{pid} ({comm}) " + " ".join(fields) + "\n", encoding="utf-8")
    return proc


# ---------- 进程探测 ----------

def test_find_srcds_picks_latest_matching(tmp_path, dirs, monkeypatch):
    proc = _fake_proc(tmp_path, {
        "100": ("srcds_run_x64", 500),
        "200": ("srcds", 800),
        "300": ("nginx", 900),
    })
    monkeypatch.setattr(runtime, "_PROC", proc)
    got = runtime.find_srcds(dirs)
    assert got is not None and got.pid == 200  # 前缀命中且启动更晚的引擎进程
    assert abs(got.start_epoch - (time.time() - 100.0 + 800 / runtime._CLK_TCK)) < 5


def test_find_srcds_none_when_no_match(tmp_path, dirs, monkeypatch):
    proc = _fake_proc(tmp_path, {"100": ("nginx", 500), "200": ("bash", 600)})
    monkeypatch.setattr(runtime, "_PROC", proc)
    assert runtime.find_srcds(dirs) is None


def test_find_srcds_prefix_matching_covers_distro_names(tmp_path, dirs, monkeypatch):
    proc = _fake_proc(tmp_path, {"100": ("srcds_linux", 500)})
    monkeypatch.setattr(runtime, "_PROC", proc)
    got = runtime.find_srcds(dirs)
    assert got is not None and got.pid == 100


# ---------- 标记调和 ----------

def _flag(db, wid: str) -> Mod:
    m = Mod(workshop_id=wid, folder_name=wid, requires_restart=True)
    db.add(m)
    db.commit()
    return m


def test_reconcile_clears_when_no_process(db, dirs, tmp_path, monkeypatch):
    _flag(db, WID_A)
    monkeypatch.setattr(runtime, "_PROC", tmp_path)  # 让 is_dir() 为真
    monkeypatch.setattr(runtime, "find_srcds", lambda s: None)
    out = runtime.reconcile_restart_flags(db, dirs)
    db.commit()
    assert out["cleared"] == 1 and out["reason"] == "no_process"
    assert db.get(Mod, WID_A).requires_restart is False


def test_reconcile_clears_when_restarted_after_change(db, dirs, tmp_path, monkeypatch):
    _flag(db, WID_A)
    monkeypatch.setattr(runtime, "_PROC", tmp_path)
    monkeypatch.setattr(runtime, "find_srcds",
                        lambda s: runtime.SrcdsProc(pid=1, start_epoch=200.0))
    monkeypatch.setattr(runtime, "latest_config_write", lambda s: 100.0)
    out = runtime.reconcile_restart_flags(db, dirs)
    db.commit()
    assert out["cleared"] == 1 and out["reason"] == "restarted"
    assert db.get(Mod, WID_A).requires_restart is False


def test_reconcile_keeps_when_instance_older_than_change(db, dirs, tmp_path, monkeypatch):
    _flag(db, WID_A)
    monkeypatch.setattr(runtime, "_PROC", tmp_path)
    monkeypatch.setattr(runtime, "find_srcds",
                        lambda s: runtime.SrcdsProc(pid=1, start_epoch=100.0))
    monkeypatch.setattr(runtime, "latest_config_write", lambda s: 200.0)
    out = runtime.reconcile_restart_flags(db, dirs)
    db.commit()
    assert out["cleared"] == 0 and out["reason"] == "still_pending"
    assert db.get(Mod, WID_A).requires_restart is True


def test_reconcile_keeps_when_no_config_timestamp(db, dirs, tmp_path, monkeypatch):
    # 没有任何配置写入时刻(ids/addons 都不存在)时保守保留
    _flag(db, WID_A)
    monkeypatch.setattr(runtime, "_PROC", tmp_path)
    monkeypatch.setattr(runtime, "find_srcds",
                        lambda s: runtime.SrcdsProc(pid=1, start_epoch=100.0))
    monkeypatch.setattr(runtime, "latest_config_write", lambda s: None)
    out = runtime.reconcile_restart_flags(db, dirs)
    db.commit()
    assert out["cleared"] == 0 and db.get(Mod, WID_A).requires_restart is True


def test_reconcile_noop_when_nothing_flagged(db, dirs, tmp_path, monkeypatch):
    db.add(Mod(workshop_id=WID_B, folder_name=WID_B, requires_restart=False))
    db.commit()
    monkeypatch.setattr(runtime, "_PROC", tmp_path)
    out = runtime.reconcile_restart_flags(db, dirs)
    assert out == {"flagged": 0, "cleared": 0, "reason": "none"}


def test_reconcile_unsupported_without_proc(db, dirs, monkeypatch):
    _flag(db, WID_A)
    monkeypatch.setattr(runtime, "_PROC", dirs.data_path / "no-such-proc")
    out = runtime.reconcile_restart_flags(db, dirs)
    assert out["cleared"] == 0 and out["reason"] == "unsupported"
    assert db.get(Mod, WID_A).requires_restart is True