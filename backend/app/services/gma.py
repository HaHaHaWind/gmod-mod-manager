"""GMA 包解析器(纯 Python,只读)。

格式依据 docs/gmod-loading-research.md 第 1 节(Valve gmad 官方仓库):
    magic "GMAD" | u8 version(=3,拒绝>3) | u64 steamid | u64 timestamp
    [v≥2: required content 字符串列表(空串结束)]
    title / description / author(均为 NUL 结尾字符串)
    i32 addon_version
    文件表:(u32 文件号; ≠0 时跟 NUL 路径 + i64 size + u32 crc32)直到文件号=0
    文件数据:按文件表顺序连续存放,无显式偏移
    尾部 u32:整个文件的 CRC32(v3)

防御性设计:所有长度/条目数有上限;size 必须非负且不越界;包内路径解包前经
`paths.gma_rel_path_safe` 校验。本模块不信任任何输入文件。
"""
from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from .paths import gma_rel_path_safe

MAGIC = b"GMAD"
SUPPORTED_VERSION = 3

_HEADER = struct.Struct("<4sBQQ")        # magic, version, steamid, timestamp
_I32 = struct.Struct("<i")
_U32 = struct.Struct("<I")
_I64 = struct.Struct("<q")

MAX_STRING_BYTES = 64 * 1024             # 单个元数据字符串上限(描述可能较长)
MAX_ENTRIES = 200_000                    # 文件表条目上限
MAX_META_BYTES = 32 * 1024 * 1024        # 头部+文件表总量上限(防解压炸弹式膨胀)
CHUNK = 256 * 1024


class GmaError(Exception):
    """GMA 结构损坏或不受支持。中文消息可直接展示给用户。"""


@dataclass
class GmaEntry:
    filename: str
    size: int
    crc32: int


@dataclass
class GmaMetadata:
    version: int
    steamid: int
    timestamp: int
    required_content: list[str]
    title: str
    description: str
    author: str
    addon_version: int
    entries: list[GmaEntry] = field(default_factory=list)
    total_size: int = 0        # 文件数据总字节数
    body_end: int = 0          # 文件数据结束后应紧邻尾部 CRC 的偏移
    file_size: int = 0         # GMA 文件实际大小
    crc_ok: bool | None = None  # None=未校验


def _read_cstring(fh, limit: int = MAX_STRING_BYTES) -> str:
    """读取一个 NUL 结尾字符串;超长视为损坏。"""
    buf = bytearray()
    while True:
        b = fh.read(1)
        if not b:
            raise GmaError("文件在字符串读取中意外结束(文件被截断)")
        if b == b"\x00":
            break
        buf += b
        if len(buf) > limit:
            raise GmaError(f"元数据字符串超过 {limit} 字节上限,疑似损坏文件")
    try:
        return buf.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - decode(errors=replace) 不会抛
        raise GmaError("元数据字符串解码失败")


def read_gma_metadata(path: Path, verify_crc: bool = False) -> GmaMetadata:
    """只读取头部与文件表,不读取文件数据块。结构损坏抛 GmaError。"""
    file_size = path.stat().st_size
    if file_size < _HEADER.size + 5:
        raise GmaError("文件过小,不是有效的 GMA 包")
    try:
        with open(path, "rb") as fh:
            magic, version, steamid, ts = _HEADER.unpack(fh.read(_HEADER.size))
            if magic != MAGIC:
                raise GmaError("魔数不符:不是 GMA 包")
            if version > SUPPORTED_VERSION:
                raise GmaError(f"GMA 版本 {version} 高于本面板支持的版本 {SUPPORTED_VERSION},已拒绝")
            required: list[str] = []
            if version >= 2:
                while True:
                    s = _read_cstring(fh)
                    if s == "":
                        break
                    required.append(s)
                    if len(required) > 1024:
                        raise GmaError("必需内容列表过长,疑似损坏")
            title = _read_cstring(fh)
            desc = _read_cstring(fh)
            author = _read_cstring(fh)
            (addon_version,) = _I32.unpack(fh.read(_I32.size))

            entries: list[GmaEntry] = []
            total = 0
            while True:
                raw = fh.read(_U32.size)
                if len(raw) < _U32.size:
                    raise GmaError("文件表意外结束(文件被截断)")
                (num,) = _U32.unpack(raw)
                if num == 0:
                    break
                if num != len(entries) + 1:
                    raise GmaError(f"文件表序号异常:期望 {len(entries) + 1},实际 {num}")
                if len(entries) >= MAX_ENTRIES:
                    raise GmaError(f"文件表条目超过 {MAX_ENTRIES} 上限,疑似损坏")
                name = _read_cstring(fh)
                raw = fh.read(_I64.size + _U32.size)
                if len(raw) < _I64.size + _U32.size:
                    raise GmaError("文件表条目数据不完整")
                size, crc = struct.unpack("<qI", raw)
                if size < 0:
                    raise GmaError(f"条目 {name!r} 大小为负,文件损坏")
                total += size
                if total > file_size:
                    raise GmaError("文件数据总量超过文件实际大小,文件被截断或损坏")
                entries.append(GmaEntry(filename=name, size=size, crc32=crc))

            body_end = fh.tell()
            # 数据区之后必须还有完整尾部 CRC(4 字节),否则文件被截断
            if file_size < body_end + total + _U32.size:
                raise GmaError("文件长度不足(数据区或尾部 CRC 缺失),文件被截断")
            meta = GmaMetadata(
                version=version, steamid=steamid, timestamp=ts,
                required_content=required, title=title, description=desc,
                author=author, addon_version=addon_version, entries=entries,
                total_size=total, body_end=body_end, file_size=file_size,
            )
            if verify_crc:
                meta.crc_ok = verify_gma_crc(path)
            return meta
    except OSError as e:
        raise GmaError(f"读取 GMA 文件失败:{e}") from e


def verify_gma_crc(path: Path) -> bool:
    """流式校验整个文件的 CRC32(尾部 u32)。O(文件大小),由用户显式触发。"""
    running = 0
    remaining = path.stat().st_size
    if remaining < 4:
        return False
    with open(path, "rb") as fh:
        while remaining > 4:
            chunk = fh.read(min(CHUNK, remaining - 4))
            if not chunk:
                return False
            running = zlib.crc32(chunk, running)
            remaining -= len(chunk)
        stored_raw = fh.read(4)
    if len(stored_raw) < 4:
        return False
    (stored,) = _U32.unpack(stored_raw)
    return (stored & 0xFFFFFFFF) == (running & 0xFFFFFFFF)


def iter_gma_payloads(path: Path):
    """顺序产出 (GmaEntry, bytes)。仅用于解包/预览小文件,不应整包载入内存。"""
    meta = read_gma_metadata(path)
    with open(path, "rb") as fh:
        fh.seek(meta.body_end)  # 数据区紧跟文件表之后
        for entry in meta.entries:
            remaining = entry.size
            parts: list[bytes] = []
            while remaining > 0:
                chunk = fh.read(min(CHUNK, remaining))
                if not chunk:
                    raise GmaError(f"条目 {entry.filename!r} 数据不完整,文件被截断")
                parts.append(chunk)
                remaining -= len(chunk)
            yield entry, b"".join(parts)


def extract_gma(path: Path, dest_dir: Path, on_progress=None) -> dict:
    """解包到 dest_dir(调用方负责先落到临时目录再原子替换)。

    每个条目路径经 `gma_rel_path_safe` 校验,拒绝绝对路径与目录穿越。
    返回 {files, bytes} 统计。on_progress(done, total) 可选回调。
    """
    meta = read_gma_metadata(path)
    dest_dir = Path(dest_dir)
    files = 0
    total_bytes = 0
    with open(path, "rb") as fh:
        fh.seek(meta.body_end)  # 数据区紧跟文件表之后
        for idx, entry in enumerate(meta.entries):
            safe_rel = gma_rel_path_safe(entry.filename)
            target = dest_dir.joinpath(*safe_rel.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with open(target, "wb") as out:
                remaining = entry.size
                while remaining > 0:
                    chunk = fh.read(min(CHUNK, remaining))
                    if not chunk:
                        raise GmaError(f"条目 {entry.filename!r} 数据不完整,文件被截断")
                    out.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            # 条目级 CRC 校验(便宜,值得做)
            with open(target, "rb") as check:
                local = 0
                while True:
                    b = check.read(CHUNK)
                    if not b:
                        break
                    local = zlib.crc32(b, local)
            if entry.crc32 and (local & 0xFFFFFFFF) != (entry.crc32 & 0xFFFFFFFF):
                raise GmaError(f"条目 {entry.filename!r} CRC 校验失败,缓存文件疑似损坏")
            files += 1
            total_bytes += written
            if on_progress:
                on_progress(idx + 1, len(meta.entries))
    # 尽力 fsync 目录;Windows 上可能不支持,忽略失败
    try:
        fd = os.open(dest_dir, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass
    return {"files": files, "bytes": total_bytes, "entries_declared": len(meta.entries)}


def summarize(meta: GmaMetadata) -> dict:
    """转成可存 JSON 的诊断摘要。"""
    return {
        "version": meta.version,
        "addon_version": meta.addon_version,
        "title": meta.title,
        "author": meta.author,
        "required_content": meta.required_content,
        "entries": len(meta.entries),
        "total_size": meta.total_size,
        "crc_ok": meta.crc_ok,
    }
