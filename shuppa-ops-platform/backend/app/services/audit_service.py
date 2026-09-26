"""Admin action audit log (dim_audit_log). Every mutating Admin endpoint
calls log_action() so there's a record of who added/changed what and when -
see app/routers/admin.py."""

from typing import Optional

from sqlalchemy import text

from app.auth import CurrentUser
from app.database import engine
from app.services.db_utils import query_records


def log_action(
    user: CurrentUser,
    action: str,
    entity_type: Optional[str] = None,
    entity_id=None,
    details: Optional[str] = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_audit_log (user_id, username, action, entity_type, entity_id, details)
                VALUES (:uid, :uname, :action, :etype, :eid, :details)
                """
            ),
            {
                "uid": user.user_id,
                "uname": user.username,
                "action": action,
                "etype": entity_type,
                "eid": str(entity_id) if entity_id is not None else None,
                "details": details,
            },
        )


def log_system_event(
    action: str,
    entity_type: Optional[str] = None,
    entity_id=None,
    details: Optional[str] = None,
) -> None:
    """Same idea as log_action, for events with no logged-in actor to
    attribute them to - self-service registration, a forgot-password
    request, and a completed password reset all happen before/without
    authentication. Recorded as an anonymous system entry (user_id NULL)
    rather than skipped entirely, so these security-relevant events still
    show up in the Admin Audit Log page instead of leaving a blind spot."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_audit_log (user_id, username, action, entity_type, entity_id, details)
                VALUES (NULL, '(anonymous)', :action, :etype, :eid, :details)
                """
            ),
            {
                "action": action,
                "etype": entity_type,
                "eid": str(entity_id) if entity_id is not None else None,
                "details": details,
            },
        )


def get_audit_log(
    limit: int = 100,
    username: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    clauses = []
    params: dict = {"limit": limit}
    if username:
        clauses.append("username = :username")
        params["username"] = username
    if action:
        clauses.append("action = :action")
        params["action"] = action
    if date_from:
        clauses.append("created_at >= :date_from")
        params["date_from"] = date_from
    if date_to:
        # date_to is a plain date (no time component) from the UI's date
        # picker - add a day so "to 2026-09-22" includes that whole day
        # rather than stopping at midnight.
        clauses.append("created_at < (:date_to::date + INTERVAL '1 day')")
        params["date_to"] = date_to
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return query_records(
        f"""
        SELECT audit_id, created_at, username, action, entity_type, entity_id, details
        FROM dim_audit_log
        {where}
        ORDER BY created_at DESC
        LIMIT :limit
        """,
        params,
    )


def get_distinct_actions() -> list[str]:
    """Powers the Audit Log page's action filter dropdown."""
    rows = query_records("SELECT DISTINCT action FROM dim_audit_log ORDER BY action")
    return [r["action"] for r in rows]


def get_distinct_usernames() -> list[str]:
    """Powers the Audit Log page's user filter dropdown."""
    rows = query_records("SELECT DISTINCT username FROM dim_audit_log ORDER BY username")
    return [r["username"] for r in rows]
