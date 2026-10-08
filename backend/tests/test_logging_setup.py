"""日志落盘:setup_logging 的文件输出、uvicorn 接管与幂等性。"""
from __future__ import annotations

import logging

import pytest

from app.config import Settings
from app.logging_setup import setup_logging


@pytest.fixture(autouse=True)
def _reset_root_logging():
    """用例后摘掉挂到根 logger 的 handler 并复位级别,避免污染其他用例。"""
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_gmm_file", False) or getattr(h, "_gmm_console", False):
            root.removeHandler(h)
            h.close()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.NOTSET)


def _file_handlers(root: logging.Logger) -> list:
    return [h for h in root.handlers if getattr(h, "_gmm_file", False)]


def _settings(tmp_path, **kw) -> Settings:
    return Settings(data_dir=str(tmp_path / "data"),
                    log_dir=str(tmp_path / "logs"), **kw)


def test_setup_logging_writes_file(tmp_path):
    logs = tmp_path / "logs"
    setup_logging(_settings(tmp_path))
    logging.getLogger("gmm.test").warning("文件日志自检 %s", "W-1")
    for h in _file_handlers(logging.getLogger()):
        h.flush()
    content = (logs / "app.log").read_text(encoding="utf-8")
    assert "文件日志自检 W-1" in content
    assert "gmm.test" in content          # 带 logger 名,便于定位模块
    assert "WARNING" in content           # 带级别
    assert content.split(" ")[0].count("-") == 2  # 带时间戳前缀


def test_setup_logging_idempotent(tmp_path):
    s = _settings(tmp_path)
    setup_logging(s)
    setup_logging(s)  # 测试里多次 create_app / reload 不会叠加 handler
    root = logging.getLogger()
    assert len(_file_handlers(root)) == 1
    assert len([h for h in root.handlers
                if getattr(h, "_gmm_console", False)]) == 1


def test_log_dir_empty_disables_file(tmp_path):
    setup_logging(Settings(data_dir=str(tmp_path / "data"), log_dir=""))
    assert _file_handlers(logging.getLogger()) == []


def test_log_dir_unwritable_degrades(tmp_path):
    # 目录位置落在一个文件上 → mkdir 失败,应降级而非抛异常
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    setup_logging(Settings(data_dir=str(tmp_path / "data"),
                           log_dir=str(blocker / "logs")))
    assert _file_handlers(logging.getLogger()) == []


def test_uvicorn_loggers_propagate_to_root(tmp_path):
    setup_logging(_settings(tmp_path))
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        assert uv.propagate is True
        assert uv.handlers == []  # 自带 handler 已清空,统一走根配置


def test_noisy_http_loggers_suppressed(tmp_path):
    setup_logging(_settings(tmp_path))
    for name in ("httpx", "httpcore"):
        assert logging.getLogger(name).level == logging.WARNING


def test_rebind_moves_file_handler_on_dir_change(tmp_path):
    setup_logging(_settings(tmp_path))
    logs2 = tmp_path / "logs2"
    setup_logging(Settings(data_dir=str(tmp_path / "data"), log_dir=str(logs2)))
    root = logging.getLogger()
    assert len(_file_handlers(root)) == 1  # 旧 handler 被替换而非叠加
    logging.getLogger("gmm.test").warning("写入新目录")
    for h in _file_handlers(root):
        h.flush()
    assert "写入新目录" in (logs2 / "app.log").read_text(encoding="utf-8")
