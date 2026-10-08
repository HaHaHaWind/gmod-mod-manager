"""安全预览代理:把 Steam CDN 的封面图经后端转发给浏览器。

安全设计:
1. 目标主机必须在后缀白名单内(Steam 官方 CDN 域)。
2. 仅 http/https、仅默认端口。
3. DNS 解析结果全部为公网地址才允许(拒绝私网/环回/链路本地/保留段)。
4. 不自动跟随重定向:手动逐跳校验(最多 3 跳),防止重定向绕过白名单。
5. 响应必须是 image/*,且超过 PREVIEW_MAX_BYTES 立即中断。
6. 响应头仅透传少量安全字段,并加 Cache-Control。

已知限制(在 docs/architecture.md 中亦有记录):DNS 解析校验与实际建立连接
之间存在经典的 TOCTOU 窗口(DNS rebinding)。由于白名单仅限大型 CDN 且
本面板只暴露在受信网络,评估为可接受残余风险;如需进一步收紧,可在部署层
为后端配置独立出站解析器。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..errors import bad_request, too_many

ALLOWED_HOST_SUFFIXES = (
    "steampowered.com",        # steamcdn-a / community.fastly / clans 等
    "akamaihd.net",            # steamuserimages-a.akamaihd.net
    "steamstatic.com",         # steamcommunity 相关静态资源
    "steamcontent.com",
)
MAX_REDIRECTS = 3
_CHUNK = 32 * 1024


def validate_preview_url(raw: str):
    """校验 URL 形态与主机白名单。返回解析结果。"""
    try:
        parts = urlparse((raw or "").strip())
    except ValueError:
        raise bad_request("预览地址无法解析", code="bad_preview_url")
    if parts.scheme not in ("http", "https"):
        raise bad_request("预览地址仅支持 http/https", code="bad_preview_url")
    host = (parts.hostname or "").lower()
    if not host:
        raise bad_request("预览地址缺少主机名", code="bad_preview_url")
    if ":" in host:  # IPv6 字面量:白名单均为域名,直接拒绝
        raise bad_request("预览地址不支持 IPv6 字面量", code="bad_preview_url")
    if parts.port not in (None, 80, 443):
        raise bad_request("预览地址仅允许 80/443 端口", code="bad_preview_url")
    if not any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES):
        raise bad_request("预览地址主机不在允许列表", code="preview_host_denied")
    return parts


def assert_resolves_public(host: str) -> None:
    """DNS 解析并检查全部地址均为公网。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise bad_request(f"预览地址解析失败:{e}", code="preview_dns_failed")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise bad_request("预览地址解析到内网地址,已拒绝", code="preview_ssrf_blocked")


def stream_preview(settings: Settings, url: str):
    """生成器:yield (headers_dict, chunk_bytes)。首个 yield 前完成全部校验。"""
    parts = validate_preview_url(url)
    assert_resolves_public(parts.hostname)

    current = url
    for _hop in range(MAX_REDIRECTS + 1):
        cp = validate_preview_url(current)
        assert_resolves_public(cp.hostname)
        with httpx.Client(timeout=settings.steam_timeout_seconds,
                          proxy=settings.steam_proxy or None,
                          follow_redirects=False) as client:
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    if _hop == MAX_REDIRECTS:
                        raise bad_request("预览重定向次数过多", code="preview_redirect_loop")
                    loc = resp.headers.get("location", "")
                    if not loc:
                        raise bad_request("预览重定向缺少目标", code="bad_preview_url")
                    from urllib.parse import urljoin
                    current = urljoin(current, loc)
                    continue
                if resp.status_code != 200:
                    raise bad_request(f"预览源返回 HTTP {resp.status_code}", code="preview_upstream_error")
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not ctype.startswith("image/"):
                    raise bad_request("预览源不是图片", code="preview_not_image")
                headers = {
                    "Content-Type": ctype,
                    "Content-Length": resp.headers.get("content-length", ""),
                    "Cache-Control": "public, max-age=86400",
                }
                yield headers, None
                sent = 0
                limit = settings.preview_max_bytes
                for chunk in resp.iter_bytes(_CHUNK):
                    sent += len(chunk)
                    if sent > limit:
                        raise too_many("预览图片超过大小上限", code="preview_too_large")
                    yield None, chunk
                return
    raise bad_request("预览请求失败", code="preview_failed")
