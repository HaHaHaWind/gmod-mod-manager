"""cfg/srcds_workshop_ids.txt 的解析与生成(GMod 2026.09.22+ 原生 Workshop 清单)。

格式为 KeyValues 子集(GMod 官方 Wiki 示例):
    "my_workshop_addons"
    {
        "1"
        {
            "wsid"    "123277559"
        }
    }

解析器刻意只支持本文件需要的子集:引号/裸 token、块、// 注释、\" 转义。
解析失败抛 IdsFileError,**绝不**覆盖原文件(防止把可修复的解析错误变成数据丢失)。
"""
from __future__ import annotations

import re
from pathlib import Path

from ..errors import ApiError
from ..services.fsops import atomic_write_bytes
from ..services.paths import valid_workshop_id

ROOT_NAME = "my_workshop_addons"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_IDS = 5000


class IdsFileError(Exception):
    """清单文件解析或写入失败。"""


# ---------- 解析 ----------

def _tokenize(text: str) -> list[str]:
    """产出 token:带引号字符串(保留转义)、{、}、裸词。剔除 // 注释。"""
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif c == "{":
            tokens.append("{")
            i += 1
        elif c == "}":
            tokens.append("}")
            i += 1
        elif c == '"':
            buf = []
            i += 1
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append('"' if nxt == '"' else {"n": "\n", "t": "\t"}.get(nxt, nxt))
                    i += 2
                elif ch == '"':
                    break
                else:
                    buf.append(ch)
                    i += 1
            else:
                raise IdsFileError("字符串未闭合(缺少结尾引号)")
            tokens.append('"' + "".join(buf))
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{}":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _parse_block(tokens: list[str], pos: int, depth: int) -> tuple[dict, int]:
    """解析 `{ key value ... }`,返回 (映射, 新位置)。值可为块(存 dict)或字符串。"""
    node: dict = {}
    if pos >= len(tokens) or tokens[pos] != "{":
        raise IdsFileError("期望 '{' 开启块")
    pos += 1
    while True:
        if pos >= len(tokens):
            raise IdsFileError("块未闭合(缺少 '}')")
        tok = tokens[pos]
        if tok == "}":
            return node, pos + 1
        key = tok.lstrip('"')
        pos += 1
        if pos >= len(tokens):
            raise IdsFileError(f"键 {key!r} 缺少值")
        val = tokens[pos]
        if val == "{":
            if depth > 4:
                raise IdsFileError("嵌套过深,不是预期的清单结构")
            sub, pos = _parse_block(tokens, pos, depth + 1)
            node[key] = sub
        else:
            node[key] = val.lstrip('"')
            pos += 1
        if len(node) > MAX_IDS:
            raise IdsFileError(f"条目超过 {MAX_IDS} 上限")


def parse_ids_text(text: str) -> list[str]:
    """解析为去重后的十进制 ID 列表(保持出现顺序)。非法结构/ID 抛 IdsFileError。"""
    tokens = _tokenize(text)
    if not tokens:
        return []
    root_name = tokens[0].lstrip('"')
    node, _ = _parse_block(tokens, 1, 0)
    if root_name != ROOT_NAME:
        # 官方示例根名为 my_workshop_addons;其余根名不拒绝,但按同样结构处理
        pass
    ids: list[str] = []
    seen: set[str] = set()
    for key, value in node.items():
        if isinstance(value, dict):
            wsid = value.get("wsid", "")
            if not isinstance(wsid, str) or not wsid:
                raise IdsFileError(f"条目 {key!r} 缺少 wsid 值")
        else:
            wsid = value  # 容错:极简写法 "1" "123456"
        wsid = wsid.strip()
        if not re.fullmatch(r"[0-9]{1,20}", wsid):
            raise IdsFileError(f"条目 {key!r} 的 wsid 不是合法十进制 ID:{wsid!r}")
        if int(wsid) > 2**63 - 1:
            raise IdsFileError(f"条目 {key!r} 的 wsid 超出 int64 范围:{wsid!r}")
        if wsid not in seen:
            seen.add(wsid)
            ids.append(wsid)
    return ids


def parse_ids_file(path: Path) -> list[str]:
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return []
    except OSError as e:
        raise IdsFileError(f"读取清单文件失败:{e}") from e
    if len(raw) > MAX_FILE_BYTES:
        raise IdsFileError(f"清单文件超过 {MAX_FILE_BYTES} 字节,疑似异常")
    return parse_ids_text(raw.decode("utf-8", errors="replace"))


# ---------- 生成 ----------

def build_ids_text(ids: list[str]) -> str:
    """确定性输出:按 ID 数值升序,序号 1..n。"""
    ordered = sorted({valid_workshop_id(x) for x in ids}, key=int)
    if len(ordered) > MAX_IDS:
        raise IdsFileError(f"条目数 {len(ordered)} 超过上限 {MAX_IDS}")
    lines = [f'"{ROOT_NAME}"', "{"]
    for i, wid in enumerate(ordered, 1):
        lines.append(f'    "{i}"')
        lines.append("    {")
        lines.append(f'        "wsid"    "{wid}"')
        lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def write_ids_file(path: Path, ids: list[str]) -> None:
    """原子写入清单(同目录临时文件 + fsync + replace + 备份轮换)。"""
    path = Path(path)
    if not path.parent.exists():
        raise IdsFileError(f"清单文件目录不存在:{path.parent}")
    content = build_ids_text(ids).encode("utf-8")
    atomic_write_bytes(path, content)
