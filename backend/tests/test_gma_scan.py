"""GMA 构造/解析、目录扫描发现、清单文件解析与状态调和。"""
import lzma

import pytest

from app.services.gma import (GmaError, is_gma_package, read_gma_metadata,
                              verify_gma_crc)
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


def test_gma_accepts_missing_trailer_crc(tmp_path):
    """尾部整包 CRC 缺失但数据区完整(各条目 CRC 有效)→ 仍应解析成功。"""
    p = build_gma(tmp_path / "nocrc.gma", title="无尾 CRC",
                  entries={"lua/a.lua": b"x" * 100, "maps/m.bsp": b"y" * 50})
    p.write_bytes(p.read_bytes()[:-4])  # 去掉尾部 4 字节整包 CRC
    meta = read_gma_metadata(p)
    assert meta.title == "无尾 CRC"
    assert meta.total_size == 150
    assert meta.has_trailer_crc is False
    assert verify_gma_crc(p) is False


def test_gma_still_rejects_missing_payload(tmp_path):
    """数据区本身缺失(截断到文件表之后)仍必须判为损坏。"""
    p = build_gma(tmp_path / "short.gma", entries={"lua/a.lua": b"z" * 500})
    p.write_bytes(p.read_bytes()[:-100])  # 切掉部分条目数据
    with pytest.raises(GmaError):
        read_gma_metadata(p)


def test_gma_reads_lzma_compressed(tmp_path):
    """legacy 缓存中的 *_legacy.bin 是 LZMA-alone 压缩的 GMA,应透明解析。"""
    plain = build_gma(tmp_path / "src.gma", title="压缩测试",
                      entries={"lua/a.lua": b"x" * 100, "maps/m.bsp": b"y" * 200})
    lz = tmp_path / "123_legacy.bin"
    lz.write_bytes(lzma.compress(plain.read_bytes(), format=lzma.FORMAT_ALONE))
    assert is_gma_package(lz) is True
    meta = read_gma_metadata(lz)
    assert meta.title == "压缩测试"
    assert [e.filename for e in meta.entries] == ["lua/a.lua", "maps/m.bsp"]
    assert meta.total_size == 300
    assert verify_gma_crc(lz) is True


def test_gma_rejects_broken_lzma(tmp_path):
    """形似 LZMA 头但流无效的 .bin,应报 GmaError 且不被当作 GMA。"""
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x5d\x00\x00\x80not-a-gma")
    assert is_gma_package(p) is False
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


def test_scan_accepts_bin_addon_by_magic(db, dirs):
    """legacy 条目以 .bin 后缀存放,内容仍是 GMA(文件头 GMAD)→ 应识别为正常。"""
    from app.models import Mod
    bin_path = dirs.cache_root / WID_A / "garrysmod" / "addons" / f"{WID_A}.bin"
    build_gma(bin_path, title="Legacy Bin")
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.invalid == []
    mod = db.get(Mod, WID_A)
    assert mod.inventory_state == "present"
    assert mod.title_local == "Legacy Bin"
    assert mod.cache_path.endswith(f"{WID_A}.bin")


def test_scan_accepts_lzma_bin_addon(db, dirs):
    """legacy 条目以 LZMA 压缩的 .bin 存放 → 应识别为正常并读出元数据。"""
    from app.models import Mod
    plain = build_gma(dirs.cache_root / WID_A / "src.gma", title="Legacy LZMA")
    bin_path = dirs.cache_root / WID_A / f"{WID_A}_legacy.bin"
    bin_path.write_bytes(lzma.compress(plain.read_bytes(), format=lzma.FORMAT_ALONE))
    plain.unlink()  # 只留 .bin,贴近真实 legacy 布局
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.invalid == []
    mod = db.get(Mod, WID_A)
    assert mod.inventory_state == "present"
    assert mod.title_local == "Legacy LZMA"
    assert mod.cache_path.endswith("_legacy.bin")


def test_scan_accepts_missing_trailer_crc(db, dirs):
    """整包尾部 CRC 缺失但数据区完整 → present,并在详情给出软提示。"""
    from app.models import Mod
    gma_path = dirs.cache_root / WID_A / "garrysmod" / "addons" / f"{WID_A}.gma"
    p = build_gma(gma_path, title="No CRC", entries={"lua/a.lua": b"x" * 300})
    p.write_bytes(p.read_bytes()[:-4])  # 去掉尾部整包 CRC
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.invalid == []
    mod = db.get(Mod, WID_A)
    assert mod.inventory_state == "present"
    assert "CRC" in mod.inventory_detail.get("warning", "")


def test_scan_flags_non_gma_bin(db, dirs):
    """既非 GMAD 也非 LZMA 的 .bin 无法当 addon 解析,应给出准确原因。"""
    from app.models import Mod
    addons = dirs.cache_root / WID_B / "garrysmod" / "addons"
    addons.mkdir(parents=True)
    (addons / f"{WID_B}.bin").write_bytes(b"NOT-A-GMA-OR-LZMA" + b"\x00" * 32)
    report = run_full_scan(db, dirs, deep=True)
    db.commit()
    assert report.invalid == [WID_B]
    mod = db.get(Mod, WID_B)
    assert mod.inventory_state == "invalid"
    assert ".bin" in mod.inventory_detail["reason"]
