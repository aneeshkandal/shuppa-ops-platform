"""Logic tests for the Session 7 login-security hardening pass: the new
password policy, the register/change-password service logic, and the
tighter dedicated rate limit on the auth endpoints. Same style as
test_logic.py/test_logic_phase7.py/test_logic_phase8.py: stub
sqlalchemy/fastapi/jose/passlib so importing app.auth/app.services.* doesn't
need real DB access or those packages installed, then exercise pure logic
with plain asserts and a couple of small monkeypatched-engine fakes for the
functions that do write to the DB. Run with `python3 test_logic_phase9.py`.
"""

import asyncio
import sys
import types

sys.path.insert(0, ".")

# --- Same stubs as test_logic_phase7.py/test_logic_phase8.py ---------------

fake_sa = types.ModuleType("sqlalchemy")
fake_sa.create_engine = lambda *a, **k: object()
fake_sa.text = lambda s: s
sys.modules["sqlalchemy"] = fake_sa

fake_fastapi = types.ModuleType("fastapi")
fake_fastapi.Depends = lambda x=None: x
fake_fastapi.HTTPException = type(
    "HTTPException",
    (Exception,),
    {
        "__init__": lambda self, status_code=None, detail=None, headers=None: (
            setattr(self, "status_code", status_code),
            setattr(self, "detail", detail),
            setattr(self, "headers", headers),
        )[-1]
    },
)
fake_fastapi.Request = type("Request", (), {})


class _FakeStatus:
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403


fake_fastapi.status = _FakeStatus
sys.modules["fastapi"] = fake_fastapi

fake_fastapi_security = types.ModuleType("fastapi.security")
fake_fastapi_security.OAuth2PasswordBearer = lambda *a, **k: (lambda *a2, **k2: None)
sys.modules["fastapi.security"] = fake_fastapi_security

fake_jose = types.ModuleType("jose")
fake_jose.JWTError = type("JWTError", (Exception,), {})
fake_jose.jwt = types.SimpleNamespace(
    encode=lambda payload, key, algorithm=None: "faketoken",
    decode=lambda token, key, algorithms=None: {"sub": "admin", "user_id": 1, "role": "ADMIN", "warehouse_id": None},
)
sys.modules["jose"] = fake_jose

fake_passlib = types.ModuleType("passlib")
fake_passlib_context = types.ModuleType("passlib.context")


class _FakeCryptContext:
    def __init__(self, *a, **k):
        pass

    def hash(self, password):
        return f"fakehash${password}"

    def verify(self, plain, hashed):
        return hashed == f"fakehash${plain}"


fake_passlib_context.CryptContext = _FakeCryptContext
sys.modules["passlib"] = fake_passlib
sys.modules["passlib.context"] = fake_passlib_context

# ---------------------------------------------------------------------------
# schemas.py password/email policy (real pydantic - no stubbing needed for
# this part, schemas.py doesn't import fastapi/sqlalchemy at all)
# ---------------------------------------------------------------------------
from pydantic import ValidationError  # noqa: E402

from app.models.schemas import AddUserRequest, RegisterRequest  # noqa: E402

try:
    AddUserRequest(username="bob", password="short1", role="WAREHOUSE", warehouse_id=1)
    raise AssertionError("a 6-char password should be rejected by the new 10-char minimum")
except ValidationError:
    pass

AddUserRequest(username="bob", password="longenough1", role="WAREHOUSE", warehouse_id=1)  # should not raise

try:
    RegisterRequest(username="bob", password="longenough1", email="not-an-email", warehouse_id=1)
    raise AssertionError("a malformed email should be rejected")
except ValidationError:
    pass

RegisterRequest(username="bob", password="longenough1", email="bob@example.com", warehouse_id=1)  # should not raise
print("schemas.py: password length + email format policy OK")

# ---------------------------------------------------------------------------
# auth.change_own_password
# ---------------------------------------------------------------------------
import app.auth as auth  # noqa: E402


class _FakeConn:
    def __init__(self):
        self.executed = []

    def execute(self, stmt, params=None):
        self.executed.append((stmt, params))


class _FakeEngineCtx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *a):
        return False


class _FakeEngine:
    def __init__(self):
        self.conn = _FakeConn()

    def begin(self):
        return _FakeEngineCtx(self.conn)


fake_engine = _FakeEngine()
auth.engine = fake_engine
auth.query_one = lambda sql, params=None: {"password_hash": "fakehash$OldPass123"}

try:
    auth.change_own_password(user_id=1, current_password="WrongPass123", new_password="NewPass1234")
    raise AssertionError("change_own_password must reject an incorrect current password")
except ValueError:
    pass
assert fake_engine.conn.executed == [], "no UPDATE should run when the current password check fails"

auth.change_own_password(user_id=1, current_password="OldPass123", new_password="NewPass1234")
assert len(fake_engine.conn.executed) == 1, "a correct current password should run exactly one UPDATE"
_, params = fake_engine.conn.executed[0]
assert params["hash"] == "fakehash$NewPass1234"
assert params["id"] == 1
print("auth.change_own_password: wrong-password rejection + successful update OK")

# ---------------------------------------------------------------------------
# auth.get_current_user's must_change_password gating (tests the gating
# branch directly with a fake decoded token, rather than the Depends/
# OAuth2PasswordBearer plumbing around it, which is what's actually stubbed
# above)
# ---------------------------------------------------------------------------


class _FakeCookies(dict):
    pass


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeRequest:
    def __init__(self, path, cookie_token=None):
        self.url = _FakeURL(path)
        self.cookies = _FakeCookies()
        if cookie_token:
            self.cookies[auth.ACCESS_TOKEN_COOKIE_NAME] = cookie_token


# jwt.decode is stubbed above to always return a fixed payload with no
# must_change_password key -> defaults to False, so _decode()'s result
# depends only on what we ask get_current_user to check via the path.
must_change_payload = {"sub": "admin", "user_id": 1, "role": "ADMIN", "warehouse_id": None, "must_change_password": True}
fake_jose.jwt.decode = lambda token, key, algorithms=None: must_change_payload

blocked = False
try:
    auth.get_current_user(_FakeRequest("/stock/summary", cookie_token="tok"), bearer_token=None)
except fake_fastapi.HTTPException as e:
    blocked = True
    assert e.status_code == 403
assert blocked, "a must_change_password user must be blocked from an unrelated endpoint"

allowed_user = auth.get_current_user(_FakeRequest("/auth/change-password", cookie_token="tok"), bearer_token=None)
assert allowed_user.must_change_password is True
print("auth.get_current_user: must_change_password blocks other paths but allows /auth/change-password OK")

# ---------------------------------------------------------------------------
# admin_service.register_user
# ---------------------------------------------------------------------------
import app.services.admin_service as admin_service  # noqa: E402
from app.models.schemas import RegisterRequest as _RegisterRequest  # noqa: E402

fake_engine2 = _FakeEngine()
admin_service.engine = fake_engine2

_existing_usernames = {"taken"}
_existing_emails = {"taken@example.com"}


def _fake_query_one(sql, params=None):
    if "MAX(user_id)" in sql:
        return {"m": 5}
    if "username" in sql and params and params.get("u") in _existing_usernames:
        return {"user_id": 999}
    if "email" in sql and params and params.get("e") in _existing_emails:
        return {"user_id": 999}
    return None


admin_service.query_one = _fake_query_one
admin_service.audit_service.log_system_event = lambda *a, **k: None

try:
    admin_service.register_user(_RegisterRequest(username="taken", password="longenough1", email="new@example.com", warehouse_id=1))
    raise AssertionError("a duplicate username must be rejected")
except ValueError:
    pass

try:
    admin_service.register_user(_RegisterRequest(username="newname", password="longenough1", email="taken@example.com", warehouse_id=1))
    raise AssertionError("a duplicate email must be rejected")
except ValueError:
    pass

result = admin_service.register_user(
    _RegisterRequest(username="newname", password="longenough1", email="new@example.com", warehouse_id=2)
)
assert result["pending_approval"] is True
assert len(fake_engine2.conn.executed) == 1
_, insert_params = fake_engine2.conn.executed[0]
assert insert_params["wh"] == 2
assert insert_params["id"] == 6
print("admin_service.register_user: duplicate checks + pending-approval insert OK")

# ---------------------------------------------------------------------------
# rate_limit.RateLimitMiddleware's dedicated tighter bucket for sensitive
# auth paths (/auth/login, /auth/register, /auth/forgot-password)
# ---------------------------------------------------------------------------
from app.rate_limit import RateLimitMiddleware  # noqa: E402


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _RLFakeURL:
    def __init__(self, path):
        self.path = path


class _RLFakeRequest:
    def __init__(self, host="5.5.5.5", path="/auth/login"):
        self.client = _FakeClient(host)
        self.url = _RLFakeURL(path)


class _FakeResponse:
    status_code = 200


async def _login_rate_limit_checks():
    # General limit is generous (100/min); login-specific limit is tight
    # (2/5min) - a script hammering /auth/login should hit the tight limit
    # long before the general one would ever trigger.
    mw = RateLimitMiddleware(app=None, requests=100, window_seconds=60, login_requests=2, login_window_seconds=300)

    async def call_next(req):
        return _FakeResponse()

    login_statuses = [(await mw.dispatch(_RLFakeRequest(path="/auth/login"), call_next)).status_code for _ in range(4)]
    register_status = (await mw.dispatch(_RLFakeRequest(path="/auth/register"), call_next)).status_code
    # A normal dashboard path from the same IP is governed only by the
    # generous general limit, unaffected by the auth bucket being exhausted.
    dashboard_status = (await mw.dispatch(_RLFakeRequest(path="/stock/summary"), call_next)).status_code
    return login_statuses, register_status, dashboard_status


login_statuses, register_status, dashboard_status = asyncio.run(_login_rate_limit_checks())
print("login rate limit statuses:", login_statuses, "register:", register_status, "dashboard:", dashboard_status)
assert login_statuses == [200, 200, 429, 429], "only the first login_requests calls to /auth/login should pass"
assert register_status == 429, "/auth/register shares the same per-IP sensitive-path bucket as /auth/login"
assert dashboard_status == 200, "a non-auth path must not be limited by the tight auth-path bucket"

print("\nALL PHASE 9 LOGIC TESTS PASSED")
