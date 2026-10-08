"""应用配置:全部来自环境变量 / .env,路径均为可配置项,未配置时允许隔离运行。"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MANAGEMENT_MODES = ("observe", "native_ids", "local_managed")
SERVER_CONTROL_MODES = ("manual", "systemd")
LOCAL_MANAGED_STRATEGIES = ("gma_copy", "folder_extract")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ---- 游戏服务器路径(默认值来自部署环境,可完全配置;空串表示未配置) ----
    gmod_server_root: str = ""
    workshop_cache_root: str = ""
    gmod_addons_root: str = ""
    workshop_ids_file: str = ""
    trash_root: str = ""
    trash_retention_days: int = 30  # 回收站自动永久删除的保留天数

    # ---- 面板自身 ----
    data_dir: str = "data"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    public_origin: str = "http://localhost:8080"
    cors_dev_origins: str = ""  # 逗号分隔,仅供开发环境
    secret_key: str = ""        # 留空则在 data_dir 下生成并持久化
    session_ttl_hours: int = 72
    login_rate_limit: str = "5/300"  # 次数/秒
    log_level: str = "INFO"
    # 运行日志目录(独立于数据目录,便于排查);相对路径基于 backend 工作目录;
    # 留空则不写文件日志。app.log 按大小轮转:单文件 10MB,保留 5 份
    log_dir: str = "logs"

    # ---- 管理模式 ----
    management_mode: str = "observe"
    server_control_mode: str = "manual"
    gmod_systemd_unit: str = ""
    gmod_process_names: str = "srcds_linux,srcds_run,srcds.exe"
    local_managed_strategy: str = "gma_copy"  # gma_copy | folder_extract
    read_only: bool = True

    # ---- 运行时探针 ----
    # srcds 挂载缓存(cfg/srcds_addons.txt,srcds 自动生成,非配置文件)用于推断 runtime_state
    runtime_probe_enabled: bool = True
    runtime_probe_file: str = ""  # 探针文件路径;留空按候选顺序自动发现

    # ---- Steam ----
    steam_api_base: str = "https://api.steampowered.com"
    steam_batch_limit: int = 100
    steam_timeout_seconds: float = 15.0
    steam_retries: int = 2
    # 访问 Steam API 与封面 CDN 走的 HTTP 代理(如 http://127.0.0.1:7890);
    # 留空则直连,同时也会读取系统环境变量 HTTP_PROXY/HTTPS_PROXY
    steam_proxy: str = ""
    metadata_ttl_seconds: int = 86400
    steam_web_api_key: str = ""  # 可选:作者昵称增强查询
    workshop_collection_id: str = ""  # 已知外部集合(冲突识别用)
    # 扫描/元数据刷新后自动抓取封面图到本地(data/previews),列表优先显示本地图
    auto_fetch_previews: bool = True

    # ---- 保护与限制 ----
    protected_ids: str = ""  # 逗号分隔,默认保护的 Workshop ID
    max_action_ids: int = 200
    plan_ttl_minutes: int = 120
    preview_max_bytes: int = 8 * 1024 * 1024

    @field_validator("management_mode")
    @classmethod
    def _v_mode(cls, v: str) -> str:
        v = (v or "observe").strip().lower()
        if v not in MANAGEMENT_MODES:
            raise ValueError(f"MANAGEMENT_MODE 必须是 {MANAGEMENT_MODES} 之一")
        return v

    @field_validator("server_control_mode")
    @classmethod
    def _v_ctl(cls, v: str) -> str:
        v = (v or "manual").strip().lower()
        if v not in SERVER_CONTROL_MODES:
            raise ValueError(f"SERVER_CONTROL_MODE 必须是 {SERVER_CONTROL_MODES} 之一")
        return v

    @field_validator("local_managed_strategy")
    @classmethod
    def _v_strategy(cls, v: str) -> str:
        v = (v or "gma_copy").strip().lower()
        if v not in LOCAL_MANAGED_STRATEGIES:
            raise ValueError(f"LOCAL_MANAGED_STRATEGY 必须是 {LOCAL_MANAGED_STRATEGIES} 之一")
        return v

    # ---- 派生路径 ----
    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir)
        return p if p.is_absolute() else Path.cwd() / p

    @property
    def log_path(self) -> Path | None:
        p = self._opt_path(self.log_dir)
        if p is None:
            return None
        return p if p.is_absolute() else Path.cwd() / p

    def _opt_path(self, raw: str) -> Path | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        return Path(raw)

    @property
    def server_root(self) -> Path | None:
        return self._opt_path(self.gmod_server_root)

    @property
    def cache_root(self) -> Path | None:
        return self._opt_path(self.workshop_cache_root)

    @property
    def addons_root(self) -> Path | None:
        return self._opt_path(self.gmod_addons_root)

    @property
    def ids_file(self) -> Path | None:
        return self._opt_path(self.workshop_ids_file)

    @property
    def trash_path(self) -> Path | None:
        return self._opt_path(self.trash_root)

    @property
    def protected_id_set(self) -> set[str]:
        return {x.strip() for x in (self.protected_ids or "").split(",") if x.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in (self.cors_dev_origins or "").split(",") if x.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.public_origin.rstrip("/")] + self.cors_origin_list
        return [o.rstrip("/") for o in origins if o]

    def ensure_data_dir(self) -> Path:
        self.data_path.mkdir(parents=True, exist_ok=True)
        return self.data_path

    def get_secret_key(self) -> str:
        """返回持久化会话签名密钥:优先 SECRET_KEY,否则在数据目录生成并保存。"""
        if self.secret_key:
            return self.secret_key
        self.ensure_data_dir()
        key_file = self.data_path / "secret.key"
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key = secrets.token_urlsafe(48)
        key_file.write_text(key, encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
