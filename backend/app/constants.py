"""状态模型常量。五个维度相互独立,严禁用单一布尔值代替(详见 docs/architecture.md)。"""
from __future__ import annotations

from enum import Enum


class InventoryState(str, Enum):
    PRESENT = "present"      # 本地缓存存在且可用
    MISSING = "missing"      # 曾登记但本次扫描未找到(不等于删除)
    INVALID = "invalid"      # 存在文件但损坏/不支持
    TRASHED = "trashed"      # 已移入回收站


class DesiredState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNMANAGED = "unmanaged"  # 未接管,仅观察


class ApplyState(str, Enum):
    SYNCED = "synced"          # 配置/部署与期望一致(仍需重启才能影响运行中的游戏)
    PENDING = "pending"        # 有待应用变更
    APPLYING = "applying"
    FAILED = "failed"
    CONFLICT = "conflict"      # 外部来源可能重新引入/外部改动未解决
    UNMANAGED = "unmanaged"


class RuntimeState(str, Enum):
    """探针(srcds 挂载缓存,如 cfg/srcds_addons.txt)可用时才产出 loaded/not_loaded;
    探针缺失/不可读时必须保持 unknown:过期日志、进程存在、数据库状态
    都不构成"当前 GMod 实例已加载"的证据。"""

    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    UNKNOWN = "unknown"


class PlanStatus(str, Enum):
    DRAFT = "draft"                  # 预览生成,未提交
    STAGED = "staged"                # 已提交,期望状态已更新,等待应用
    APPLYING = "applying"
    APPLIED = "applied"              # 配置已应用,待重启验证
    FAILED = "failed"
    CANCELLED = "cancelled"
    RECOVERY_REQUIRED = "recovery_required"


class PlanItemStatus(str, Enum):
    PENDING = "pending"
    STAGED = "staged"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"      # 后台重启时仍在执行


class ModAction(str, Enum):
    ENABLE = "enable"
    DISABLE = "disable"
    DELETE = "delete"


class TrashStatus(str, Enum):
    IN_TRASH = "in_trash"
    RESTORED = "restored"
    PURGED = "purged"


class ExclusionReason(str, Enum):
    DELETED = "deleted"
    DISABLED = "disabled"


class LoadSource(str, Enum):
    UNMANAGED_CACHE = "unmanaged_cache"   # 缓存目录存在,但不在任何受管加载入口
    NATIVE_IDS = "native_ids"             # 受管 srcds_workshop_ids.txt
    LOCAL_MANAGED = "local_managed"       # 受管部署副本
    EXTERNAL_COLLECTION = "external_collection"  # 可能由外部集合引入
    EXTERNAL_ADDONS = "external_addons"   # 其他管理员放置的本地 addon
    UNKNOWN = "unknown"


INVENTORY_ZH = {
    "present": "正常", "missing": "缺失", "invalid": "异常", "trashed": "回收站",
}
DESIRED_ZH = {
    "enabled": "期望启用", "disabled": "期望禁用", "unmanaged": "未接管",
}
APPLY_ZH = {
    "synced": "已同步(待重启)", "pending": "待应用", "applying": "应用中",
    "failed": "应用失败", "conflict": "存在冲突", "unmanaged": "未接管",
}
RUNTIME_ZH = {
    "loaded": "已加载", "not_loaded": "未加载", "unknown": "未知(无运行时探针)",
}
