"""Steam Workshop 元数据获取(无需 API Key 的公开接口)。

依据 docs/gmod-loading-research.md 第 4 节:
- POST ISteamRemoteStorage/GetPublishedFileDetails/v1/(itemcount + publishedfileids[i])
- POST ISteamRemoteStorage/GetCollectionDetails/v1/
- 官方未记载批量上限,采用社区经验值 100(可配置 STEAM_BATCH_LIMIT)
- 每项 result=1 才算成功;其余按失败记录原因,绝不静默吞掉
"""
from __future__ import annotations

import re
import time
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from .. import constants as C
from ..config import Settings
from ..models.entities import CollectionSnapshot, Mod, utcnow
from .categories import derive_category

_TAG_RE = re.compile(r"<[^>]+>")
_TAG_SAFE_RE = re.compile(r"\[(/?[a-zA-Z0-9_]+)[^\]]*\]")
MAX_IDS_PER_REQUEST = 100  # 硬上限,防止误配置 STEAM_BATCH_LIMIT 过大


class SteamError(Exception):
    """Steam 接口不可用或返回异常。中文消息可直接展示。"""


def _batch_size(settings: Settings) -> int:
    return max(1, min(settings.steam_batch_limit, MAX_IDS_PER_REQUEST))


def _post_with_retry(settings: Settings, form: dict) -> dict:
    url = settings.steam_api_base.rstrip("/") + "/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    last_exc: Exception | None = None
    for attempt in range(settings.steam_retries + 1):
        try:
            with httpx.Client(timeout=settings.steam_timeout_seconds,
                              proxy=settings.steam_proxy or None) as client:
                resp = client.post(url, data=form)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            last_exc = e
            if attempt < settings.steam_retries:
                time.sleep(0.8 * (attempt + 1))  # 简单退避;任务线程中可接受
    raise SteamError(f"Steam 接口请求失败:{last_exc}")


def fetch_details(settings: Settings, ids: list[str]) -> tuple[dict[str, dict], list[dict]]:
    """批量获取详情。返回 (成功映射 wid→detail, 失败列表 [{id, reason, kind}])。

    kind=unavailable:物品不可访问/已下架,属稳定状态(不重试);
    kind=error:需重试的错误(如物品不属于 Garry's Mod)。
    """
    ok: dict[str, dict] = {}
    failed: list[dict] = []
    ordered = list(dict.fromkeys(ids))
    for i in range(0, len(ordered), _batch_size(settings)):
        chunk = ordered[i:i + _batch_size(settings)]
        form: dict = {"itemcount": str(len(chunk))}
        for j, wid in enumerate(chunk):
            form[f"publishedfileids[{j}]"] = wid
        data = _post_with_retry(settings, form)
        response = data.get("response") or {}
        details = response.get("publishedfiledetails")
        if not isinstance(details, list):
            raise SteamError("Steam 响应缺少 publishedfiledetails 字段")
        by_id = {}
        for d in details:
            by_id[str(d.get("publishedfileid"))] = d
        for wid in chunk:
            d = by_id.get(wid)
            if d is None:
                failed.append({"id": wid, "reason": "Steam 响应中缺少该项", "kind": "unavailable"})
            elif int(d.get("result", 0)) != 1:
                code = int(d.get("result") or 0)
                msg = ("该创意工坊物品已被删除或下架" if code == 9
                       else f"该创意工坊物品不可访问(result={code})")
                failed.append({"id": wid, "reason": msg, "kind": "unavailable"})
            elif int(d.get("consumer_app_id", 0) or 0) not in (0, 4000):
                failed.append({"id": wid, "reason": "该物品不属于 Garry's Mod(AppId=4000)",
                               "kind": "error"})
            else:
                ok[wid] = d
    return ok, failed


def _clean_description(raw: str) -> str:
    """Steam 描述混有 BBCode 与 HTML:去标签保文本,足够列表/详情展示。"""
    text = _TAG_RE.sub("", raw or "")
    text = _TAG_SAFE_RE.sub("", text)
    return text.strip()


def apply_details(mod: Mod, d: dict) -> None:
    """把 Steam 详情写入 Mod 元数据缓存字段(远程优先原则)。"""
    mod.title_remote = (d.get("title") or "").strip()[:512]
    mod.author_steamid = str(d.get("creator") or "")
    mod.author_name = (d.get("author") or "").strip()[:256]
    mod.description = _clean_description(d.get("description") or "")
    mod.tags = [t.get("tag", "") for t in (d.get("tags") or []) if isinstance(t, dict)]
    mod.category = derive_category(mod.tags)
    mod.preview_url = (d.get("preview_url") or "")[:1024]
    mod.remote_file_size = int(d.get("file_size") or 0) or None
    mod.time_published = int(d.get("time_created") or 0) or None
    mod.time_updated = int(d.get("time_updated") or 0) or None
    vis = int(d.get("file_visibility", 0) or 0)
    mod.remote_visibility = {0: "unknown", 1: "public", 2: "friends", 3: "private", 8: "unlisted"}.get(vis, str(vis))
    mod.metadata_state = "fresh"
    mod.metadata_source = "steam"
    mod.metadata_fetched_at = utcnow()
    mod.metadata_error = ""


def mark_error(mod: Mod, reason: str) -> None:
    mod.metadata_state = "error"
    mod.metadata_error = reason[:512]
    mod.metadata_fetched_at = utcnow()


def mark_unavailable(mod: Mod, reason: str) -> None:
    """物品不可访问(私密/被删):不是错误,是稳定状态。"""
    mod.metadata_state = "unavailable"
    mod.metadata_error = reason[:512]
    mod.metadata_fetched_at = utcnow()


def is_fresh(mod: Mod, settings: Settings) -> bool:
    if mod.metadata_state != "fresh" or mod.metadata_fetched_at is None:
        return False
    age = utcnow() - mod.metadata_fetched_at
    if age >= timedelta(seconds=settings.metadata_ttl_seconds):
        mod.metadata_state = "stale"
        return False
    return True


def refresh_metadata(session: Session, settings: Settings, ids: list[str]) -> dict:
    """刷新一批 ID 的元数据,跳过仍新鲜者。返回统计供任务进度使用。"""
    stats = {"refreshed": 0, "skipped": 0, "failed": 0, "unavailable": 0}
    need: list[str] = []
    for wid in ids:
        mod = session.get(Mod, wid)
        if mod is not None and is_fresh(mod, settings):
            stats["skipped"] += 1
            continue
        need.append(wid)
    if not need:
        return stats
    details, failed = fetch_details(settings, need)
    failed_map = {f["id"]: f for f in failed}
    for wid in need:
        mod = session.get(Mod, wid)
        if mod is None:
            continue
        if wid in details:
            d = details[wid]
            if int(d.get("file_visibility", 1) or 1) == 0:
                mark_unavailable(mod, "该物品不可公开访问")
                stats["unavailable"] += 1
            else:
                apply_details(mod, d)
                stats["refreshed"] += 1
        elif wid in failed_map:
            f = failed_map[wid]
            if f.get("kind") == "unavailable":
                mark_unavailable(mod, f["reason"])
                stats["unavailable"] += 1
            else:
                mark_error(mod, f["reason"])
                stats["failed"] += 1
    session.commit()
    return stats


# ---------- 合集展开 ----------

def _post_collection(settings: Settings, form: dict) -> dict:
    url = settings.steam_api_base.rstrip("/") + "/ISteamRemoteStorage/GetCollectionDetails/v1/"
    last_exc: Exception | None = None
    for attempt in range(settings.steam_retries + 1):
        try:
            with httpx.Client(timeout=settings.steam_timeout_seconds,
                              proxy=settings.steam_proxy or None) as client:
                resp = client.post(url, data=form)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            last_exc = e
            if attempt < settings.steam_retries:
                time.sleep(0.8 * (attempt + 1))
    raise SteamError(f"Steam 合集接口请求失败:{last_exc}")


def expand_collection(settings: Settings, collection_id: str) -> dict:
    """展开合集:返回 items(普通物品)/sub_collections/inaccessible。"""
    form = {
        "collectioncount": "1",
        "publishedfileids[0]": collection_id,
    }
    data = _post_collection(settings, form)
    details = ((data.get("response") or {}).get("collectiondetails") or [{}])[0]
    if int(details.get("result", 0)) != 1:
        raise SteamError(f"合集查询失败:result={details.get('result')}")
    items: list[str] = []
    subs: list[str] = []
    for child in details.get("children") or []:
        cid = str(child.get("publishedfileid") or "")
        if not cid:
            continue
        ftype = int(child.get("filetype", 0) or 0)
        if ftype == 2:  # collection
            subs.append(cid)
        else:
            items.append(cid)
    return {"items": items, "sub_collections": subs, "inaccessible": []}


def snapshot_collection(session: Session, settings: Settings, collection_id: str) -> CollectionSnapshot:
    """拉取合集并存快照(用于冲突识别:外部集合可能重新引入已禁用 ID)。"""
    expanded = expand_collection(settings, collection_id)
    snap = session.get(CollectionSnapshot, collection_id)
    if snap is None:
        snap = CollectionSnapshot(collection_id=collection_id)
        session.add(snap)
    snap.items = expanded["items"]
    snap.sub_collections = expanded["sub_collections"]
    snap.inaccessible = expanded["inaccessible"]
    snap.fetched_at = utcnow()
    snap.status = "ok"
    session.commit()
    return snap
