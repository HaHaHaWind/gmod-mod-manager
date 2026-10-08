"""Alembic 环境:元数据来自 app.db.Base,数据库地址来自应用配置(DATA_DIR 等)。"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

# 保证可以 import app.*(backend 目录在 sys.path)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context  # noqa: E402
from sqlalchemy import engine_from_config, pool  # noqa: E402

from app import models  # noqa: F401,E402  确保全部实体注册到 metadata
from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    s = get_settings()
    return f"sqlite:///{(s.data_path / 'gmm.db').as_posix()}"


def run_migrations_offline() -> None:
    context.configure(url=_db_url(), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"},
                      render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # SQLite 无法自建父目录:迁移前确保数据目录存在(与 app.db.get_engine 行为一致)
    get_settings().ensure_data_dir()
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _db_url()
    connectable = engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # SQLite:批量模式以支持 ALTER/索引变更
        context.configure(connection=connection, target_metadata=target_metadata,
                          render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
