"""三种管理模式的真实加载适配器。

职责:把"期望状态"落成游戏服务器上的真实变化。
- observe:       只读观察,拒绝一切写操作
- native_ids:    写 cfg/srcds_workshop_ids.txt(GMod 2026.09.22+)
- local_managed: 在 addons/ 维护受管副本(gma_copy 复制 / folder_extract 解包)

硬性边界(来自需求文档与调研):
- 本适配器绝不杀进程、绝不自动重启;requires_restart 只是标记,
  重启由 SERVER_CONTROL_MODE(manual=提示管理员 / systemd=独立 API 显式触发)处理。
- 全部文件写入走原子操作;受管命名 gmm_<ID>_v<N>.gma / gmm_<ID>/。
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

from .. import constants as C
from ..config import Settings
from ..errors import ApiError, forbidden, not_found, unprocessable
from ..models.entities import Mod, utcnow
from ..services import gma
from ..services.fsops import cleanup_tmp_files, copy_item, fsync_dir, move_item
from ..services.idsfile import IdsFileError, build_ids_text, parse_ids_file, write_ids_file
from ..services.paths import safe_child

_MANAGED_FILE_RE = re.compile(r"^gmm_([0-9]{1,20})_v([0-9]+)\.gma$", re.IGNORECASE)
_MANAGED_DIR_RE = re.compile(r"^gmm_([0-9]{1,20})$", re.IGNORECASE)


class AdapterContext:
    def __init__(self, session, settings: Settings, actor: str = "system"):
        self.session = session
        self.settings = settings
        self.actor = actor


def get_adapter(ctx: AdapterContext):
    mode = ctx.settings.management_mode
    if mode == "observe":
        return ObserveAdapter(ctx)
    if mode == "native_ids":
        return NativeIdsAdapter(ctx)
    if mode == "local_managed":
        return LocalManagedAdapter(ctx)
    raise ApiError(500, "bad_mode", f"未知管理模式:{mode}")


def _get_mod_or_404(session, wid: str) -> Mod:
    mod = session.get(Mod, wid)
    if mod is None:
        raise not_found(f"Mod {wid} 未登记,请先执行扫描")
    return mod


def _primary_gma(settings: Settings, mod: Mod) -> Path:
    if not mod.cache_path:
        raise unprocessable(f"Mod {mod.workshop_id} 没有可用的本地 GMA 记录", code="no_local_gma")
    p = Path(mod.cache_path)
    if not p.is_file():
        raise unprocessable(f"本地 GMA 文件不存在:{p}", code="cache_missing")
    return p


class BaseAdapter:
    mode = ""

    def __init__(self, ctx: AdapterContext):
        self.ctx = ctx
        self.settings = ctx.settings
        self.session = ctx.session

    # ---- 预检:返回 warnings 列表,抛 ApiError 表示阻止 ----
    def check(self, action: str, wid: str) -> list[dict]:
        mod = _get_mod_or_404(self.session, wid)
        warns: list[dict] = []
        if action == C.ModAction.DELETE.value and mod.protected:
            raise unprocessable(f"Mod {wid} 受保护,禁止删除:{mod.protected_reason or '未说明原因'}",
                                code="protected")
        if action == C.ModAction.ENABLE.value and mod.inventory_state != C.InventoryState.PRESENT.value:
            raise unprocessable(f"Mod {wid} 当前状态为 {mod.inventory_state},无法启用", code="not_present")
        for s in mod.load_sources or []:
            if s in (C.LoadSource.EXTERNAL_ADDONS.value, C.LoadSource.EXTERNAL_COLLECTION.value):
                warns.append({"kind": "external_source", "message": f"该 ID 存在外部来源({s}),变更后可能被外部工具覆盖"})
        if (mod.inventory_detail or {}).get("conflicts"):
            warns.append({"kind": "conflict", "message": "存在未解决冲突,详见详情页"})
        return warns

    # ---- 单项应用;成功返回 result dict,失败抛 ApiError ----
    def apply(self, action: str, wid: str, params: dict) -> dict:
        raise NotImplementedError

    # ---- 应用后统一回写 ----
    def _post_apply(self, mod: Mod, action: str, result: dict) -> None:
        if action == C.ModAction.ENABLE.value:
            mod.desired_state = C.DesiredState.ENABLED.value
            mod.apply_state = C.ApplyState.SYNCED.value
        elif action == C.ModAction.DISABLE.value:
            mod.desired_state = C.DesiredState.DISABLED.value
            mod.apply_state = C.ApplyState.SYNCED.value
        mod.requires_restart = True  # 任何影响加载入口的变更都需要重启才对运行中实例生效
        mod.apply_error = ""
        mod.updated_at = utcnow()
        self.session.add(mod)

    def _post_failed(self, mod: Mod, err: str) -> None:
        mod.apply_state = C.ApplyState.FAILED.value
        mod.apply_error = err[:1024]
        self.session.add(mod)


class ObserveAdapter(BaseAdapter):
    """观察模式:生成预览可以,应用一律拒绝。"""
    mode = "observe"

    def apply(self, action: str, wid: str, params: dict) -> dict:
        raise forbidden(
            "当前为观察模式(OBSERVE),只能查看不能变更;请先在设置中切换管理模式",
            code="observe_readonly",
        )


class NativeIdsAdapter(BaseAdapter):
    """原生 Workshop ID 清单模式:整个文件一次原子写入。"""
    mode = "native_ids"

    def _require_ids_file(self) -> Path:
        f = self.settings.ids_file
        if f is None:
            raise ApiError(400, "ids_file_unconfigured",
                           "未配置 WORKSHOP_IDS_FILE(cfg/srcds_workshop_ids.txt 路径),无法使用原生清单模式")
        return f

    def check(self, action: str, wid: str) -> list[dict]:
        warns = super().check(action, wid)
        self._require_ids_file()
        warns.append({"kind": "version", "message": "原生清单需要 GMod 服务端 2026.09.22+ 构建,请确认服务器版本"})
        return warns

    def _read_ids(self) -> list[str]:
        try:
            return parse_ids_file(self._require_ids_file())
        except IdsFileError as e:
            raise ApiError(409, "ids_file_invalid", f"清单文件解析失败,已阻止自动覆盖,请人工检查:{e}")

    def apply(self, action: str, wid: str, params: dict) -> dict:
        ids = self._read_ids()
        before = list(ids)
        if action == C.ModAction.ENABLE.value:
            if wid not in ids:
                ids.append(wid)
        elif action in (C.ModAction.DISABLE.value, C.ModAction.DELETE.value):
            ids = [x for x in ids if x != wid]
        if ids == before:
            return {"changed": False, "note": "清单中无变化"}
        try:
            write_ids_file(self._require_ids_file(), ids)
        except IdsFileError as e:
            raise ApiError(500, "ids_file_write_failed", f"写入清单失败:{e}")
        return {"changed": True, "count": len(ids)}

    def current_count(self) -> int:
        try:
            return len(self._read_ids())
        except ApiError:
            return -1


class LocalManagedAdapter(BaseAdapter):
    """本地受管加载模式:在 addons/ 下维护 gmm_ 前缀的受管副本。"""
    mode = "local_managed"

    def _require_addons(self) -> Path:
        root = self.settings.addons_root
        if root is None:
            raise ApiError(400, "addons_unconfigured",
                           "未配置 GMOD_ADDONS_ROOT,无法使用本地受管模式")
        if not root.is_dir():
            raise ApiError(400, "addons_missing", f"addons 目录不存在:{root}")
        return root

    # ---- 受管副本管理 ----
    def _managed_paths(self, addons: Path, wid: str) -> list[Path]:
        out = []
        for p in addons.iterdir():
            m = _MANAGED_FILE_RE.match(p.name) or _MANAGED_DIR_RE.match(p.name)
            if m and m.group(1) == wid:
                out.append(p)
        return sorted(out, key=lambda p: p.name)

    def _remove_managed(self, addons: Path, wid: str) -> int:
        n = 0
        for p in self._managed_paths(addons, wid):
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
            n += 1
        if n:
            fsync_dir(addons)
        return n

    def apply(self, action: str, wid: str, params: dict) -> dict:
        addons = self._require_addons()
        mod = _get_mod_or_404(self.session, wid)

        if action == C.ModAction.ENABLE.value:
            return self._deploy(addons, mod)
        if action == C.ModAction.DISABLE.value:
            removed = self._remove_managed(addons, wid)
            return {"changed": removed > 0, "removed_copies": removed}
        if action == C.ModAction.DELETE.value:
            removed = self._remove_managed(addons, wid)
            return {"changed": True, "removed_copies": removed, "note": "缓存目录由回收站流程处理"}
        raise ApiError(400, "bad_action", f"未知动作:{action}")

    def _deploy(self, addons: Path, mod: Mod) -> dict:
        src = _primary_gma(self.settings, mod)
        # 先核验源包结构完好(读表便宜)
        try:
            meta = gma.read_gma_metadata(src)
        except gma.GmaError as e:
            raise unprocessable(f"源 GMA 解析失败,已取消部署:{e}", code="gma_invalid")
        strategy = self.settings.local_managed_strategy
        wid = mod.workshop_id
        new_version = (mod.deploy_version or 0) + 1
        # 清掉旧副本,避免多版本并存
        self._remove_managed(addons, wid)
        if strategy == "gma_copy":
            name = f"gmm_{wid}_v{new_version}.gma"
            dst = copy_item(src, addons, name)
            deploy_path, deploy_size, files = str(dst), dst.stat().st_size, len(meta.entries)
        else:
            # folder_extract:解包到 addons 下临时目录,完成后原子改名
            tmp = addons / f".gmm-extract-{uuid.uuid4().hex[:12]}"
            try:
                stats = gma.extract_gma(src, tmp)
                dst = addons / f"gmm_{wid}"
                if dst.exists():
                    shutil.rmtree(dst)
                os.rename(tmp, dst)
                fsync_dir(addons)
            finally:
                if tmp.exists():
                    shutil.rmtree(tmp, ignore_errors=True)
            deploy_path, deploy_size, files = str(dst), stats["bytes"], stats["files"]
        mod.deploy_version = new_version
        mod.deploy_path = deploy_path
        mod.deploy_size = deploy_size
        mod.deployed_fingerprint = mod.source_fingerprint
        mod.deployed_at = utcnow()
        mod.source_changed = False
        return {"changed": True, "strategy": strategy, "version": new_version,
                "path": deploy_path, "files": files, "size": deploy_size}

    # ---- 崩溃恢复:受管副本与数据库互核 ----
    def verify_actual(self, mod: Mod) -> str:
        """返回 'deployed' | 'absent' | 'unknown'(副本存在但指纹对不上)。"""
        addons = self.settings.addons_root
        if addons is None or not addons.is_dir():
            return "absent"
        paths = self._managed_paths(addons, mod.workshop_id)
        if not paths:
            return "absent"
        if mod.deployed_fingerprint and mod.source_fingerprint == mod.deployed_fingerprint:
            return "deployed"
        return "unknown"


def cleanup_work_dirs(settings: Settings) -> int:
    """启动时清理受管目录与回收站的暂存残留。"""
    n = 0
    for d in (settings.addons_root, settings.trash_path, settings.cache_root):
        if d is not None and d.is_dir():
            n += cleanup_tmp_files(d)
    return n
