"""测试基座:进程级隔离环境(全部路径指向临时目录)+ 登录态/CSRF 辅助。

环境变量在导入 app 之前设置(settings 在模块导入期被多处捕获);
各用例通过直接修改 Settings 单例属性切换管理模式,autouse 夹具负责还原默认值。
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import time
import zlib
from pathlib import Path

# ---- 必须先于任何 app 导入:定义隔离环境 ----
_BASE = Path(tempfile.mkdtemp(prefix="gmm-test-env-"))
os.environ.update({
    "DATA_DIR": str(_BASE / "data"),
    "WORKSHOP_CACHE_ROOT": str(_BASE / "cache"),
    "GMOD_ADDONS_ROOT": str(_BASE / "addons"),
    "WORKSHOP_IDS_FILE": str(_BASE / "cfg" / "srcds_workshop_ids.txt"),
    "TRASH_ROOT": str(_BASE / "trash"),
    "PUBLIC_ORIGIN": "http://testserver",
    "LOG_LEVEL": "WARNING",
})

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import (Base, get_engine, get_session_factory,  # noqa: E402
                    reset_engine_for_tests)

reset_engine_for_tests()
get_settings.cache_clear()

ADMIN_USER = "admin"
ADMIN_PASS = "AdminPass123"
WID_A = "240123456"
WID_B = "250123456"
WID_C = "260123456"


# ---------- GMA 构造(按解析器约定的二进制布局,含尾部 CRC) ----------

def build_gma(path: Path, title: str = "TestAddon",
              entries: dict[str, bytes] | None = None, version: int = 3) -> Path:
    entries = entries if entries is not None else {"lua/autorun/test.lua": b"print(1)\n"}
    buf = bytearray()
    buf += b"GMAD" + struct.pack("<B", version)
    buf += struct.pack("<QQ", 76561198000000000, 1700000000)
    if version >= 2:
        buf += b"workshop-123\x00" + b"\x00"   # required content 列表,空串结束
    buf += title.encode("utf-8") + b"\x00"
    buf += b"a short description\x00author\x00"
    buf += struct.pack("<i", 1)
    datas: list[bytes] = []
    for i, (name, data) in enumerate(entries.items(), 1):
        buf += struct.pack("<I", i) + name.encode("utf-8") + b"\x00"
        buf += struct.pack("<q", len(data)) + struct.pack("<I", zlib.crc32(data) & 0xFFFFFFFF)
        datas.append(data)
    buf += struct.pack("<I", 0)
    for d in datas:
        buf += d
    buf += struct.pack("<I", zlib.crc32(bytes(buf)) & 0xFFFFFFFF)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))
    return path


def make_cache_mod(settings, wid: str, title: str = "") -> Path:
    """在缓存根下按标准布局放置一个可解析的 GMA。"""
    gma_path = settings.cache_root / wid / "garrysmod" / "addons" / f"{wid}.gma"
    return build_gma(gma_path, title=title or f"Addon {wid}")


# ---------- 夹具 ----------

@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(client):
    """每个用例一张干净表(仅清数据,不重建引擎,worker 会话保持有效)。"""
    engine = get_engine()
    Session = get_session_factory()
    s = Session()
    try:
        with engine.connect() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
            conn.commit()
    except Exception:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _restore_settings():
    """用例内对 Settings 单例的改动在用例后还原默认,避免用例间串扰。"""
    yield
    s = get_settings()
    s.management_mode = "observe"
    s.read_only = True
    s.local_managed_strategy = "gma_copy"
    s.trash_retention_days = 30
    s.protected_ids = ""
    s.preview_max_bytes = 8 * 1024 * 1024
    s.auto_fetch_previews = True
    s.runtime_probe_enabled = True
    s.runtime_probe_file = ""
    s.gmod_addons_root = os.environ["GMOD_ADDONS_ROOT"]  # 探针用例可能改写路径


@pytest.fixture()
def settings():
    return get_settings()


@pytest.fixture()
def dirs(settings):
    """清空 cache/addons/trash/cfg/previews 五个工作目录,保证用例从空盘开始。"""
    import shutil
    for p in (settings.cache_root, settings.addons_root, settings.trash_path,
              settings.ids_file.parent if settings.ids_file else None,
              settings.data_path / "previews"):
        if p is None:
            continue
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture()
def admin_user(db):
    from app.models import User
    from app.security.password import hash_password
    u = User(username=ADMIN_USER, password_hash=hash_password(ADMIN_PASS), is_admin=True)
    db.add(u)
    db.commit()
    return u


class Api:
    """带登录态与 CSRF 的 API 辅助。"""

    def __init__(self, client: TestClient, csrf: str):
        self.client = client
        self.csrf = csrf

    def _h(self, headers: dict | None) -> dict:
        h = {"x-csrf-token": self.csrf}
        if headers:
            h.update(headers)
        return h

    def get(self, url: str, **kw):
        return self.client.get(url, **kw)

    def post(self, url: str, json=None, headers: dict | None = None, **kw):
        return self.client.post(url, json=json, headers=self._h(headers), **kw)


@pytest.fixture()
def anon(client):
    """匿名客户端:独立 cookie jar,避免登录态串扰(不进入 lifespan)。"""
    from app.main import app
    c = TestClient(app)
    yield c
    c.close()


@pytest.fixture()
def auth(client, admin_user) -> Api:
    r = client.post("/api/auth/login",
                    json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    return Api(client, r.json()["csrf_token"])


def wait_task(api: Api, task_id: str, timeout: float = 15.0) -> str:
    """轮询任务直至终态(依赖真实 worker 线程执行)。"""
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        r = api.get(f"/api/tasks/{task_id}")
        assert r.status_code == 200, r.text
        last = r.json()["status"]
        if last in ("succeeded", "failed", "interrupted", "cancelled"):
            return last
        time.sleep(0.2)
    return f"timeout({last})"


def make_mod_present(db, settings, wid: str, title: str = ""):
    """不落盘的快捷方式:登记一个 present 状态的 Mod 并放置缓存文件。"""
    from app.models import Mod
    make_cache_mod(settings, wid, title)
    mod = Mod(workshop_id=wid, folder_name=wid, inventory_state="present",
              cache_path=str(settings.cache_root / wid / "garrysmod" / "addons" / f"{wid}.gma"),
              size_bytes=1024, file_count=1)
    db.add(mod)
    db.commit()
    return mod
