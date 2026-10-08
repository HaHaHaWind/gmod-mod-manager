"""srcds 运行时挂载探针:内容解析、候选发现、runtime_state 三态刷新。"""
from app.models import Mod
from app.services.probe import (find_probe_file, parse_mounted_ids,
                                read_mounted_ids, update_runtime_states)
from app.services.scan import run_full_scan
from tests.conftest import WID_A, WID_B, make_cache_mod


# ---------- 内容解析 ----------

def test_parse_keyvalues_wsid():
    text = '"srcds_addons"\n{\n"1"\n{\n"wsid" "123277559"\n}\n"2"\n{\n"wsid" "456123789"\n}\n}\n'
    assert parse_mounted_ids(text) == {"123277559", "456123789"}


def test_parse_bare_number_list():
    # 旧版缓存可能是每行/空白分隔的纯 ID 列表
    assert parse_mounted_ids("123277559\n250123456\n") == {"123277559", "250123456"}


def test_parse_wsid_mode_wins_over_bare():
    # 出现 wsid 键时只信 wsid,忽略其余数字(避免把序号/时间戳误判为 ID)
    text = '"1"\n{\n"wsid" "123277559"\n}\n"2" "999"\n'
    assert parse_mounted_ids(text) == {"123277559"}


def test_parse_bare_mode_filters_short_and_embedded_numbers():
    # 无 wsid 时:短数字(<3 位)与夹在词中的数字不算 ID
    assert parse_mounted_ids("addons v2 mounted\n12 123277559\nid250123456") == {"123277559"}


def test_parse_empty_and_garbage():
    assert parse_mounted_ids("") == set()
    assert parse_mounted_ids("no ids here") == set()


# ---------- 候选发现 ----------

def test_find_probe_prefers_cfg_then_explicit(tmp_path, dirs):
    cfg_probe = dirs.ids_file.parent / "srcds_addons.txt"
    cfg_probe.write_text("123\n", encoding="utf-8")
    assert find_probe_file(dirs) == cfg_probe
    explicit = tmp_path / "custom_probe.txt"
    explicit.write_text("456\n", encoding="utf-8")
    dirs.runtime_probe_file = str(explicit)
    assert find_probe_file(dirs) == explicit


def test_find_probe_missing(dirs):
    assert find_probe_file(dirs) is None


def test_find_probe_disabled(dirs):
    (dirs.ids_file.parent / "srcds_addons.txt").write_text("123\n", encoding="utf-8")
    dirs.runtime_probe_enabled = False
    assert find_probe_file(dirs) is None


def test_find_probe_new_cache_layout(tmp_path, dirs):
    # 新版布局:<srcds 根>/cache/srcds_addon_list_cache.txt
    root = tmp_path / "GarrysModDS"
    (root / "cache").mkdir(parents=True)
    newf = root / "cache" / "srcds_addon_list_cache.txt"
    newf.write_text("999\n", encoding="utf-8")
    dirs.gmod_addons_root = str(root / "garrysmod" / "addons")
    assert find_probe_file(dirs) == newf


# ---------- 读取与状态刷新 ----------

def test_read_mounted_ids_status_and_ids(dirs):
    status, ids = read_mounted_ids(dirs)
    assert status == "not_found" and ids == set()
    p = dirs.ids_file.parent / "srcds_addons.txt"
    p.write_text('"wsid" "123277559"', encoding="utf-8")
    status, ids = read_mounted_ids(dirs)
    assert status.startswith("ok:") and ids == {"123277559"}


def test_update_runtime_states_three_ways(db, dirs):
    from tests.conftest import WID_C
    for wid in (WID_A, WID_B, WID_C):
        db.add(Mod(workshop_id=wid, folder_name=wid))
    db.commit()
    p = dirs.ids_file.parent / "srcds_addons.txt"
    p.write_text(f"{WID_A}\n", encoding="utf-8")
    status = update_runtime_states(db, dirs)
    db.commit()
    assert status.startswith("ok:")
    assert db.get(Mod, WID_A).runtime_state == "loaded"
    assert db.get(Mod, WID_B).runtime_state == "not_loaded"
    assert db.get(Mod, WID_C).runtime_state == "not_loaded"

    # 探针消失后重刷:回退到 unknown
    p.unlink()
    update_runtime_states(db, dirs)
    db.commit()
    assert db.get(Mod, WID_A).runtime_state == "unknown"


# ---------- 与全量扫描集成 ----------

def test_scan_with_probe_marks_runtime(db, dirs):
    make_cache_mod(dirs, WID_A)
    make_cache_mod(dirs, WID_B)
    probe = dirs.ids_file.parent / "srcds_addons.txt"
    probe.write_text(f"{WID_A}\n", encoding="utf-8")  # 只有 A 实际挂载
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.runtime_probe.startswith("ok:")
    assert db.get(Mod, WID_A).runtime_state == "loaded"
    assert db.get(Mod, WID_B).runtime_state == "not_loaded"
    assert report.summary()["runtime_probe"].startswith("ok:")


def test_scan_without_probe_keeps_unknown(db, dirs):
    make_cache_mod(dirs, WID_A)
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.runtime_probe == "not_found"
    assert db.get(Mod, WID_A).runtime_state == "unknown"


def test_scan_probe_disabled_keeps_unknown(db, dirs):
    make_cache_mod(dirs, WID_A)
    (dirs.ids_file.parent / "srcds_addons.txt").write_text(WID_A, encoding="utf-8")
    dirs.runtime_probe_enabled = False
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.runtime_probe == "disabled"
    assert db.get(Mod, WID_A).runtime_state == "unknown"
