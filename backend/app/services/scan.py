"""缓存与 addons 目录扫描:发现、登记、五维状态调和。

职责边界:本模块只"观察与登记",不修改任何游戏服务器文件;
写入行为(改清单/部署副本/回收站)全部在 adapters 与 services.trash 中。

约定:
- Workshop 缓存布局:cache_root/<ID>/garrysmod/addons/*.gma(容错:也接受 cache_root/<ID>/*.gma)
- 受管部署命名:文件 `gmm_<ID>_v<N>.gma`,文件夹 `gmm_<ID>`(gma_copy / folder_extract 两种策略)
- 大小写不敏感文件系统:ID 目录名统一按原样记录,匹配以字符串精确比较
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import constants as C
from ..config import Settings
from ..models.entities import CollectionSnapshot, Mod, ModFile, TrashEntry, utcnow
from . import gma, probe, runtime
from .idsfile import parse_ids_file
from .paths import detect_dir_nesting

_ID_DIR = re.compile(r"^[0-9]{1,20}$")
_MANAGED_FILE = re.compile(r"^gmm_([0-9]{1,20})_v([0-9]+)\.gma$", re.IGNORECASE)
_MANAGED_DIR = re.compile(r"^gmm_([0-9]{1,20})$", re.IGNORECASE)
_MAX_SNAPSHOT_FILES = 500      # ModFile 快照上限,超出截断并在 note 标注
_MAX_EXTERNAL_PARSE = 100      # 外部 addon 最多解析元数据的条数


@dataclass
class GmaFound:
    path: Path
    size: int
    mtime: float


@dataclass
class CacheFind:
    workshop_id: str
    directory: Path
    gmas: list[GmaFound] = field(default_factory=list)
    non_gma: list[str] = field(default_factory=list)  # 疑似 addon 但文件头非 GMAD(如压缩内容)


@dataclass
class AddonsEntry:
    name: str
    path: Path
    kind: str                    # gma | folder
    managed: bool
    workshop_id: str | None
    version: int | None
    size: int


@dataclass
class ScanReport:
    started_at: float = field(default_factory=time.time)
    anomalies: list[str] = field(default_factory=list)
    cache_ids: list[str] = field(default_factory=list)
    addons_entries: list[AddonsEntry] = field(default_factory=list)
    ids_in_file: list[str] = field(default_factory=list)
    ids_file_error: str = ""
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    runtime_probe: str = ""  # 探针状态:disabled / not_found / unreadable:<原因> / ok:<路径>

    @property
    def duration_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def summary(self) -> dict:
        return {
            "duration_ms": self.duration_ms,
            "cache_ids": len(self.cache_ids),
            "created": len(self.created),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
            "missing": len(self.missing),
            "invalid": len(self.invalid),
            "anomalies": self.anomalies,
            "runtime_probe": self.runtime_probe,
        }


# ---------- 发现 ----------

def _find_gmas(directory: Path) -> tuple[list[GmaFound], list[str]]:
    """在 ID 目录中定位 GMA:优先标准布局 garrysmod/addons/,退化为一层查找。

    老的创意工坊条目(legacy)在缓存里以 .bin 后缀存放,内容为 GMA(可能经
    LZMA 压缩),因此除 .gma 外也接受内容确为 GMA 的 .bin;其余 .bin 记入
    non_gma,供上层给出准确原因,而不是笼统的"未找到 .gma 文件"。
    """
    found: list[GmaFound] = []
    non_gma: list[str] = []
    std = directory / "garrysmod" / "addons"
    search_dirs = [std] if std.is_dir() else [directory]
    for base in search_dirs:
        try:
            for p in base.iterdir():
                if p.is_symlink() or not p.is_file():
                    continue
                ext = p.suffix.lower()
                if ext == ".gma" or (ext == ".bin" and gma.is_gma_package(p)):
                    st = p.stat()
                    found.append(GmaFound(path=p, size=st.st_size, mtime=st.st_mtime))
                elif ext == ".bin":
                    non_gma.append(p.name)
        except OSError as e:
            found.append(GmaFound(path=base / f"<io-error:{e.errno}>", size=-1, mtime=0))
    return found, non_gma


def discover_cache(settings: Settings, report: ScanReport) -> list[CacheFind]:
    root = settings.cache_root
    if root is None:
        report.anomalies.append("未配置 Workshop 缓存根目录(WORKSHOP_CACHE_ROOT),跳过缓存扫描")
        return []
    if not root.is_dir():
        report.anomalies.append(f"缓存根目录不存在或不可访问:{root}")
        return []
    trash = settings.trash_path
    finds: list[CacheFind] = []
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError as e:
        report.anomalies.append(f"缓存根目录读取失败:{e}")
        return []
    for child in children:
        if not child.is_dir():
            continue
        if trash and detect_dir_nesting(child, trash):
            report.anomalies.append(f"目录与回收站配置重叠,已跳过:{child}")
            continue
        if not _ID_DIR.match(child.name):
            report.anomalies.append(f"缓存目录名不是合法 Workshop ID,已跳过:{child.name}")
            continue
        if int(child.name) > 2**63 - 1:
            report.anomalies.append(f"缓存目录 ID 超出 int64 范围,已跳过:{child.name}")
            continue
        gf, non_gma = _find_gmas(child)
        finds.append(CacheFind(workshop_id=child.name, directory=child, gmas=gf, non_gma=non_gma))
        report.cache_ids.append(child.name)
    return finds


def discover_addons(settings: Settings, report: ScanReport) -> list[AddonsEntry]:
    root = settings.addons_root
    if root is None:
        return []
    if not root.is_dir():
        report.anomalies.append(f"addons 目录不存在或不可访问:{root}")
        return []
    entries: list[AddonsEntry] = []
    parsed = 0
    try:
        children = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError as e:
        report.anomalies.append(f"addons 目录读取失败:{e}")
        return []
    for child in children:
        if child.is_symlink():
            report.anomalies.append(f"addons 下存在符号链接,已跳过:{child.name}")
            continue
        if child.is_file() and child.suffix.lower() == ".gma":
            m = _MANAGED_FILE.match(child.name)
            if m:
                entries.append(AddonsEntry(child.name, child, "gma", True, m.group(1), int(m.group(2)), child.stat().st_size))
                continue
            st = child.stat()
            entries.append(AddonsEntry(child.name, child, "gma", False, None, None, st.st_size))
            if parsed < _MAX_EXTERNAL_PARSE:
                parsed += 1
                try:
                    meta = gma.read_gma_metadata(child)
                    # 提取展示信息:仅当文件名可推断 ID 时才归属,否则仅登记
                    num = re.match(r"^([0-9]{1,20})", child.name)
                    if num and int(num.group(1)) <= 2**63 - 1:
                        for e in entries:
                            if e.path == child:
                                e.workshop_id = num.group(1)
                                break
                except gma.GmaError:
                    pass
        elif child.is_dir():
            m = _MANAGED_DIR.match(child.name)
            if m:
                size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                entries.append(AddonsEntry(child.name, child, "folder", True, m.group(1), None, size))
            else:
                size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                entries.append(AddonsEntry(child.name, child, "folder", False, None, None, size))
    report.addons_entries = entries
    return entries


# ---------- 调和 ----------

def _fingerprint(gmas_found: list[GmaFound]) -> str:
    if not gmas_found:
        return ""
    parts = "|".join(f"{g.path.name}:{int(g.mtime)}:{g.size}" for g in sorted(gmas_found, key=lambda g: g.path.name))
    return parts[:128]


def _trashed_ids(session: Session) -> set[str]:
    rows = session.execute(select(TrashEntry.workshop_id).where(TrashEntry.status == C.TrashStatus.IN_TRASH.value)).scalars()
    return set(rows)


def _collection_ids(session: Session) -> set[str]:
    rows = session.execute(select(CollectionSnapshot)).scalars()
    out: set[str] = set()
    for snap in rows:
        for item in snap.items or []:
            out.add(str(item))
    return out


def _snapshot_files(session: Session, wid: str, primary: GmaFound) -> int:
    """primary GMA 的文件表快照入库;返回写入条数(超上限截断)。"""
    session.execute(delete(ModFile).where(ModFile.workshop_id == wid))
    try:
        meta = gma.read_gma_metadata(primary.path)
    except gma.GmaError:
        return 0
    rows = []
    truncated = False
    for entry in meta.entries:
        if len(rows) >= _MAX_SNAPSHOT_FILES:
            truncated = True
            break
        rows.append(ModFile(workshop_id=wid, rel_path=entry.filename, size=entry.size,
                            mtime=0, note="截断展示" if truncated else ""))
    for r in rows:
        session.add(r)
    return len(rows)


def run_full_scan(session: Session, settings: Settings, deep: bool = True) -> ScanReport:
    """全量扫描:发现缓存/addons → 与数据库调和。

    只写 inventory 相关字段与 load_sources/冲突诊断;
    desired/apply 状态仅在新建记录时初始化为 unmanaged,绝不覆盖用户决定。
    """
    report = ScanReport()
    finds = discover_cache(settings, report)
    addons = discover_addons(settings, report)
    try:
        ids_in_file = parse_ids_file(settings.ids_file) if settings.ids_file else []
        report.ids_in_file = ids_in_file
    except Exception as e:  # IdsFileError 或 IO 错误:如实记录,不中断扫描
        report.ids_file_error = str(e)
    id_set = {f.workshop_id for f in finds}
    addons_by_id: dict[str, list[AddonsEntry]] = {}
    for a in addons:
        if a.workshop_id:
            addons_by_id.setdefault(a.workshop_id, []).append(a)
    coll_ids = _collection_ids(session)
    trash_ids = _trashed_ids(session)
    now = utcnow()

    for find in finds:
        wid = find.workshop_id
        mod = session.get(Mod, wid)
        fp = _fingerprint(find.gmas)
        valid_gmas = [g for g in find.gmas if g.size >= 0]
        if not valid_gmas:
            # 目录存在但没有可用 GMA:存在性异常 → INVALID
            if mod is None:
                mod = Mod(workshop_id=wid, folder_name=find.directory.name)
                session.add(mod)
                report.created.append(wid)
            mod.inventory_state = C.InventoryState.INVALID.value
            detail = dict(mod.inventory_detail or {})
            if find.gmas:
                detail["reason"] = "读取 .gma 文件信息失败"
            elif find.non_gma:
                shown = "、".join(find.non_gma[:3])
                more = "" if len(find.non_gma) <= 3 else f" 等 {len(find.non_gma)} 个"
                detail["reason"] = f"缓存内含 .bin 文件,但内容既非 GMAD 也非 LZMA 压缩的 GMA(可能不是 addon 内容):{shown}{more}"
            else:
                detail["reason"] = "目录存在但未找到 GMA 文件"
            detail["gmas"] = [g.path.name for g in find.gmas]
            mod.inventory_detail = detail
            mod.last_scan_at = now
            report.invalid.append(wid)
            continue

        primary = max(valid_gmas, key=lambda g: (g.size, g.mtime))
        changed = (mod is None or mod.source_fingerprint != fp)
        meta = None
        meta_error = ""
        if changed or deep:
            try:
                meta = gma.read_gma_metadata(primary.path)
            except gma.GmaError as e:
                meta_error = str(e)

        if mod is None:
            mod = Mod(workshop_id=wid, folder_name=find.directory.name)
            session.add(mod)
            report.created.append(wid)
        elif changed:
            report.updated.append(wid)
        else:
            report.unchanged.append(wid)

        # ---- inventory ----
        if meta_error:
            mod.inventory_state = C.InventoryState.INVALID.value
            detail = dict(mod.inventory_detail or {})
            detail["reason"] = f"GMA 解析失败:{meta_error}"
            mod.inventory_detail = detail
            mod.last_scan_at = now
            report.invalid.append(wid)
            continue
        mod.inventory_state = C.InventoryState.PRESENT.value
        mod.missing_since = None
        mod.cache_path = str(primary.path)
        mod.size_bytes = sum(g.size for g in valid_gmas)
        mod.file_count = (len(meta.entries) if meta else mod.file_count)
        mod.cache_mtime = int(primary.mtime)
        mod.source_fingerprint = fp
        mod.last_scan_at = now

        # 本地元数据回退:仅在远程标题为空时写入,不覆盖 Steam 结果
        if meta:
            if meta.title and not (mod.title_remote or "").strip():
                mod.title_local = meta.title[:512]
            if meta.author and not (mod.author_name or "").strip():
                mod.author_name = meta.author[:256]
            if not (mod.description or "").strip() and meta.description:
                mod.description = meta.description

        # ---- load_sources 与冲突诊断 ----
        sources: list[str] = []
        if wid in ids_in_file:
            sources.append(C.LoadSource.NATIVE_IDS.value)
        if any(a.managed and a.workshop_id == wid for a in addons):
            sources.append(C.LoadSource.LOCAL_MANAGED.value)
        external = [a for a in addons_by_id.get(wid, []) if not a.managed]
        if external:
            sources.append(C.LoadSource.EXTERNAL_ADDONS.value)
        if wid in coll_ids:
            sources.append(C.LoadSource.EXTERNAL_COLLECTION.value)
        if not sources:
            sources.append(C.LoadSource.UNMANAGED_CACHE.value)
        mod.load_sources = sources
        mod.load_source = sources[0]

        detail = dict(mod.inventory_detail or {})
        detail["gmas"] = [{"name": g.path.name, "size": g.size} for g in valid_gmas]
        detail["conflicts"] = _conflicts(mod, sources, wid in ids_in_file)
        if meta:
            detail["gma_meta"] = gma.summarize(meta)
            if meta.has_trailer_crc:
                detail.pop("warning", None)
            else:
                detail["warning"] = "GMA 缺少整包尾部 CRC(各条目 CRC 校验通过,内容完整,可正常使用)"
        mod.inventory_detail = detail

        # 部署副本源变更检测(本地受管模式;未 flush 的新对象列为 None,防御取值)
        if (mod.deploy_version or 0) > 0 and mod.deployed_fingerprint and mod.deployed_fingerprint != fp:
            mod.source_changed = True

        if deep or changed:
            _snapshot_files(session, wid, primary)

    # ---- 磁盘消失的已登记 Mod ----
    existing = session.execute(select(Mod)).scalars().all()
    for mod in existing:
        if mod.workshop_id in id_set:
            continue
        if mod.workshop_id in trash_ids:
            if mod.inventory_state != C.InventoryState.TRASHED.value:
                mod.inventory_state = C.InventoryState.TRASHED.value
                mod.last_scan_at = now
                report.updated.append(mod.workshop_id)
            continue
        if mod.inventory_state == C.InventoryState.PRESENT.value:
            mod.inventory_state = C.InventoryState.MISSING.value
            mod.missing_since = mod.missing_since or now
            mod.last_scan_at = now
            report.missing.append(mod.workshop_id)

    # ---- runtime_state:srcds 挂载缓存探针(缺失则保持 unknown) ----
    report.runtime_probe = refresh_runtime_flags(session, settings)
    # ---- 待重启:若运行中实例已晚于最新配置写入,则标记不再成立 ----
    runtime.reconcile_restart_flags(session, settings)
    return report


def _conflicts(mod: Mod, sources: list[str], in_ids: bool) -> list[dict]:
    """把"外部来源可能重新引入"的情况整理为面向用户的冲突提示。"""
    out: list[dict] = []
    if (C.LoadSource.EXTERNAL_ADDONS.value in sources):
        out.append({"kind": "external_addons", "message": "addons 目录存在同名外部条目,非本面板受管"})
    if (C.LoadSource.EXTERNAL_COLLECTION.value in sources):
        out.append({"kind": "external_collection", "message": "该 ID 出现在外部 Workshop 合集中,可能被外部工具重新引入"})
    if in_ids and mod.desired_state == C.DesiredState.DISABLED.value:
        out.append({"kind": "native_ids_mismatch", "message": "该 ID 仍在原生清单文件中,但期望状态为禁用,需应用变更"})
    return out


def refresh_runtime_flags(session: Session, settings: Settings) -> str:
    """用 srcds 挂载缓存探针刷新 runtime_state,返回探针状态描述。

    原设计"没有可靠探针,一律 unknown"(调研文档第 3 节);现接入
    cfg/srcds_addons.txt / cache/srcds_addon_list_cache.txt(srcds 自动写出的
    挂载缓存)作为直接证据:探针存在时产出 loaded/not_loaded,
    探针缺失或不可读时仍保持 unknown,安全语义不变。
    """
    return probe.update_runtime_states(session, settings)
