"""JWT authentication + role-based access helpers.

Two roles, seeded by scripts/seed_database.py into dim_users:
  - ADMIN: full access to every warehouse's data, and the only role allowed
    to call the /admin/* endpoints (add warehouses/suppliers/products/
    locations).
  - WAREHOUSE: scoped to exactly one warehouse (its warehouse_id is embedded
    in the JWT at login). Every dashboard read endpoint auto-filters to that
    warehouse for these users regardless of any warehouse_id query param
    they pass - see effective_warehouse_id() below.

This is a deliberately lightweight auth layer (bcrypt password hashing +
signed JWTs) sized for an internal ops dashboard with a handful of named
accounts - still no refresh tokens or session table, so a token can't be
revoked early; it just expires after ACCESS_TOKEN_EXPIRE_MINUTES. See
README.md for the seeded default accounts and how to add more via the
Admin UI's Manage Users page (POST /admin/users), or self-service
registration at POST /auth/register (pending Admin approval - see
admin_service.register_user).

Login security follow-up (see README's "Login security" section for the
full writeup):
  - The browser app authenticates via an httpOnly cookie
    (ACCESS_TOKEN_COOKIE_NAME below), not a JS-readable localStorage token,
    so an XSS bug can no longer just read the token out of storage. The
    Authorization: Bearer header still works too, for /docs and API
    scripts - see get_current_user.
  - must_change_password forces a real password to be set (via
    POST /auth/change-password) before anything else works, for the seeded
    demo accounts and any account an Admin sets/resets a password for.
  - POST /auth/forgot-password / POST /auth/reset-password give a
    self-service reset path (see app/services/email_service.py) instead of
    "ask an Admin to reset it" being the only option.
  - JWT_SECRET_KEY has no usable default in production - see the startup
    check right below.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import text

from app.config import ENVIRONMENT
from app.database import engine
from app.services.db_utils import query_one

# The name of the httpOnly cookie the browser app authenticates with (see
# create_access_token / routers/auth.py's login()). Kept as a constant here
# so auth.py (reading it) and routers/auth.py (setting/clearing it) can't
# drift out of sync.
ACCESS_TOKEN_COOKIE_NAME = "shuppa_access_token"

_DEFAULT_SECRET_KEY = "shuppa-dev-secret-change-me-in-production"
SECRET_KEY = os.getenv("JWT_SECRET_KEY", _DEFAULT_SECRET_KEY)
if ENVIRONMENT == "production" and SECRET_KEY == _DEFAULT_SECRET_KEY:
    # This string is sitting in plain sight in this file (and anywhere this
    # repo has ever been pushed), so if it's ever actually used to sign
    # tokens in production, anyone can forge a valid admin JWT. Refuse to
    # start rather than silently running with a known-public secret.
    raise RuntimeError(
        "JWT_SECRET_KEY must be set to a real secret when ENVIRONMENT=production - "
        "refusing to start with the public default dev secret. Generate one with, "
        "e.g., `python -c \"import secrets; print(secrets.token_hex(32))\"` and set "
        "it in backend/.env."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

# Paths a user with must_change_password=true is still allowed to call -
# everything else is blocked (see get_current_user below) until they set a
# real password. Keep this in sync with routers/auth.py.
_PASSWORD_CHANGE_EXEMPT_PATHS = {"/auth/change-password", "/auth/me", "/auth/logout"}

# Basic brute-force speed bump, not real account-security tooling: after this
# many consecutive wrong passwords, the account is locked for LOCKOUT_MINUTES.
# Both reset to zero/NULL on a successful login. This is intentionally simple
# (no IP tracking, no CAPTCHA, no admin unlock button - Admin can clear a
# lockout by resetting the user's password from Manage Users, which also
# clears failed_login_count) - see README's "Auth is intentionally
# lightweight" section.
MAX_FAILED_LOGIN_ATTEMPTS = int(os.getenv("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False so we can distinguish "no token" (401 with our own
# message) from "bad token" and so an optional-auth dependency is possible.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class CurrentUser(BaseModel):
    user_id: int
    username: str
    role: str
    warehouse_id: Optional[int] = None
    must_change_password: bool = False


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


class AccountLockedError(Exception):
    def __init__(self, locked_until: datetime):
        self.locked_until = locked_until
        super().__init__(f"Account locked until {locked_until.isoformat()}")


class AccountDeactivatedError(Exception):
    pass


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Verifies credentials and enforces the lockout policy above.

    Raises AccountLockedError / AccountDeactivatedError for those specific
    cases (so the login endpoint can give a clear message) and returns None
    for a plain wrong username/password (deliberately the same response
    whether the username doesn't exist or the password is wrong, to avoid
    leaking which usernames are valid).
    """
    row = query_one("SELECT * FROM dim_users WHERE username = :u", {"u": username})
    if not row:
        return None

    if row.get("is_active") is False:
        raise AccountDeactivatedError()

    locked_until = row.get("locked_until")
    if locked_until and locked_until > datetime.utcnow():
        raise AccountLockedError(locked_until)

    if not verify_password(password, row["password_hash"]):
        _record_failed_login(row)
        return None

    _record_successful_login(row["user_id"])
    return row


def _record_failed_login(row: dict) -> None:
    new_count = (row.get("failed_login_count") or 0) + 1
    with engine.begin() as conn:
        if new_count >= MAX_FAILED_LOGIN_ATTEMPTS:
            conn.execute(
                text(
                    "UPDATE dim_users SET failed_login_count = :c, "
                    "locked_until = NOW() + (:mins || ' minutes')::interval WHERE user_id = :id"
                ),
                {"c": new_count, "mins": LOCKOUT_MINUTES, "id": row["user_id"]},
            )
        else:
            conn.execute(
                text("UPDATE dim_users SET failed_login_count = :c WHERE user_id = :id"),
                {"c": new_count, "id": row["user_id"]},
            )


def _record_successful_login(user_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE dim_users SET failed_login_count = 0, locked_until = NULL, "
                "last_login_at = NOW() WHERE user_id = :id"
            ),
            {"id": user_id},
        )


def change_own_password(user_id: int, current_password: str, new_password: str) -> None:
    """Used by POST /auth/change-password - the one path a user with
    must_change_password=true is allowed to call (see
    _PASSWORD_CHANGE_EXEMPT_PATHS) to set a real password for themselves.
    Requires the current password (which, for a forced change, is the known
    demo/admin-set one) so this can't be used to take over a session that
    was stolen without also knowing the password."""
    row = query_one("SELECT password_hash FROM dim_users WHERE user_id = :id", {"id": user_id})
    if not row or not verify_password(current_password, row["password_hash"]):
        raise ValueError("Current password is incorrect")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE dim_users SET password_hash = :hash, must_change_password = false, "
                "failed_login_count = 0, locked_until = NULL WHERE user_id = :id"
            ),
            {"hash": hash_password(new_password), "id": user_id},
        )


def create_access_token(user: dict) -> str:
    payload = {
        "sub": user["username"],
        "user_id": user["user_id"],
        "role": user["role"],
        "warehouse_id": user["warehouse_id"],
        "must_change_password": bool(user.get("must_change_password")),
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode(token: str) -> CurrentUser:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session - please log in again.")
    return CurrentUser(
        user_id=payload["user_id"],
        username=payload["sub"],
        role=payload["role"],
        warehouse_id=payload.get("warehouse_id"),
        must_change_password=bool(payload.get("must_change_password", False)),
    )


def get_current_user(request: Request, bearer_token: Optional[str] = Depends(oauth2_scheme)) -> CurrentUser:
    """Reads the token from the Authorization header first (so the
    interactive /docs page and any script-based API client keep working
    exactly as before), falling back to the httpOnly cookie the browser app
    now authenticates with (see ACCESS_TOKEN_COOKIE_NAME) - the cookie can't
    be read or exfiltrated by JavaScript, unlike the old localStorage token.
    """
    token = bearer_token or request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = _decode(token)
    if user.must_change_password and request.url.path not in _PASSWORD_CHANGE_EXEMPT_PATHS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must set a new password before continuing.",
            headers={"X-Password-Change-Required": "true"},
        )
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def effective_warehouse_id(requested: Optional[int], user: CurrentUser) -> Optional[int]:
    """WAREHOUSE-role users are always locked to their own warehouse_id,
    regardless of what they pass in the query string or request body.
    ADMIN users get whatever warehouse_id they requested (None = all
    warehouses)."""
    if user.role == "WAREHOUSE":
        return user.warehouse_id
    return requested
