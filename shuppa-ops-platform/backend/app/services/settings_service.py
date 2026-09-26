"""Dashboard-configurable settings (alert thresholds etc.), stored in
dim_settings as plain key/value text so Admin can tune them from the UI
instead of them being hardcoded constants in Python. Defaults are seeded by
app/migrations.py (and scripts/seed_database.py on a full reseed).

Also supports a "preview" mode: the Settings page wants to show how many
alerts would fire under a *hypothetical* set of thresholds, before Admin
saves them. Rather than threading an `overrides` parameter through every
threshold read in stock_service/supplier_service/alerts_service, `override()`
below sets values in a contextvar that get_setting()/get_setting_float()
check first - it's request-scoped (a contextvar, not a global), so it can't
leak between concurrent requests, and callers outside a `with override(...)`
block behave exactly as before.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from sqlalchemy import text

from app.database import engine
from app.services.db_utils import query_records

_override_ctx: ContextVar[Optional[dict]] = ContextVar("settings_override", default=None)


@contextmanager
def override(overrides: dict):
    """Temporarily makes get_setting()/get_setting_float() prefer values from
    `overrides` (falling back to the real stored value for any key not
    present in it). Used by the Settings-page "preview impact" endpoint to
    compute alert counts under proposed thresholds without saving them."""
    token = _override_ctx.set({k: str(v) for k, v in overrides.items()})
    try:
        yield
    finally:
        _override_ctx.reset(token)


def get_all_settings() -> dict:
    rows = query_records("SELECT setting_key, setting_value, updated_at FROM dim_settings ORDER BY setting_key")
    return {r["setting_key"]: r["setting_value"] for r in rows}


def get_all_settings_detailed() -> list[dict]:
    return query_records("SELECT setting_key, setting_value, updated_at FROM dim_settings ORDER BY setting_key")


def get_setting(key: str, default: str) -> str:
    overrides = _override_ctx.get()
    if overrides and key in overrides:
        return overrides[key]
    rows = query_records("SELECT setting_value FROM dim_settings WHERE setting_key = :k", {"k": key})
    return rows[0]["setting_value"] if rows else default


def get_setting_float(key: str, default: float) -> float:
    val = get_setting(key, str(default))
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def update_settings(updates: dict) -> dict:
    with engine.begin() as conn:
        for key, value in updates.items():
            conn.execute(
                text(
                    "INSERT INTO dim_settings (setting_key, setting_value, updated_at) VALUES (:k, :v, NOW()) "
                    "ON CONFLICT (setting_key) DO UPDATE SET setting_value = :v, updated_at = NOW()"
                ),
                {"k": key, "v": str(value)},
            )
    return get_all_settings()
