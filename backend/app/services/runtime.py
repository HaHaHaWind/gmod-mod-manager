"""srcds 进程探测 + "待重启"标记调和。

背景与语义:
- requires_restart 的含义是"**运行中的 srcds 实例还没加载最新配置**",
  它只在 apply / 删除时被置 True;此前没有任何清除路径,导致服务器重启后
  UI 仍一直显示"待重启"。
- 该实例由 MCSManager(而非 systemd)拉起,因此以 **进程启动时刻** 作为重启证据:
    * 找不到 srcds 进程 → 不存在旧实例,标记应清除(下次启动自然生效);
    * 进程启动时刻晚于"最新配置写入时刻" → 已重启并加载,标记应清除;
    * 进程启动时刻早于/等于配置写入时刻 → 旧实例仍在跑,保留标记。
- "最新配置写入时刻"取 max(ids 文件 mtime, addons 目录 mtime):apply 当刻就会写这两个位置,
  文件 mtime 天然等于变更时刻,无需新增数据库字段或迁移。

安全:本模块**纯读 /proc 与文件元数据**,不写游戏服务器文件、不杀进程、不重启。
非 Linux 平台(无 /proc)一律跳过,不做任何清除。
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models.entities import Mod

log = logging.getLogger("gmm.runtime")

try:
    _CLK_TCK = os.sysconf("SC_CLK_TCK")
except (AttributeError, ValueError, OSError):  # 非 Linux 平台无 sysconf
    _CLK_TCK = 100

_PROC = Path("/proc")


@dataclass
class SrcdsProc:
    pid: int
    start_epoch: float


def _read_comm(pid: int) -> str:
    try:
        return (_PROC / str(pid) / "comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_start_epoch(pid: int) -> float | None:
    """由 /proc/<pid>/stat 的 starttime(第 22 字段,单位 clock tick)反推启动 epoch。"""
    try:
        raw = (_PROC / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # comm 可能含空格或括号,必须从最后一个 ')' 之后再切字段
    rp = raw.rfind(")")
    if rp < 0:
        return None
    fields = raw[rp + 2:].split()
    if len(fields) < 20:  # fields[0] 是 state,starttime 为 fields[19]
        return None
    try:
        start_ticks = int(fields[19])
    except ValueError:
        return None
    try:
        uptime = float((_PROC / "uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    return time.time() - uptime + start_ticks / _CLK_TCK


def _names(settings: Settings) -> list[str]:
    raw = (settings.gmod_process_names or "srcds").lower()
    return [x.strip() for x in raw.split(",") if x.strip()]


def find_srcds(settings: Settings) -> SrcdsProc | None:
    """返回启动时间最新的匹配进程。

    同一实例会有启动脚本与引擎两个进程(comm 前缀都是 srcds),取启动更晚者即引擎,
    两者相差数秒,对"是否重启过"的判断没有影响。
    """
    names = _names(settings)
    if not names or not _PROC.is_dir():
        return None
    best: SrcdsProc | None = None
    try:
        entries = os.listdir(_PROC)
    except OSError:
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        comm = _read_comm(pid).lower()
        if not comm or not any(comm.startswith(n) for n in names):
            continue
        start = _read_start_epoch(pid)
        if start is None:
            continue
        if best is None or start > best.start_epoch:
            best = SrcdsProc(pid=pid, start_epoch=start)
    return best


def latest_config_write(settings: Settings) -> float | None:
    """最新一次影响加载入口的写入时刻 = max(ids 文件 mtime, addons 目录 mtime)。"""
    stamps: list[float] = []
    for p in (settings.ids_file, settings.addons_root):
        if p is None:
            continue
        try:
            stamps.append(p.stat().st_mtime)
        except OSError:
            continue
    return max(stamps) if stamps else None


def reconcile_restart_flags(session: Session, settings: Settings) -> dict:
    """清除已不再成立的 requires_restart;返回诊断摘要(供日志/测试)。

    不在此处 commit:由调用方(例行维护 / 扫描任务)统一提交。
    """
    flagged = session.execute(
        select(Mod).where(Mod.requires_restart == True)  # noqa: E712
    ).scalars().all()
    if not flagged:
        return {"flagged": 0, "cleared": 0, "reason": "none"}
    if not _PROC.is_dir():
        return {"flagged": len(flagged), "cleared": 0, "reason": "unsupported"}

    proc = find_srcds(settings)
    if proc is None:
        reason = "no_process"
    else:
        changed = latest_config_write(settings)
        if changed is None or proc.start_epoch <= changed:
            return {"flagged": len(flagged), "cleared": 0, "reason": "still_pending",
                    "srcds_pid": proc.pid, "srcds_start": int(proc.start_epoch)}
        reason = "restarted"

    for mod in flagged:
        mod.requires_restart = False
        session.add(mod)
    log.info("清除待重启标记:%d 个(依据=%s)", len(flagged), reason)
    return {"flagged": len(flagged), "cleared": len(flagged), "reason": reason}