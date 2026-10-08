"""鉴权/会话/CSRF/登录限速/审计脱敏。"""
from app.security.password import check_password_strength, hash_password, verify_password
from tests.conftest import ADMIN_PASS, ADMIN_USER


def _audit_rows(db, action, outcome=None):
    from sqlalchemy import select
    from app.models import AuditLog
    q = select(AuditLog).where(AuditLog.action == action)
    if outcome:
        q = q.where(AuditLog.outcome == outcome)
    return list(db.execute(q).scalars())


# ---------- 密码 ----------

def test_password_hash_and_verify():
    h = hash_password("AdminPass123")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "AdminPass123")
    assert not verify_password(h, "wrong-pass-999")


def test_password_strength_rules():
    assert check_password_strength("short1") is not None          # 少于 10 位
    assert check_password_strength("onlyletterspass") is not None  # 无数字
    assert check_password_strength("12345678901") is not None      # 无字母
    assert check_password_strength("AdminPass123") is None


# ---------- 登录/登出 ----------

def test_login_wrong_password_401_and_audited(auth, anon, db):
    r = anon.post("/api/auth/login", json={"username": ADMIN_USER, "password": "no-such-pass-1"})
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "unauthorized"
    assert body["request_id"]
    assert "message" in body
    fails = _audit_rows(db, "auth.login", outcome="fail")
    assert len(fails) == 1
    assert fails[0].actor == ADMIN_USER


def test_login_success_sets_cookie_and_returns_csrf(anon, admin_user):
    r = anon.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["username"] == ADMIN_USER and body["is_admin"] is True
    assert body["csrf_token"]
    assert "gmm_session" in anon.cookies


def test_me_requires_auth(anon):
    r = anon.get("/api/auth/me")
    assert r.status_code == 401


def test_me_and_logout(auth):
    r = auth.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["csrf_token"] == auth.csrf
    r = auth.post("/api/auth/logout")
    assert r.status_code == 200
    assert auth.get("/api/auth/me").status_code == 401


# ---------- CSRF ----------

def test_write_without_csrf_rejected(auth):
    r = auth.client.post("/api/plans", json={"items": [{"action": "enable", "workshop_id": "1"}]})
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"


def test_read_endpoints_need_session_only(anon, auth):
    assert anon.get("/api/mods").status_code == 401
    assert auth.get("/api/mods").status_code == 200


# ---------- 登录限速 ----------

def test_login_rate_limit(anon, db, admin_user):
    last = None
    for _ in range(6):  # 默认 5/300:第 6 次应被拒
        last = anon.post("/api/auth/login",
                         json={"username": "ratelimit_user", "password": "whatever-123"})
    assert last.status_code == 429
    assert last.json()["code"] == "rate_limited"
    # 其他用户不受影响(限速按键 ip|username 隔离)
    r = anon.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200, r.text


# ---------- 审计脱敏 ----------

def test_audit_redact_masks_sensitive_keys():
    from app.services.audit import redact
    out = redact({"password": "secret1", "access_token": "t1",
                  "nested": {"csrf": "c1", "keep": "v"}, "plain": "x"})
    assert out["password"] == "***"
    assert out["access_token"] == "***"
    assert out["nested"]["csrf"] == "***"
    assert out["nested"]["keep"] == "v"
    assert out["plain"] == "x"


def test_audit_api_lists_entries(auth, db):
    from app.services import audit as audit_svc
    audit_svc.log(db, actor="tester", action="unit.test", detail={"password": "p", "ip": "1.2.3.4"})
    db.commit()
    r = auth.get("/api/system/audit")
    assert r.status_code == 200
    items = r.json()["items"]
    row = next(x for x in items if x["action"] == "unit.test")
    assert row["detail"]["password"] == "***"
    assert row["detail"]["ip"] == "1.2.3.4"
