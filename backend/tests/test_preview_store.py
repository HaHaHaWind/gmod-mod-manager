"""本地预览图:下载落盘、批量同步、扫描/刷新任务联动、列表端点与回收站清理。

网络层全部使用替身:httpx.Client 换成查表路由,DNS 公网校验直接跳过
(SSRF 细节已在 test_preview.py 单独覆盖,这里只关心存取与编排行为)。
"""
from __future__ import annotations

import httpx
import pytest

from app.models import Mod
from app.services import preview as pv
from app.services import preview_store as ps
from app.services import steam, trash
from tests.conftest import WID_A, WID_B, WID_C, make_mod_present, wait_task

U1 = "https://steamuserimages-a.akamaihd.net/ugc/1/a.jpg"
U2 = "https://steamcdn-a.akamaihd.net/ugc/1/b.jpg"


# ---------- httpx 替身 ----------

class _Resp:
    """最小流式响应替身。"""

    def __init__(self, status=200, headers=None, chunks=(), redirect_to=""):
        self.status_code = status
        self.headers = dict(headers or {})
        if redirect_to:
            self.headers["location"] = redirect_to
        self._chunks = list(chunks)

    @property
    def is_redirect(self):
        return 300 <= self.status_code < 400 and bool(self.headers.get("location"))

    def iter_bytes(self, _n):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _StreamCtx:
    def __init__(self, target):
        self._target = target

    def __enter__(self):
        if isinstance(self._target, Exception):
            raise self._target
        return self._target

    def __exit__(self, *exc):
        return False


def _install_http(monkeypatch, routes):
    """把 httpx.Client 换成查表替身(未命中的 URL 一律 404);返回请求记录。"""
    calls = []

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url):
            calls.append(url)
            return _StreamCtx(routes.get(url, _Resp(status=404)))

    monkeypatch.setattr(ps.httpx, "Client", _FakeClient)
    return calls


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    """跳过 DNS 公网校验:本文件只测存取与编排。"""
    monkeypatch.setattr(pv, "assert_resolves_public", lambda host: None)


def _write_preview(settings, wid, data=b"x", suffix=".jpg"):
    d = ps.previews_dir(settings)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{wid}{suffix}"
    p.write_bytes(data)
    return p


# ---------- download_preview ----------

def test_download_saved_jpeg_cleans_part(dirs, settings, monkeypatch):
    calls = _install_http(monkeypatch, {
        U1: _Resp(headers={"content-type": "image/jpeg; charset=binary"},
                  chunks=[b"AA", b"BB"])})
    assert ps.download_preview(settings, WID_A, U1) == "saved"
    f = ps.preview_path(settings, WID_A)
    assert f.read_bytes() == b"AABB"
    assert not f.with_name(f.name + ".part").exists()   # 原子落盘,无残留
    assert ps.has_preview(settings, WID_A)
    assert calls == [U1]


def test_download_saves_png_extension(dirs, settings, monkeypatch):
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "image/png"},
                                         chunks=[b"PNGDATA"])})
    assert ps.download_preview(settings, WID_A, U1) == "saved"
    assert (ps.previews_dir(settings) / f"{WID_A}.png").is_file()
    assert ps.has_preview(settings, WID_A)
    # find_preview 能找到非 .jpg 的落盘文件(列表端点依赖这一点)
    assert ps.find_preview(settings, WID_A) == ps.previews_dir(settings) / f"{WID_A}.png"


def test_download_invalid_url_rejected(dirs, settings, monkeypatch):
    calls = _install_http(monkeypatch, {})
    assert ps.download_preview(settings, WID_A, "https://evil.example.com/x.jpg") == "invalid"
    assert not ps.has_preview(settings, WID_A)
    assert calls == []                                  # 白名单拦截,未发起请求


def test_download_follows_whitelisted_redirect(dirs, settings, monkeypatch):
    routes = {U1: _Resp(status=302, redirect_to=U2),
              U2: _Resp(headers={"content-type": "image/jpeg"}, chunks=[b"R"])}
    calls = _install_http(monkeypatch, routes)
    assert ps.download_preview(settings, WID_A, U1) == "saved"
    assert calls == [U1, U2]                            # 逐跳校验后落地


def test_download_rejects_redirect_to_denied_host(dirs, settings, monkeypatch):
    bad = "http://127.0.0.1:8080/x.jpg"
    _install_http(monkeypatch, {U1: _Resp(status=302, redirect_to=bad)})
    assert ps.download_preview(settings, WID_A, U1) == "failed"
    assert not ps.has_preview(settings, WID_A)


def test_download_upstream_404(dirs, settings, monkeypatch):
    _install_http(monkeypatch, {})                      # 未命中一律 404
    assert ps.download_preview(settings, WID_B, U1) == "failed"
    assert not ps.has_preview(settings, WID_B)


def test_download_rejects_non_image(dirs, settings, monkeypatch):
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "text/html"},
                                         chunks=[b"<html>"])})
    assert ps.download_preview(settings, WID_B, U1) == "invalid"
    assert not ps.has_preview(settings, WID_B)


def test_download_oversize_rejected(dirs, settings, monkeypatch):
    settings.preview_max_bytes = 10
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "image/jpeg"},
                                         chunks=[b"x" * 8, b"y" * 8])})
    assert ps.download_preview(settings, WID_A, U1) == "invalid"
    assert not ps.has_preview(settings, WID_A)
    assert not (ps.previews_dir(settings) / f"{WID_A}.jpg.part").exists()


def test_download_network_error(dirs, settings, monkeypatch):
    _install_http(monkeypatch, {U1: httpx.ConnectError("连接失败")})
    assert ps.download_preview(settings, WID_A, U1) == "failed"
    assert not ps.has_preview(settings, WID_A)


# ---------- ensure_previews / delete ----------

def test_ensure_previews_stats_and_cache(db, dirs, settings, monkeypatch):
    for wid in (WID_A, WID_B, WID_C):
        make_mod_present(db, settings, wid)
    db.get(Mod, WID_A).preview_url = U1                 # 可下载 → saved
    db.get(Mod, WID_B).preview_url = U2                 # 上游 404 → failed
    # WID_C 不给地址 → no_url;"999999999" 未登记 → no_url
    db.commit()
    calls = _install_http(monkeypatch, {
        U1: _Resp(headers={"content-type": "image/jpeg"}, chunks=[b"x"])})

    stats = ps.ensure_previews(db, settings, [WID_A, WID_B, WID_C, "999999999"])
    assert stats == {"total": 4, "cached": 0, "saved": 1,
                     "failed": 1, "no_url": 2}
    assert calls == [U1, U2]                            # no_url 的不发起请求

    # 第二轮:已落盘的直接走缓存,不再请求网络
    stats2 = ps.ensure_previews(db, settings, [WID_A, WID_B, WID_C, "999999999"])
    assert stats2["cached"] == 1 and stats2["saved"] == 0


def test_delete_preview_roundtrip(dirs, settings):
    assert ps.has_preview(settings, WID_A) is False
    _write_preview(settings, WID_A, suffix=".webp")
    assert ps.has_preview(settings, WID_A) is True
    assert ps.delete_preview(settings, WID_A) is True
    assert ps.has_preview(settings, WID_A) is False
    assert ps.delete_preview(settings, WID_A) is False  # 幂等


# ---------- sync_after_scan ----------

def test_sync_after_scan_refreshes_then_downloads(db, dirs, settings, monkeypatch):
    make_mod_present(db, settings, WID_A)
    db.get(Mod, WID_A).preview_url = U1
    db.commit()
    monkeypatch.setattr(ps.steam, "refresh_metadata",
                        lambda s, st, ids: {"refreshed": len(ids)})
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "image/jpeg"},
                                         chunks=[b"S"])})
    out = ps.sync_after_scan(db, settings)
    assert out["meta"] == {"refreshed": 1}
    assert out["saved"] == 1


def test_sync_after_scan_survives_steam_error(db, dirs, settings, monkeypatch):
    make_mod_present(db, settings, WID_A)
    db.get(Mod, WID_A).preview_url = U1
    db.commit()

    def _boom(session, st, ids):
        raise steam.SteamError("Steam 接口不可用")

    monkeypatch.setattr(ps.steam, "refresh_metadata", _boom)
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "image/jpeg"},
                                         chunks=[b"S"])})
    out = ps.sync_after_scan(db, settings)
    assert "Steam 接口不可用" in out["meta"]["error"]    # 元数据失败只记录,不断链
    assert out["saved"] == 1


def test_sync_after_scan_empty_inventory(db, dirs, settings):
    out = ps.sync_after_scan(db, settings)
    assert out["meta"] is None
    assert out["total"] == 0


# ---------- 列表端点:三分支 ----------

def test_preview_endpoint_branches(auth, anon, db, dirs, settings):
    # 未登记 → 404;匿名 → 401/403
    assert auth.get(f"/api/mods/{WID_A}/preview").status_code == 404
    assert anon.get(f"/api/mods/{WID_A}/preview").status_code in (401, 403)

    make_mod_present(db, settings, WID_A)

    # 已登记但无本地文件、无远程地址 → 404
    assert auth.get(f"/api/mods/{WID_A}/preview").status_code == 404

    # 有远程地址但未落盘 → 302 到安全代理(前端 <img> 跟随即可显示)
    db.get(Mod, WID_A).preview_url = U1
    db.commit()
    r = auth.get(f"/api/mods/{WID_A}/preview", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/api/preview?url=")

    # 已落盘 → 直接回本地文件
    _write_preview(settings, WID_A, b"JPEGBYTES")
    r = auth.get(f"/api/mods/{WID_A}/preview")
    assert r.status_code == 200
    assert r.content == b"JPEGBYTES"
    assert r.headers["content-type"].startswith("image/jpeg")


def test_preview_endpoint_serves_non_jpg(auth, db, dirs, settings):
    make_mod_present(db, settings, WID_B)
    _write_preview(settings, WID_B, b"PNG", suffix=".png")
    r = auth.get(f"/api/mods/{WID_B}/preview")
    assert r.status_code == 200
    assert r.content == b"PNG"


# ---------- 回收站联动 ----------

def test_purge_deletes_local_preview(db, dirs, settings):
    make_mod_present(db, settings, WID_A)
    _write_preview(settings, WID_A)
    assert ps.has_preview(settings, WID_A)

    entry = trash.move_to_trash(db, settings, WID_A, actor="tester")
    db.commit()
    assert ps.has_preview(settings, WID_A)              # 移入回收站不动封面
    trash.purge(db, settings, entry.id, actor="tester")
    db.commit()
    assert ps.has_preview(settings, WID_A) is False     # 永久清除时一并删除


# ---------- 任务链路(API + 真实 worker) ----------

def test_scan_task_downloads_previews(auth, db, dirs, settings, monkeypatch):
    make_mod_present(db, settings, WID_A)

    def _fake_refresh(session, st, ids):
        m = session.get(Mod, WID_A)
        m.preview_url = U1
        session.commit()
        return {"refreshed": len(ids), "skipped": 0, "failed": 0, "unavailable": 0}

    monkeypatch.setattr(ps.steam, "refresh_metadata", _fake_refresh)
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "image/jpeg"},
                                         chunks=[b"J1", b"J2"])})

    r = auth.post("/api/mods/scan", json={"deep": False})
    assert r.status_code == 200, r.text
    task_id = r.json()["task"]["id"]
    assert wait_task(auth, task_id) == "succeeded"

    detail = auth.get(f"/api/tasks/{task_id}").json()
    assert detail["result"]["previews"]["saved"] == 1
    assert ps.preview_path(settings, WID_A).read_bytes() == b"J1J2"


def test_scan_task_skips_previews_when_disabled(auth, db, dirs, settings, monkeypatch):
    settings.auto_fetch_previews = False
    make_mod_present(db, settings, WID_A)
    monkeypatch.setattr(ps.steam, "refresh_metadata",
                        lambda s, st, ids: {"refreshed": 0})
    r = auth.post("/api/mods/scan", json={"deep": False})
    task_id = r.json()["task"]["id"]
    assert wait_task(auth, task_id) == "succeeded"
    detail = auth.get(f"/api/tasks/{task_id}").json()
    assert "previews" not in detail["result"]           # 关闭开关则完全跳过


def test_metadata_refresh_task_downloads_previews(auth, db, dirs, settings,
                                                  monkeypatch):
    make_mod_present(db, settings, WID_A)

    def _fake_refresh(session, st, ids):
        m = session.get(Mod, WID_A)
        m.preview_url = U1
        session.commit()
        return {"refreshed": 1, "skipped": 0, "failed": 0, "unavailable": 0}

    monkeypatch.setattr(ps.steam, "refresh_metadata", _fake_refresh)
    _install_http(monkeypatch, {U1: _Resp(headers={"content-type": "image/jpeg"},
                                         chunks=[b"M"])})

    r = auth.post("/api/mods/metadata/refresh", json={"ids": [WID_A]})
    assert r.status_code == 200, r.text
    task_id = r.json()["task"]["id"]
    assert wait_task(auth, task_id) == "succeeded"
    detail = auth.get(f"/api/tasks/{task_id}").json()
    assert detail["result"]["previews"]["saved"] == 1
