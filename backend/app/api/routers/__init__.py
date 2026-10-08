"""路由汇总。"""
from __future__ import annotations

from . import auth, misc, mods, plans, system

ALL_ROUTERS = (auth.router, mods.router, plans.router, misc.router,
               misc.trash_router, system.router)
