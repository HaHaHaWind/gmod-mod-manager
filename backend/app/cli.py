"""管理员命令行工具(在没有 Web 界面时完成初始化)。

用法(在 backend 目录下):
  python -m app.cli init-db
  python -m app.cli create-admin <用户名> [--password <密码>]
  python -m app.cli list-admins
  python -m app.cli reset-password <用户名> [--password <密码>]
  python -m app.cli recover            # 手动执行一次启动恢复
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .config import get_settings
from .db import get_session_factory
from .models.entities import User, utcnow
from .security.password import check_password_strength, hash_password


def _ask_password(explicit: str | None) -> str:
    pwd = explicit or getpass.getpass("设置管理员密码(至少 10 位,含字母与数字):")
    while True:
        weak = check_password_strength(pwd)
        if weak is None:
            break
        print(f"密码不合格:{weak}")
        pwd = getpass.getpass("请重新输入密码:")
    if not explicit:
        again = getpass.getpass("再次输入密码确认:")
        if again != pwd:
            sys.exit("两次输入不一致,已取消")
    return pwd


def cmd_init_db(_args) -> None:
    from .db import Base, get_engine
    from . import models  # noqa: F401 确保实体注册
    engine = get_engine()
    Base.metadata.create_all(engine)
    print(f"数据库已初始化:{get_settings().data_path / 'gmm.db'}")


def cmd_create_admin(args) -> None:
    from . import models  # noqa: F401
    username = args.username.strip()
    if not 3 <= len(username) <= 64:
        sys.exit("用户名长度需在 3-64 之间")
    pwd = _ask_password(args.password)
    Session = get_session_factory()
    session = Session()
    try:
        exists = session.query(User).filter(User.username == username).first()
        if exists:
            sys.exit(f"用户 {username} 已存在")
        session.add(User(username=username, password_hash=hash_password(pwd),
                         is_admin=True))
        session.commit()
        print(f"管理员 {username} 已创建")
    finally:
        session.close()


def cmd_list_admins(_args) -> None:
    from . import models  # noqa: F401
    Session = get_session_factory()
    session = Session()
    try:
        rows = session.query(User).order_by(User.id).all()
        if not rows:
            print("(还没有任何用户)")
            return
        for u in rows:
            print(f"[{u.id}] {u.username}  admin={u.is_admin}  created={u.created_at}")
    finally:
        session.close()


def cmd_reset_password(args) -> None:
    from . import models  # noqa: F401
    Session = get_session_factory()
    session = Session()
    try:
        u = session.query(User).filter(User.username == args.username).first()
        if u is None:
            sys.exit(f"用户 {args.username} 不存在")
        pwd = _ask_password(args.password)
        u.password_hash = hash_password(pwd)
        u.created_at = u.created_at or utcnow()
        session.add(u)
        session.commit()
        print(f"用户 {args.username} 的密码已重置")
    finally:
        session.close()


def cmd_recover(_args) -> None:
    from .workers.runner import startup_recovery
    out = startup_recovery()
    print("启动恢复完成:", out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gmm-manage", description="GMod Mod 管理面板 - 管理命令")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="创建数据库表").set_defaults(func=cmd_init_db)

    p = sub.add_parser("create-admin", help="创建管理员")
    p.add_argument("username")
    p.add_argument("--password", default="", help="非交互指定密码(否则提示输入)")
    p.set_defaults(func=cmd_create_admin)

    sub.add_parser("list-admins", help="列出用户").set_defaults(func=cmd_list_admins)

    p = sub.add_parser("reset-password", help="重置用户密码")
    p.add_argument("username")
    p.add_argument("--password", default="")
    p.set_defaults(func=cmd_reset_password)

    sub.add_parser("recover", help="执行启动恢复(中断任务/过期清理)").set_defaults(func=cmd_recover)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
