"""Smoke test: stub every dependency this sandbox can't install (no pypi
network here - sqlalchemy/passlib/jose/fastapi all get installed for real on
the user's machine) and import every backend module to catch wiring bugs
(missing imports, typos, bad signatures) that py_compile's syntax-only check
can't see.
"""
import sys
import types

# --- sqlalchemy ---
fake_sa = types.ModuleType("sqlalchemy")
fake_sa.create_engine = lambda *a, **k: object()
fake_sa.text = lambda s: s
sys.modules["sqlalchemy"] = fake_sa

# --- passlib ---
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

# --- jose ---
fake_jose = types.ModuleType("jose")


class _FakeJWTError(Exception):
    pass


class _FakeJWT:
    @staticmethod
    def encode(payload, key, algorithm=None):
        return "faketoken"

    @staticmethod
    def decode(token, key, algorithms=None):
        return {"sub": "admin", "user_id": 1, "role": "ADMIN", "warehouse_id": None}


fake_jose.jwt = _FakeJWT
fake_jose.JWTError = _FakeJWTError
sys.modules["jose"] = fake_jose

# --- fastapi (real one should be installed via pip in this sandbox; if not, skip) ---
try:
    import fastapi  # noqa: F401
except ImportError:
    print("fastapi not installed in this sandbox - skipping router import checks.")
    sys.exit(0)

sys.path.insert(0, ".")

import app.auth  # noqa: E402
import app.migrations  # noqa: E402
import app.rate_limit  # noqa: E402
import app.services.admin_service  # noqa: E402
import app.services.alerts_service  # noqa: E402
import app.services.audit_service  # noqa: E402
import app.services.db_utils  # noqa: E402
import app.services.settings_service  # noqa: E402
import app.services.stock_service  # noqa: E402
import app.services.supplier_service  # noqa: E402
import app.services.sales_service  # noqa: E402
import app.services.storage_optimizer  # noqa: E402
import app.services.delivery_risk_service  # noqa: E402
import app.routers.auth  # noqa: E402
import app.routers.admin  # noqa: E402
import app.routers.alerts  # noqa: E402
import app.routers.search  # noqa: E402
import app.routers.settings  # noqa: E402
import app.routers.stock  # noqa: E402
import app.routers.suppliers  # noqa: E402
import app.routers.sales  # noqa: E402
import app.routers.storage  # noqa: E402
import app.routers.delivery  # noqa: E402
import app.main  # noqa: E402

print("ALL IMPORTS OK")
