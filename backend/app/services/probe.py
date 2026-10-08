"""srcds 运行时挂载探针:从 srcds 自动写出的 Workshop 缓存读取"实际挂载了哪些 ID"。

背景(经 GMod 官方 Wiki 与 Rubat 提交记录核实):
- cfg/srcds_addons.txt 是 srcds 运行时**自动生成**的挂载缓存,不是配置文件;
  原生 workshop 方式直接从 steam_cache 挂载 .gma,addons/ 目录下不会有文件;
- 新版 srcds 已把该缓存从 cfg/srcds_addons.txt(位置太笼统)迁移到
  <srcds 根>/cache/srcds_addon_list_cache.txt,旧位置仍被读取以兼容;
- 它是 runtime_state 的直接证据源:缓存里列出的 ID 即 srcds 挂载的模组。

安全语义(与调研文档第 3 节一致):
- 探针被禁用/缺失/不可读/过大 → 一律 unknown,绝不臆测;
- 探针存在时才产出 loaded / not_loaded;
- 探针反映的是 srcds 最近一次写出的挂载记录,服务器未运行时即"上次会话"的事实。
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import constants as C
from ..config import Settings
from ..models.entities import Mod

_MAX_PROBE_BYTES = 8 * 1024 * 1024  # 探针文件正常只有几 KB;超限视为异常拒绝读取
# KeyValues 形式:"wsid" "123277559"(新版缓存可能带键名)
_WSID_KV = re.compile(r'wsid"\s*"(\d{1,20})"', re.IGNORECASE)
# 退化形式:独立的纯数字 token(≥3 位,前后不能是字母/数字/点,避免匹配版本号片段、路径名)
_BARE_ID = re.compile(r"(?<![\w.])\d{3,20}(?![\w.])")


def _candidates(settings: Settings) -> list[Path]:
    """按优先级列出候选探针路径(不检查存在性)。"""
    out: list[Path] = []
    ids = settings.ids_file
    if ids is not None:  # 旧版布局:<garrysmod>/cfg/srcds_addons.txt
        out.append(ids.parent / "srcds_addons.txt")
    addons = settings.addons_root
    if addons is not None:
        # 新版布局:<srcds 根>/cache/srcds_addon_list_cache.txt(garrysmod 的上级即 srcds 根)
        out.append(addons.parent.parent / "cache" / "srcds_addon_list_cache.txt")
        # 兜底:garrysmod/cache/srcds_addon_list_cache.txt
        out.append(addons.parent / "cache" / "srcds_addon_list_cache.txt")
    return out


def find_probe_file(settings: Settings) -> Path | None:
    """返回第一个可用的探针文件;显式配置优先,禁用时返回 None。"""
    if not settings.runtime_probe_enabled:
        return None
    explicit = (settings.runtime_probe_file or "").strip()
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for p in _candidates(settings):
        if p.is_file():
            return p
    return None


def parse_mounted_ids(text: str) -> set[str]:
    """宽容解析探针内容:优先 KeyValues 的 wsid 键,否则退化为独立数字 token。

    探针是 srcds 自己写出的缓存,格式未在官方文档中完整定义,
    因此对"每行一个 ID""KeyValues 块"等形式都保持兼容;解析不出 ID 就返回空集。
    """
    ids = set(_WSID_KV.findall(text))
    if ids:
        return ids
    return set(_BARE_ID.findall(text))


def read_mounted_ids(settings: Settings) -> tuple[str, set[str]]:
    """读取探针。返回 (状态描述, 挂载 ID 集合)。

    状态描述用于日志与扫描报告:disabled / not_found / unreadable:<原因> /
    oversize:<文件名> / ok:<路径>。
    """
    if not settings.runtime_probe_enabled:
        return "disabled", set()
    path = find_probe_file(settings)
    if path is None:
        return "not_found", set()
    try:
        raw = path.read_bytes()
    except OSError as e:
        return f"unreadable:{e}", set()
    if len(raw) > _MAX_PROBE_BYTES:
        return f"oversize:{path.name}", set()
    ids = parse_mounted_ids(raw.decode("utf-8", errors="replace"))
    return f"ok:{path}", ids


def update_runtime_states(session: Session, settings: Settings) -> str:
    """按探针刷新全部 Mod 的 runtime_state,返回探针状态描述(写入扫描报告)。

    探针不可用(禁用/缺失/不可读)时:全部保持 unknown——
    "没有证据就不下结论"是五维状态模型的安全底线。
    """
    status, mounted = read_mounted_ids(settings)
    if not mounted:
        unknown = C.RuntimeState.UNKNOWN.value
        for mod in session.execute(select(Mod)).scalars():
            mod.runtime_state = unknown
        return status
    loaded = C.RuntimeState.LOADED.value
    not_loaded = C.RuntimeState.NOT_LOADED.value
    for mod in session.execute(select(Mod)).scalars():
        mod.runtime_state = loaded if mod.workshop_id in mounted else not_loaded
    return status
