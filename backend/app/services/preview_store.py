"""本地预览图存取:扫描/元数据刷新后自动抓取 Steam 封面落盘。

设计:
1. 存储:<data_dir>/previews/<workshop_id>.jpg 等按内容类型定后缀,与面板数据同目录,随备份一起走。
2. 下载安全:复用 preview.py 的 URL 白名单、SSRF DNS 校验、逐跳重定向校验、image/* 校验与大小上限。
3. 原子落盘:先写 .part 临时文件再 os.replace,进程中断不会留下半张图。
4. 容错:单张失败仅计数,绝不影响扫描/刷新任务的整体结果(网络不可用只体现在统计里)。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Mod
from ..errors import ApiError
from . import preview as pv
from . import steam

log = logging.getLogger("gmm.preview_store")

_EXT_BY_CTYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_CHUNK = 32 * 1024
MAX_REDIRECTS = 3


def previews_dir(settings: Settings) -> Path:
    return settings.data_path / "previews"


def preview_path(settings: Settings, wid: str) -> Path:
    """返回该 Mod 的本地预览图路径(存在与否由调用方判断)。"""
    return previews_dir(settings) / f"{wid}.jpg"


def find_preview(settings: Settings, wid: str) -> Path | None:
    """返回本地预览图的实际路径(后缀按内容类型可能是 .png 等);无则 None。"""
    d = previews_dir(settings)
    if not d.is_dir():
        return None
    for p in sorted(d.glob(f"{wid}.*")):
        if p.suffix in _EXT_BY_CTYPE.values() and p.is_file():
            return p
    return None


def has_preview(settings: Settings, wid: str) -> bool:
    d = previews_dir(settings)
    if not d.is_dir():
        return False
    return any(d.glob(f"{wid}.*"))


def delete_preview(settings: Settings, wid: str) -> bool:
    """删除本地预览图(回收站永久清除时联动);返回是否删了文件。"""
    d = previews_dir(settings)
    removed = False
    if d.is_dir():
        for p in d.glob(f"{wid}.*"):
            try:
                p.unlink()
                removed = True
            except OSError:
                log.warning("预览图删除失败:%s", p)
    return removed


def download_preview(settings: Settings, wid: str, url: str) -> str:
    """下载单张封面到本地。返回 saved/invalid/failed,失败不打断调用方。"""
    try:
        pv.validate_preview_url(url)
    except ApiError:
        return "invalid"
    tmp: Path | None = None
    current = url
    try:
        base = preview_path(settings, wid)
        base.parent.mkdir(parents=True, exist_ok=True)
        tmp = base.with_name(base.name + ".part")
        ctype = ""
        for _hop in range(MAX_REDIRECTS + 1):
            parts = pv.validate_preview_url(current)
            pv.assert_resolves_public(parts.hostname)
            with httpx.Client(timeout=settings.steam_timeout_seconds,
                              follow_redirects=False) as client:
                with client.stream("GET", current) as resp:
                    if resp.is_redirect:
                        if _hop == MAX_REDIRECTS:
                            return "failed"
                        loc = resp.headers.get("location", "")
                        if not loc:
                            return "invalid"
                        from urllib.parse import urljoin
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code != 200:
                        return "failed"
                    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                    if ctype not in _EXT_BY_CTYPE:
                        return "invalid"
                    sent = 0
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_bytes(_CHUNK):
                            sent += len(chunk)
                            if sent > settings.preview_max_bytes:
                                return "invalid"  # 超上限按拒绝处理
                            f.write(chunk)
                    break
        dest = base.with_suffix(_EXT_BY_CTYPE.get(ctype, ".jpg"))
        os.replace(tmp, dest)
        return "saved"
    except (httpx.HTTPError, OSError, ApiError) as e:
        log.info("预览图下载失败 wid=%s:%s", wid, e)
        return "failed"
    finally:
        # 残留的 .part 一并清理(成功路径 os.replace 已移走,missing_ok 兜底)
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def ensure_previews(session: Session, settings: Settings, ids: list[str]) -> dict:
    """为一组 Mod 补齐本地封面:已有跳过,无远程地址跳过,下载逐张容错。"""
    stats = {"total": 0, "cached": 0, "saved": 0, "failed": 0, "no_url": 0}
    for wid in ids:
        stats["total"] += 1
        if has_preview(settings, wid):
            stats["cached"] += 1
            continue
        mod = session.get(Mod, wid)
        if mod is None or not (mod.preview_url or "").strip():
            stats["no_url"] += 1
            continue
        r = download_preview(settings, wid, mod.preview_url)
        if r == "saved":
            stats["saved"] += 1
        elif r == "failed":
            stats["failed"] += 1
        else:
            stats["no_url"] += 1  # 地址非法视为无可用封面
    return stats


def sync_after_scan(session: Session, settings: Settings) -> dict:
    """扫描后补齐所有在场 Mod 的封面:缺远程地址/已过期的先刷新元数据,再统一下载。

    返回扁平结构:{"meta": 元数据刷新统计或错误, "total/saved/cached/...": 下载统计}。
    """
    ids = [w for (w,) in session.query(Mod.workshop_id)
           .filter(Mod.inventory_state == "present").all()]
    meta = None
    if ids:
        try:
            meta = steam.refresh_metadata(session, settings, ids)  # 内部跳过仍新鲜者
        except steam.SteamError as e:
            meta = {"error": str(e)[:300]}
            log.info("扫描后元数据刷新失败(继续下载已有封面):%s", e)
    return {"meta": meta, **ensure_previews(session, settings, ids)}
