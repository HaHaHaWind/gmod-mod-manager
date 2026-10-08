"""运行日志落盘:统一写入独立 logs 目录并按大小轮转,便于服务器排错。

- app.log:gmm.* 业务日志与 uvicorn 访问/错误日志共用,带时间戳与 logger 名。
- 轮转:单文件 10MB,保留 5 份(app.log.1 ~ app.log.5),无需外部 logrotate。
- LOG_DIR 留空则不写文件;目录不可写时降级为仅终端输出,不阻塞启动。
- 幂等:重复调用(多次 create_app / --reload)不会叠加 handler。
"""
from __future__ import annotations

import logging
import logging.handlers

from .config import Settings

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUPS = 5
_NOISY_LOGGERS = ("httpx", "httpcore")  # 每请求一条 INFO 刷屏,统一压到 WARNING


def setup_logging(settings: Settings) -> None:
    """配置根日志:终端 + 轮转文件(可选);进程内可安全重复调用。"""
    root = logging.getLogger()
    root.setLevel((settings.log_level or "INFO").upper())
    if not any(getattr(h, "_gmm_console", False) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        console._gmm_console = True
        root.addHandler(console)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # uvicorn 自带 handler 会绕过根配置;清掉后统一走根 handler(终端+文件)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True

    _rebind_file_handler(root, settings)


def _rebind_file_handler(root: logging.Logger, settings: Settings) -> None:
    """替换文件 handler(LOG_DIR 可在运行时变更);不可用时降级为无文件日志。"""
    for h in list(root.handlers):
        if getattr(h, "_gmm_file", False):
            root.removeHandler(h)
            h.close()
    log_dir = settings.log_path
    if log_dir is None:
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_dir / "app.log", maxBytes=_MAX_BYTES,
            backupCount=_BACKUPS, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FORMAT))
        fh._gmm_file = True
        root.addHandler(fh)
    except OSError as e:
        logging.getLogger("gmm.logging").warning(
            "日志目录不可用(%s),文件日志停用:%s", log_dir, e)
