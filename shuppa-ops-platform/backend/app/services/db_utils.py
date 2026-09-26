"""Small helpers shared by every router/service so query code stays uniform."""

from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text

from app.database import engine


def query_records(sql: str, params: Optional[dict[str, Any]] = None) -> list[dict]:
    """Run a parameterized SELECT and return a list of plain dicts."""
    with engine.connect() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row._mapping) for row in result]


def query_one(sql: str, params: Optional[dict[str, Any]] = None) -> dict:
    """Run a parameterized SELECT expected to return exactly one row."""
    rows = query_records(sql, params)
    return rows[0] if rows else {}


def query_df(sql: str, params: Optional[dict[str, Any]] = None) -> pd.DataFrame:
    """Run a parameterized SELECT and return a DataFrame (handy for pandas-side math)."""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def warehouse_filter_clause(warehouse_id: Optional[int], column: str = "warehouse_id") -> str:
    """Returns a SQL fragment ("" or "AND <column> = :warehouse_id") for optional filters."""
    return f"AND {column} = :warehouse_id" if warehouse_id is not None else ""


def date_range_clause(
    date_from: Optional[str],
    date_to: Optional[str],
    column: str = "date_id",
    from_param: str = "date_from",
    to_param: str = "date_to",
) -> str:
    """Returns a SQL fragment for the dashboard-wide date filter.

    Powers the "Before" (date_to only), "After" (date_from only) and
    "Between" (both) filter modes exposed in the UI - the frontend always
    resolves whichever mode is picked down to a date_from/date_to pair, so
    the backend only needs to know about bounds, not modes.
    """
    clauses = []
    if date_from:
        clauses.append(f"{column} >= :{from_param}")
    if date_to:
        clauses.append(f"{column} <= :{to_param}")
    return (" AND " + " AND ".join(clauses)) if clauses else ""


def _parse_date(value: Optional[str]):
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def previous_period_window(
    date_from: Optional[str], date_to: Optional[str], default_days: int = 30
) -> tuple[Optional[str], Optional[str]]:
    """Powers the "vs last period" comparison on KPI cards.

    - If the caller has an explicit date range active (from the dashboard's
      Before/After/Between filter), the "previous period" is the
      immediately-preceding window of the same length.
    - If no range is active (the default "all dates" view), compares the
      trailing `default_days` days against the `default_days` before that,
      so KPI cards always have a meaningful comparison rather than "vs all
      of history", which would rarely move.

    Returns (prev_from, prev_to) as ISO date strings, or (None, None) when
    there's no sensible "today" to anchor an implicit window to (that case
    is handled by the caller falling back to a DB-side MAX(date) anchor).
    """
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)

    if d_from and d_to:
        length = (d_to - d_from).days + 1
        prev_to = d_from - timedelta(days=1)
        prev_from = prev_to - timedelta(days=length - 1)
        return prev_from.isoformat(), prev_to.isoformat()
    if d_to and not d_from:
        # "Before" mode - previous period is the same-length window right before it.
        prev_to = d_to - timedelta(days=default_days)
        prev_from = prev_to - timedelta(days=default_days - 1)
        return prev_from.isoformat(), prev_to.isoformat()
    if d_from and not d_to:
        # "After" mode - open-ended, so there's no fixed-length window to mirror.
        return None, None
    # No range active at all - caller anchors the implicit window to the
    # data's own MAX(date) rather than wall-clock "today" (the seeded demo
    # data isn't necessarily current), so this returns None and the calling
    # service builds the SQL window itself.
    return None, None


def resolve_comparison_window(
    date_from: Optional[str],
    date_to: Optional[str],
    max_date_query: str,
    max_date_params: Optional[dict[str, Any]] = None,
    default_days: int = 30,
) -> tuple[Optional[str], Optional[str]]:
    """Resolves the (prev_from, prev_to) window for a KPI card's "vs previous
    period" comparison, for the common case where a service needs
    previous_period_window()'s "no explicit filter" gap filled in by
    anchoring to the underlying table's own latest date.

    `max_date_query` should be a SELECT that returns a single column aliased
    `d` (e.g. "SELECT MAX(date_id) AS d FROM fact_sales_daily WHERE ...")
    already scoped to whatever warehouse filter the caller needs.
    """
    prev_from, prev_to = previous_period_window(date_from, date_to, default_days)
    if prev_from and prev_to:
        return prev_from, prev_to
    if date_from and not date_to:
        # Open-ended "After" filter - no fixed-length window to mirror.
        return None, None
    if date_from or date_to:
        # date_to-only ("Before") mode already handled above by
        # previous_period_window; reaching here means it had nothing to
        # anchor to (e.g. malformed input) - bail out rather than guess.
        return None, None
    row = query_one(max_date_query, max_date_params or {})
    max_d = row.get("d") if row else None
    if not max_d:
        return None, None
    max_d = _parse_date(max_d)
    prev_to = max_d - timedelta(days=default_days)
    prev_from = prev_to - timedelta(days=default_days - 1)
    return prev_from.isoformat(), prev_to.isoformat()


def compute_deltas(current: dict, previous: dict, keys: list[str]) -> dict:
    """Builds a {key: {previous, absolute, pct}} map for KPI-card "vs last
    period" indicators. A key is omitted (value None) when either side is
    missing/non-numeric rather than raising, since a comparison that can't be
    computed shouldn't break the whole KPI response."""
    deltas: dict[str, Any] = {}
    for key in keys:
        cur_val = current.get(key)
        prev_val = previous.get(key)
        if cur_val is None or prev_val is None:
            deltas[key] = None
            continue
        try:
            cur_f = float(cur_val)
            prev_f = float(prev_val)
        except (TypeError, ValueError):
            deltas[key] = None
            continue
        absolute = cur_f - prev_f
        pct = (absolute / prev_f * 100) if prev_f else None
        deltas[key] = {
            "previous": prev_f,
            "absolute": round(absolute, 2),
            "pct": round(pct, 2) if pct is not None else None,
        }
    return deltas
