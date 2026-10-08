"""文件系统安全:Workshop ID 校验、防目录穿越/符号链接逃逸/TOCTOU 的基础检查。"""
from __future__ import annotations

import os
import re
from pathlib import Path, PureWindowsPath

from ..errors import bad_request

_ID_RE = re.compile(r"^[0-9]{1,20}$")
MAX_ID = 2**63 - 1  # Workshop ID 为 int64


def valid_workshop_id(raw: str) -> str:
    """校验并归一化十进制 Workshop ID;ID 在全栈均为字符串。"""
    s = (raw or "").strip()
    if not _ID_RE.match(s):
        raise bad_request(f"非法 Workshop ID:{raw!r}", code="invalid_workshop_id")
    if int(s) > MAX_ID:
        raise bad_request(f"Workshop ID 超出取值范围:{raw!r}", code="invalid_workshop_id")
    return s


def valid_workshop_ids(raw_list) -> list[str]:
    out = []
    for r in raw_list:
        out.append(valid_workshop_id(str(r)))
    if len(set(out)) != len(out):
        raise bad_request("ID 列表存在重复", code="duplicate_ids")
    return out


def check_component(name: str) -> str:
    """校验单级路径组件:拒绝分隔符、..、NUL、盘符与绝对路径形态。"""
    if not name or name in (".", ".."):
        raise bad_request(f"非法路径组件:{name!r}", code="unsafe_path")
    if "\x00" in name:
        raise bad_request("路径包含 NUL 字节", code="unsafe_path")
    if "/" in name or "\\" in name or ":" in name:
        raise bad_request(f"路径组件包含分隔符或盘符:{name!r}", code="unsafe_path")
    if PureWindowsPath(name).is_absolute() or os.path.isabs(name):
        raise bad_request("不允许绝对路径", code="unsafe_path")
    return name


def _norm(p: Path) -> str:
    # 大小写不敏感文件系统兼容;realpath 不展开不存在的部分但仍规范化
    try:
        r = os.path.realpath(str(p))
    except OSError:
        r = str(p.absolute())
    return os.path.normcase(os.path.normpath(r))


def ensure_within(root: Path, child: Path) -> Path:
    """确认 child 位于 root 内(展开符号链接后仍不越界)。返回规范化 child。"""
    root_real = _norm(root)
    child_real = _norm(child)
    if child_real == root_real:
        raise bad_request("路径不能等于根目录", code="unsafe_path")
    if not child_real.startswith(root_real + os.sep):
        raise bad_request(f"路径越界:{child}", code="path_escape")
    return child


def safe_child(root: Path, *components: str) -> Path:
    """逐组件校验后拼接,并做整体越界检查(含符号链接解析)。"""
    cur = Path(root)
    for c in components:
        cur = cur / check_component(c)
    return ensure_within(Path(root), cur)


def no_symlink_components(root: Path, relative: Path) -> None:
    """检查 root 下相对路径的每一级都不是符号链接(不跟随未知链接)。"""
    cur = Path(root)
    for part in relative.parts:
        cur = cur / part
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            return  # 不存在的部分无需检查
        if os.path.stat.S_ISLNK(st.st_mode) if hasattr(os.path, "stat") else cur.is_symlink():
            raise bad_request(f"路径包含符号链接:{cur}", code="symlink_escape")


def is_symlink(p: Path) -> bool:
    try:
        return os.path.islink(p)
    except OSError:
        return False


def gma_rel_path_safe(rel: str) -> str:
    """校验 GMA 包内条目路径(用于解包):拒绝绝对路径、穿越、盘符、NUL、过深层级。"""
    rel = (rel or "").replace("\\", "/")
    if not rel or rel.startswith("/") or ":" in rel or "\x00" in rel:
        raise bad_request(f"GMA 内非法路径:{rel!r}", code="unsafe_gma_entry")
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise bad_request(f"GMA 内非法路径:{rel!r}", code="unsafe_gma_entry")
    if len(parts) > 32 or sum(len(p) for p in parts) > 400:
        raise bad_request(f"GMA 内路径过深或过长:{rel!r}", code="unsafe_gma_entry")
    return "/".join(parts)


def detect_dir_nesting(a: Path, b: Path) -> bool:
    """两路径是否存在嵌套关系(用于回收站与活动目录互斥校验)。"""
    na, nb = _norm(a), _norm(b)
    return na == nb or na.startswith(nb + os.sep) or nb.startswith(na + os.sep)
