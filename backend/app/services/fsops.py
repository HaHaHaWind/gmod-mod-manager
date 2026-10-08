"""文件操作原语:原子写入、同文件系统重命名、跨文件系统暂存复制-校验-原子提交。
目标:崩溃后不留半截配置;跨盘移动可恢复;不覆盖已有内容除非显式允许。"""
from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

from ..errors import conflict
from .paths import ensure_within, is_symlink


def fsync_dir(p: Path) -> None:
    try:
        fd = os.open(str(p), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass  # Windows 上对目录 fsync 可能不支持


def same_fs(a: Path, b: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def atomic_write_bytes(target: Path, data: bytes, keep_backup: bool = True,
                       mode: int | None = None) -> Path | None:
    """原子写入:同目录临时文件 + fsync + os.replace;保留 .gmm-backup-* 备份与权限。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    old_mode = None
    old_uid = old_gid = -1
    if target.exists():
        st = os.stat(target)
        old_mode = st.st_mode & 0o777
        old_uid, old_gid = st.st_uid, st.st_gid
    tmp = target.parent / f".{target.name}.gmm-tmp-{uuid.uuid4().hex[:12]}"
    bak: Path | None = None
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if old_mode is not None:
            os.chmod(tmp, old_mode)
        elif mode is not None:
            os.chmod(tmp, mode)
        if keep_backup and target.exists():
            bak = target.parent / f"{target.name}.gmm-backup-{int(time.time())}"
            os.replace(target, bak)
            # 保留最近 5 份备份
            _prune_backups(target.parent, target.name, keep=5)
        os.replace(tmp, target)
        if hasattr(os, "chown") and old_uid >= 0:
            try:
                os.chown(target, old_uid, old_gid)
            except (OSError, PermissionError):
                pass
        fsync_dir(target.parent)
        return bak
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _prune_backups(directory: Path, name: str, keep: int = 5) -> None:
    baks = sorted(directory.glob(f"{name}.gmm-backup-*"))
    for old in baks[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def move_item(src: Path, dst_dir: Path, new_name: str | None = None,
              overwrite: bool = False) -> Path:
    """移动文件/目录。同文件系统原子重命名;跨文件系统走暂存复制+校验+原子提交+清理。
    不跟随符号链接;目标存在且未允许覆盖时抛 409。"""
    if is_symlink(src):
        raise conflict(f"源路径是符号链接,拒绝操作:{src}", code="symlink_source")
    ensure_within(dst_dir, dst_dir / (new_name or "x")).parent.mkdir(parents=True, exist_ok=True)
    name = new_name or src.name
    dst = dst_dir / name
    if dst.exists() or dst.is_symlink():
        if not overwrite:
            raise conflict(f"目标已存在,拒绝覆盖:{dst}", code="target_exists")
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst_dir.mkdir(parents=True, exist_ok=True)
    if same_fs(src, dst_dir):
        os.rename(src, dst)
        return dst
    # 跨文件系统:暂存复制
    tmp = dst_dir / f".gmm-move-{uuid.uuid4().hex[:12]}"
    try:
        if src.is_dir():
            shutil.copytree(src, tmp, symlinks=False)
        else:
            shutil.copy2(src, tmp, follow_symlinks=False)
        _verify_copy(src, tmp)
        # 到达此处时 dst 必然不存在(存在性检查已在函数开头完成)
        os.rename(tmp, dst)
        fsync_dir(dst_dir)
        if src.is_dir():
            shutil.rmtree(src)
        else:
            src.unlink()
        fsync_dir(src.parent)
        return dst
    finally:
        if tmp.exists():
            if tmp.is_dir():
                shutil.rmtree(tmp, ignore_errors=True)
            else:
                try:
                    tmp.unlink()
                except OSError:
                    pass


def copy_item(src: Path, dst_dir: Path, new_name: str) -> Path:
    """复制文件/目录到 dst_dir(不覆盖已存在目标)。"""
    dst = dst_dir / new_name
    if dst.exists() or dst.is_symlink():
        raise conflict(f"目标已存在,拒绝覆盖:{dst}", code="target_exists")
    dst_dir.mkdir(parents=True, exist_ok=True)
    tmp = dst_dir / f".gmm-copy-{uuid.uuid4().hex[:12]}"
    try:
        if src.is_dir():
            shutil.copytree(src, tmp, symlinks=False)
        else:
            shutil.copy2(src, tmp, follow_symlinks=False)
        _verify_copy(src, tmp)
        os.rename(tmp, dst)
        fsync_dir(dst_dir)
        return dst
    finally:
        if tmp.exists():
            if tmp.is_dir():
                shutil.rmtree(tmp, ignore_errors=True)
            else:
                try:
                    tmp.unlink()
                except OSError:
                    pass


def _verify_copy(src: Path, tmp: Path) -> None:
    if src.is_dir():
        src_files = [p for p in src.rglob("*") if p.is_file() and not p.is_symlink()]
        dst_files = [p for p in tmp.rglob("*") if p.is_file()]
        if len(src_files) != len(dst_files):
            raise conflict("复制校验失败:文件数量不一致", code="copy_verify_failed")
        if sum(p.stat().st_size for p in src_files) != sum(p.stat().st_size for p in dst_files):
            raise conflict("复制校验失败:总大小不一致", code="copy_verify_failed")
    else:
        if os.path.getsize(tmp) != os.path.getsize(src):
            raise conflict("复制校验失败:大小不一致", code="copy_verify_failed")


def check_free_space(target_dir: Path, needed: int) -> None:
    try:
        free = shutil.disk_usage(str(target_dir)).free
    except OSError:
        return
    if free < needed:
        from ..errors import ApiError
        raise ApiError(507, "insufficient_space",
                       f"磁盘空间不足:需要约 {needed} 字节,仅剩 {free} 字节")


def cleanup_tmp_files(directory: Path) -> int:
    """清理中断遗留的暂存文件(.gmm-tmp-*/.gmm-move-*/.gmm-copy-*)。"""
    n = 0
    if not directory.exists():
        return 0
    for p in directory.iterdir():
        if p.name.startswith(".gmm-") and (".gmm-tmp-" in p.name or ".gmm-move-" in p.name or ".gmm-copy-" in p.name):
            try:
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                n += 1
            except OSError:
                pass
    return n
