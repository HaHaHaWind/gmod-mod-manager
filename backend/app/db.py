"""SQLAlchemy 引擎与会话:SQLite,外键开启,忙等待 30s,启用 WAL;单实例写入。"""
from __future__ import annotations

import threading
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker | None = None
_lock = threading.Lock()


def _make_engine(db_path):
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"timeout": 30, "check_same_thread": False},
                           pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        try:
            cur.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        cur.close()

    return engine


def get_engine():
    global _engine, _session_factory
    with _lock:
        if _engine is None:
            s = get_settings()
            s.ensure_data_dir()
            db_path = s.data_path / "gmm.db"
            _engine = _make_engine(db_path)
            _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker:
    get_engine()
    assert _session_factory
    return _session_factory


def reset_engine_for_tests():
    """测试专用:切换临时数据库后调用。"""
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None


def get_db():
    Session = get_session_factory()
    db = Session()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
