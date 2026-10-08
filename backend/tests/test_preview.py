"""预览代理安全:URL 白名单 / 端口与 scheme / SSRF DNS 检查 / 重定向与内容校验。"""
import socket

import pytest

from app.errors import ApiError
from app.services import preview
from app.services.preview import (assert_resolves_public, stream_preview,
                                  validate_preview_url)

OK_URL = "https://steamuserimages-a.akamaihd.net/ugc/123/ABC.jpg"


def _expect(code: str, fn, *args):
    with pytest.raises(ApiError) as ei:
        fn(*args)
    assert ei.value.code == code
    return ei


# ---------- URL 形态与白名单 ----------

@pytest.mark.parametrize("url", [
    "https://steamcdn-a.akamaihd.net/steamcommunity/public/images/x.jpg",
    "http://clans.cloudflare.steampowered.com/banner.jpg",
    "https://shared.fastly.steampowered.com/a.png",
    "https://steamuserimages-a.akamaihd.net/ugc/1/x.jpg",
    "https://images.steamusercontent.com/ugc/123/ABC/",  # 工坊图片现行 CDN 域
    "https://steamusercontent.com/i.png",
    "https://steamstatic.com/i.png",
    "https://cache1.steamcontent.com/z.bin",
])
def test_validate_accepts_whitelisted_hosts(url):
    assert validate_preview_url(url).scheme in ("http", "https")


@pytest.mark.parametrize("url,code", [
    ("ftp://steamcdn-a.akamaihd.net/x.jpg", "bad_preview_url"),          # scheme
    ("https://steamcdn-a.akamaihd.net:8080/x.jpg", "bad_preview_url"),   # 非默认端口
    ("https://evil.example.com/x.jpg", "preview_host_denied"),           # 域名外
    ("https://steampowered.com.evil.com/x.jpg", "preview_host_denied"),  # 后缀仿冒
    ("https://x.jpg@steampowered.com.evil.net/y", "preview_host_denied"),
    ("https://steamusercontent.com.evil.com/x.jpg", "preview_host_denied"),
    ("https://[2001:db8::1]/x.jpg", "bad_preview_url"),                  # IPv6 字面量
    ("https:///nohost.jpg", "bad_preview_url"),                          # 缺主机
])
def test_validate_rejects_bad_urls(url, code):
    _expect(code, validate_preview_url, url)


# ---------- SSRF:DNS 解析必须全公网 ----------

def _fake_getaddrinfo(monkeypatch, *ips):
    infos = [(socket.AF_INET, None, None, "", (ip, 0)) for ip in ips]
    monkeypatch.setattr(preview.socket, "getaddrinfo", lambda *a, **k: infos)


def test_ssrf_blocks_private_addresses(monkeypatch):
    for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.9", "172.16.0.1",
               "169.254.169.254", "0.0.0.0", "224.0.0.1", "240.0.0.1"):
        _fake_getaddrinfo(monkeypatch, ip)
        _expect("preview_ssrf_blocked", assert_resolves_public,
                "steamcdn-a.akamaihd.net")


def test_ssrf_mixed_addresses_rejected(monkeypatch):
    """任一解析结果为内网即拒绝(不能只检查第一个)。"""
    _fake_getaddrinfo(monkeypatch, "8.8.8.8", "10.0.0.1")
    _expect("preview_ssrf_blocked", assert_resolves_public, "steamcdn-a.akamaihd.net")


def test_ssrf_allows_public(monkeypatch):
    _fake_getaddrinfo(monkeypatch, "8.8.8.8", "1.2.3.4")
    assert_resolves_public("steamcdn-a.akamaihd.net")


def test_dns_failure_maps_to_api_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("nameserver timeout")
    monkeypatch.setattr(preview.socket, "getaddrinfo", boom)
    _expect("preview_dns_failed", assert_resolves_public, "steamcdn-a.akamaihd.net")


# ---------- 流式代理:重定向 / 内容类型 / 大小上限 ----------

class FakeResp:
    def __init__(self, status=200, headers=None, chunks=(b"data",),
                 is_redirect=False, location=""):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.is_redirect = is_redirect
        if location:
            self.headers["location"] = location

    def iter_bytes(self, n):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeClient:
    script: list[FakeResp] = []   # 每跳弹出一个响应

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def stream(self, method, url):
        return FakeClient.script.pop(0)


@pytest.fixture()
def fake_http(monkeypatch):
    monkeypatch.setattr(preview.httpx, "Client", FakeClient)
    _fake_getaddrinfo(monkeypatch, "93.184.216.34")   # 全部跳都解析到公网
    return FakeClient


def _consume(settings, url):
    headers, body = None, bytearray()
    for h, chunk in stream_preview(settings, url):
        if h:
            headers = h
        if chunk:
            body += chunk
    return headers, bytes(body)


def test_stream_ok(fake_http, settings):
    fake_http.script = [FakeResp(headers={"content-type": "image/png; charset=binary"},
                                 chunks=(b"PN", b"GDATA"))]
    headers, body = _consume(settings, OK_URL)
    assert body == b"PNGDATA"
    assert headers["Content-Type"] == "image/png"
    assert "max-age" in headers["Cache-Control"]


def test_stream_rejects_non_image(fake_http, settings):
    fake_http.script = [FakeResp(headers={"content-type": "text/html"})]
    _expect("preview_not_image", _consume, settings, OK_URL)


def test_stream_validates_redirect_target(fake_http, settings):
    """重定向到白名单外域名 → 拒绝(手动逐跳校验,不自动跟随)。"""
    fake_http.script = [FakeResp(status=302, is_redirect=True,
                                 location="https://evil.example.com/x.jpg")]
    _expect("preview_host_denied", _consume, settings, OK_URL)


def test_stream_rejects_private_redirect_target(fake_http, settings, monkeypatch):
    fake_http.script = [FakeResp(status=302, is_redirect=True,
                                 location="http://steamstatic.com/x.jpg")]
    # 第二跳 DNS 解析到内网 → SSRF 拦截
    infos = [(socket.AF_INET, None, None, "", ("127.0.0.1", 0))]
    monkeypatch.setattr(preview.socket, "getaddrinfo", lambda *a, **k: infos)
    _expect("preview_ssrf_blocked", _consume, settings, OK_URL)


def test_stream_redirect_loop(fake_http, settings):
    fake_http.script = [FakeResp(status=302, is_redirect=True, location="/2.jpg")
                        for _ in range(4)]
    _expect("preview_redirect_loop", _consume, settings, OK_URL)


def test_stream_upstream_error(fake_http, settings):
    fake_http.script = [FakeResp(status=404)]
    _expect("preview_upstream_error", _consume, settings, OK_URL)


def test_stream_size_limit(fake_http, settings, monkeypatch):
    monkeypatch.setattr(settings, "preview_max_bytes", 8)
    fake_http.script = [FakeResp(headers={"content-type": "image/png"},
                                 chunks=(b"a" * 5, b"b" * 5))]
    _expect("preview_too_large", _consume, settings, OK_URL)
