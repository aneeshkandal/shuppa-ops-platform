import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import text

from app.auth import (
    ACCESS_TOKEN_COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AccountDeactivatedError,
    AccountLockedError,
    CurrentUser,
    authenticate_user,
    change_own_password,
    create_access_token,
    get_current_user,
    hash_password,
)
from app.config import ENVIRONMENT
from app.database import engine
from app.models.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.services import admin_service, audit_service, email_service
from app.services.db_utils import query_one, query_records

router = APIRouter(prefix="/auth", tags=["Auth"])

# How long a forgot-password link stays usable. Short-lived by design - see
# dim_password_reset_tokens in app/migrations.py.
RESET_TOKEN_EXPIRE_MINUTES = 30

# A Secure cookie is silently dropped by browsers over plain http://, which
# is how local dev runs - only require it over the real HTTPS deployment.
_COOKIE_SECURE = ENVIRONMENT == "production"


def _set_auth_cookie(response: Response, token: str) -> None:
    """The browser app's actual auth mechanism: an httpOnly cookie that
    JavaScript can't read (so an XSS bug can't just steal it out of
    localStorage the way the old token storage could). SameSite=lax means it
    still rides along on a normal top-level navigation to this site but not
    on a cross-site POST from somewhere else, which is most of what CSRF
    protection here relies on - see README's "Login security" section for
    the full reasoning and its limits."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


@router.post("/login")
def login(response: Response, form: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 password-flow login. Accepts form fields username/password
    (not JSON) so it works directly with FastAPI's interactive /docs and
    any standard OAuth2 client; the frontend posts a URL-encoded form too.

    Sets the real auth cookie (see _set_auth_cookie) AND still returns
    access_token in the JSON body - the cookie is what the browser app
    actually uses, but the JSON field keeps /docs's "Authorize" button and
    any script-based API client working via a plain Bearer header (see
    app/auth.py's get_current_user, which accepts either).
    """
    try:
        user = authenticate_user(form.username, form.password)
    except AccountLockedError as e:
        raise HTTPException(
            status_code=423,
            detail=(
                f"Too many failed login attempts. Try again after "
                f"{e.locked_until.strftime('%H:%M:%S UTC')}, or ask an Admin to reset your password."
            ),
        )
    except AccountDeactivatedError:
        raise HTTPException(status_code=403, detail="This account has been deactivated. Contact an Admin.")
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = create_access_token(user)
    _set_auth_cookie(response, token)
    warehouse_name = None
    if user["warehouse_id"] is not None:
        wh = query_records("SELECT warehouse_name FROM dim_warehouses WHERE warehouse_id = :w", {"w": user["warehouse_id"]})
        warehouse_name = wh[0]["warehouse_name"] if wh else None
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "role": user["role"],
            "warehouse_id": user["warehouse_id"],
            "warehouse_name": warehouse_name,
            "must_change_password": bool(user.get("must_change_password")),
        },
    }


@router.post("/logout")
def logout(response: Response):
    """Clears the httpOnly auth cookie. This has to be a server round-trip -
    unlike the old localStorage token, JavaScript can't read or delete an
    httpOnly cookie itself."""
    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, path="/")
    return {"logged_out": True}


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user)):
    warehouse_name = None
    if current_user.warehouse_id is not None:
        wh = query_records(
            "SELECT warehouse_name FROM dim_warehouses WHERE warehouse_id = :w", {"w": current_user.warehouse_id}
        )
        warehouse_name = wh[0]["warehouse_name"] if wh else None
    return {**current_user.model_dump(), "warehouse_name": warehouse_name}


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, response: Response, current_user: CurrentUser = Depends(get_current_user)):
    """The one path a must_change_password=true user can call (see
    app/auth.py's get_current_user) - lets the seeded demo accounts, or
    anyone an Admin just reset a password for, set a real password of their
    own choosing before doing anything else in the app.

    Reissues the auth cookie afterward with must_change_password baked in as
    false. Without this, the browser keeps sending the OLD cookie (minted at
    login, before this call) on every request after this one - and since
    get_current_user's gate reads must_change_password from the token's own
    claim rather than a fresh DB lookup, every other route (including the
    /auth/me call the frontend makes right after this succeeds) would still
    see the stale "true" and bounce the user straight back to
    /change-password, looking like the page just reloads/loops after a
    successful change."""
    try:
        change_own_password(current_user.user_id, req.current_password, req.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_service.log_action(current_user, "change_own_password", "user", current_user.user_id)
    new_token = create_access_token(
        {
            "username": current_user.username,
            "user_id": current_user.user_id,
            "role": current_user.role,
            "warehouse_id": current_user.warehouse_id,
            "must_change_password": False,
        }
    )
    _set_auth_cookie(response, new_token)
    return {"changed": True, "access_token": new_token}


@router.get("/warehouses")
def list_warehouses_for_registration():
    """Unauthenticated on purpose - powers the warehouse dropdown on the
    public /register page. Only returns id + name, see
    admin_service.list_warehouses_public."""
    return admin_service.list_warehouses_public()


@router.post("/register")
def register(req: RegisterRequest):
    """Self-service signup. Always creates a WAREHOUSE-role account that
    can't log in until an Admin approves it from Manage Users - see
    admin_service.register_user. Rate-limited more tightly than the general
    API (see app/rate_limit.py's _SENSITIVE_AUTH_PATHS)."""
    try:
        result = admin_service.register_user(req)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {
        "message": "Registration submitted. An Admin needs to approve your account before you can log in.",
        **result,
    }


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """Always returns the same generic response whether or not the email
    matches an active account - same anti-enumeration principle as the
    login endpoint's "incorrect username or password" message (see
    authenticate_user's docstring in app/auth.py)."""
    user = query_one(
        "SELECT user_id FROM dim_users WHERE email = :e AND is_active = true", {"e": req.email}
    )
    if user:
        raw_token = secrets.token_urlsafe(32)
        # Only the hash is stored - a database leak alone can't be used to
        # reset anyone's password (see dim_password_reset_tokens in
        # app/migrations.py).
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO dim_password_reset_tokens (user_id, token_hash, expires_at) "
                    "VALUES (:uid, :hash, :exp)"
                ),
                {"uid": user["user_id"], "hash": token_hash, "exp": expires_at},
            )
        email_service.send_password_reset_email(req.email, raw_token)
        audit_service.log_system_event("forgot_password_requested", "user", user["user_id"], req.email)
    return {"message": "If that email address is registered and active, a password reset link has been sent."}


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest):
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    row = query_one(
        "SELECT token_id, user_id, expires_at, used_at FROM dim_password_reset_tokens WHERE token_hash = :h",
        {"h": token_hash},
    )
    if not row or row["used_at"] is not None or row["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired. Request a new one.")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE dim_users SET password_hash = :hash, must_change_password = false, "
                "failed_login_count = 0, locked_until = NULL WHERE user_id = :id"
            ),
            {"hash": hash_password(req.new_password), "id": row["user_id"]},
        )
        conn.execute(text("UPDATE dim_password_reset_tokens SET used_at = NOW() WHERE token_id = :id"), {"id": row["token_id"]})

    audit_service.log_system_event("password_reset_completed", "user", row["user_id"])
    return {"reset": True}
