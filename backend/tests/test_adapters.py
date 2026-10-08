"""三种管理适配器:模式分发 / observe 只读 / check 预检 / native_ids 清单 / local_managed 部署。"""
import pytest

from app.adapters.loaders import (AdapterContext, LocalManagedAdapter,
                                  NativeIdsAdapter, ObserveAdapter,
                                  get_adapter)
from app.errors import ApiError
from app.services import gma
from app.services.idsfile import parse_ids_file
from tests.conftest import WID_A, WID_B, make_cache_mod, make_mod_present


def _ctx(db, settings):
    return AdapterContext(db, settings, actor="tester")


# ---------- 模式分发 ----------

def test_get_adapter_dispatches_by_mode(db, settings):
    settings.management_mode = "observe"
    assert isinstance(get_adapter(_ctx(db, settings)), ObserveAdapter)
    settings.management_mode = "native_ids"
    assert isinstance(get_adapter(_ctx(db, settings)), NativeIdsAdapter)
    settings.management_mode = "local_managed"
    assert isinstance(get_adapter(_ctx(db, settings)), LocalManagedAdapter)
    settings.management_mode = "bogus"
    with pytest.raises(ApiError) as ei:
        get_adapter(_ctx(db, settings))
    assert ei.value.code == "bad_mode"


# ---------- observe:只写预览,拒绝一切变更 ----------

def test_observe_apply_always_rejected(db, dirs):
    ad = ObserveAdapter(_ctx(db, dirs))
    with pytest.raises(ApiError) as ei:
        ad.apply("enable", WID_A, {})
    assert ei.value.status == 403
    assert ei.value.code == "observe_readonly"


# ---------- check 预检 ----------

def test_check_requires_registered_mod(db, dirs, settings):
    ad = get_adapter(_ctx(db, settings))
    with pytest.raises(ApiError) as ei:
        ad.check("enable", WID_A)
    assert ei.value.status == 404


def test_check_blocks_enable_when_not_present(db, dirs, settings):
    from app.models import Mod
    make_mod_present(db, settings, WID_A)
    db.expire_all()
    mod = db.get(Mod, WID_A)
    mod.inventory_state = "trashed"
    db.commit()
    ad = get_adapter(_ctx(db, settings))
    with pytest.raises(ApiError) as ei:
        ad.check("enable", WID_A)
    assert ei.value.code == "not_present"
    # delete 不要求 present,不受此限制
    ad.check("delete", WID_A)


def test_check_blocks_delete_protected(db, dirs, settings):
    from app.models import Mod
    make_mod_present(db, settings, WID_A)
    mod = db.get(Mod, WID_A)
    mod.protected = True
    mod.protected_reason = "核心玩法依赖"
    db.commit()
    ad = get_adapter(_ctx(db, settings))
    with pytest.raises(ApiError) as ei:
        ad.check("delete", WID_A)
    assert ei.value.code == "protected"
    assert "核心玩法依赖" in ei.value.message
    # enable 不受保护限制
    assert ad.check("enable", WID_A) == []


def test_check_warns_on_external_source(db, dirs, settings):
    from app.models import Mod
    make_mod_present(db, settings, WID_A)
    mod = db.get(Mod, WID_A)
    mod.load_sources = ["external_addons"]
    db.commit()
    ad = get_adapter(_ctx(db, settings))
    warns = ad.check("enable", WID_A)
    assert any(w["kind"] == "external_source" for w in warns)


# ---------- native_ids ----------

def test_native_ids_check_appends_version_warning(db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    ad = get_adapter(_ctx(db, settings))  # mode=observe 时 check 也走 Base;显式构造
    ad = NativeIdsAdapter(_ctx(db, settings))
    warns = ad.check("enable", WID_A)
    assert any(w["kind"] == "version" for w in warns)


def test_native_ids_enable_disable_roundtrip(db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    make_mod_present(db, settings, WID_B)
    ad = NativeIdsAdapter(_ctx(db, settings))
    assert parse_ids_file(settings.ids_file) == []

    r = ad.apply("enable", WID_A, {})
    assert r["changed"] is True
    assert parse_ids_file(settings.ids_file) == [WID_A]

    ad.apply("enable", WID_B, {})
    assert parse_ids_file(settings.ids_file) == [WID_A, WID_B]  # 按数值升序

    r = ad.apply("disable", WID_A, {})
    assert r["changed"] is True
    assert parse_ids_file(settings.ids_file) == [WID_B]

    # delete 同样从清单移除
    ad.apply("delete", WID_B, {})
    assert parse_ids_file(settings.ids_file) == []


def test_native_ids_no_change_skips_write(db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    ad = NativeIdsAdapter(_ctx(db, settings))
    ad.apply("enable", WID_A, {})
    before = settings.ids_file.read_bytes()
    r = ad.apply("enable", WID_A, {})
    assert r["changed"] is False
    assert settings.ids_file.read_bytes() == before


def test_native_ids_requires_ids_file_configured(db, dirs, settings, monkeypatch):
    make_mod_present(db, settings, WID_A)
    monkeypatch.setattr(settings, "workshop_ids_file", "")  # ids_file → None
    ad = NativeIdsAdapter(_ctx(db, settings))
    with pytest.raises(ApiError) as ei:
        ad.apply("enable", WID_A, {})
    assert ei.value.code == "ids_file_unconfigured"


def test_native_ids_invalid_file_blocks_overwrite(db, dirs, settings):
    """清单损坏时拒绝应用(409),绝不覆盖原文件——避免可修复错误变成数据丢失。"""
    make_mod_present(db, settings, WID_A)
    settings.ids_file.write_bytes(b'"my_workshop_addons" { broken')  # 块未闭合
    ad = NativeIdsAdapter(_ctx(db, settings))
    with pytest.raises(ApiError) as ei:
        ad.apply("enable", WID_A, {})
    assert ei.value.code == "ids_file_invalid"
    assert ei.value.status == 409
    assert settings.ids_file.read_bytes() == b'"my_workshop_addons" { broken'


# ---------- local_managed ----------

def test_local_managed_gma_copy_versions(db, dirs, settings):
    settings.management_mode = "local_managed"
    settings.local_managed_strategy = "gma_copy"
    make_mod_present(db, settings, WID_A)
    from app.models import Mod
    ad = LocalManagedAdapter(_ctx(db, settings))

    r = ad.apply("enable", WID_A, {})
    assert r["changed"] is True and r["strategy"] == "gma_copy" and r["version"] == 1
    dst = settings.addons_root / f"gmm_{WID_A}_v1.gma"
    assert dst.is_file()
    mod = db.get(Mod, WID_A)
    assert mod.deploy_version == 1 and mod.deploy_path == str(dst)
    assert mod.source_changed is False

    r = ad.apply("enable", WID_A, {})          # 再次部署 → v2 替换 v1
    assert r["version"] == 2
    assert not dst.exists()                    # 旧版本已被清理
    assert (settings.addons_root / f"gmm_{WID_A}_v2.gma").is_file()

    r = ad.apply("disable", WID_A, {})
    assert r["changed"] is True and r["removed_copies"] == 1
    assert list(settings.addons_root.iterdir()) == []


def test_local_managed_folder_extract(db, dirs, settings):
    settings.management_mode = "local_managed"
    settings.local_managed_strategy = "folder_extract"
    make_mod_present(db, settings, WID_A)
    from app.models import Mod
    ad = LocalManagedAdapter(_ctx(db, settings))

    r = ad.apply("enable", WID_A, {})
    assert r["strategy"] == "folder_extract" and r["files"] >= 1
    dst = settings.addons_root / f"gmm_{WID_A}"
    assert dst.is_dir()
    assert (dst / "lua" / "autorun" / "test.lua").is_file()  # GMA 内条目被解包
    assert not any(p.name.startswith(".gmm-extract-") for p in settings.addons_root.iterdir())

    ad.apply("disable", WID_A, {})
    assert not dst.exists()


def test_local_managed_rejects_invalid_source_gma(db, dirs, settings):
    """源 GMA 损坏 → 422 gma_invalid,addons 下不留半成品。"""
    settings.management_mode = "local_managed"
    src = make_cache_mod(settings, WID_A)
    src.write_bytes(b"GMAD\x02garbage")         # 截断损坏
    from app.models import Mod
    mod = Mod(workshop_id=WID_A, folder_name=WID_A, inventory_state="present",
              cache_path=str(src), size_bytes=src.stat().st_size, file_count=1)
    db.add(mod)
    db.commit()
    ad = LocalManagedAdapter(_ctx(db, settings))
    with pytest.raises(ApiError) as ei:
        ad.apply("enable", WID_A, {})
    assert ei.value.code == "gma_invalid"
    assert list(settings.addons_root.iterdir()) == []
