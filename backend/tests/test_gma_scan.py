"""GMA 构造/解析、目录扫描发现、清单文件解析与状态调和。"""
import pytest

from app.services.gma import GmaError, read_gma_metadata, verify_gma_crc
from app.services.idsfile import (IdsFileError, build_ids_text,
                                  parse_ids_file, parse_ids_text, write_ids_file)
from app.services.scan import run_full_scan
from tests.conftest import WID_A, WID_B, WID_C, build_gma, make_cache_mod


# ---------- GMA ----------

def test_gma_roundtrip_and_crc(tmp_path, dirs):
    p = build_gma(tmp_path / "x" / "a.gma", title="环形测试",
                  entries={"maps/gm_test.bsp": b"X" * 5000, "lua/x.lua": b"y"})
    meta = read_gma_metadata(p)
    assert meta.title == "环形测试"
    assert meta.author == "author"
    assert [e.filename for e in meta.entries] == ["maps/gm_test.bsp", "lua/x.lua"]
    assert meta.total_size == 5001
    assert verify_gma_crc(p) is True


def test_gma_rejects_garbage(tmp_path):
    p = tmp_path / "bad.gma"
    p.write_bytes(b"NOTGMA" + b"\x00" * 64)
    with pytest.raises(GmaError):
        read_gma_metadata(p)


def test_gma_rejects_truncated_table(tmp_path):
    p = build_gma(tmp_path / "t.gma")
    raw = p.read_bytes()
    p.write_bytes(raw[:-10])  # 破坏尾部
    with pytest.raises(GmaError):
        read_gma_metadata(p)


# ---------- 清单文件 ----------

def test_ids_file_roundtrip(tmp_path, dirs):
    ids = [WID_C, WID_A, WID_B]
    f = dirs.ids_file
    write_ids_file(f, ids)
    parsed = parse_ids_file(f)
    assert parsed == sorted(ids, key=int)          # 生成按数值升序
    assert parse_ids_text(build_ids_text(ids)) == parsed


def test_ids_file_rejects_invalid(tmp_path):
    bad = '"my_workshop_addons"\n{\n"1"\n{\n"wsid" "abc"\n}\n}\n'
    with pytest.raises(IdsFileError):
        parse_ids_text(bad)


def test_ids_file_tolerant_minimal_form():
    assert parse_ids_text('"my_workshop_addons"\n{\n"1" "123456"\n}\n') == ["123456"]


# ---------- 扫描 ----------

def test_scan_discovers_and_reconciles(db, dirs):
    make_cache_mod(dirs, WID_A)
    make_cache_mod(dirs, WID_B, title="Second")
    (dirs.cache_root / "not-an-id").mkdir()       # 非法目录名 → 异常清单
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert set(report.created) == {WID_A, WID_B}
    assert any("not-an-id" in a for a in report.anomalies)

    from app.models import Mod
    mod = db.get(Mod, WID_A)
    assert mod.inventory_state == "present"
    assert mod.title_local == f"Addon {WID_A}"
    assert mod.load_sources == ["unmanaged_cache"]
    assert mod.runtime_state == "unknown"
    assert mod.file_count == 1
    assert db.query(type(mod)).count() == 2


def test_scan_marks_missing_after_removal(db, dirs):
    make_cache_mod(dirs, WID_A)
    run_full_scan(db, dirs, deep=True)
    db.commit()

    import shutil
    shutil.rmtree(dirs.cache_root / WID_A)
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.missing == [WID_A]

    from app.models import Mod
    mod = db.get(Mod, WID_A)
    assert mod.inventory_state == "missing"
    assert mod.missing_since is not None


def test_scan_detects_external_addons_source(db, dirs):
    make_cache_mod(dirs, WID_A)
    build_gma(dirs.addons_root / f"{WID_A}_something_else.gma", title="外部遗留")
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.created == [WID_A]

    from app.models import Mod
    mod = db.get(Mod, WID_A)
    assert "external_addons" in mod.load_sources
    kinds = {c["kind"] for c in mod.inventory_detail.get("conflicts", [])}
    assert "external_addons" in kinds


def test_scan_preserves_user_decisions(db, dirs):
    """重扫绝不覆盖 desired/apply(用户决定只由计划修改)。"""
    from app.models import Mod
    mod = run_full_scan(db, dirs, deep=True) and db.get(Mod, "0")  # 占位
    make_cache_mod(dirs, WID_A)
    run_full_scan(db, dirs, deep=True)
    db.commit()
    m = db.get(Mod, WID_A)
    m.desired_state = "enabled"
    m.apply_state = "synced"
    db.commit()

    run_full_scan(db, dirs, deep=True)
    db.commit()
    m2 = db.get(Mod, WID_A)
    assert m2.desired_state == "enabled"
    assert m2.apply_state == "synced"
