"""Unified alerts feed: pulls together the individual alert/risk signals
that already exist on each dashboard page (Stock, Supplier, Delivery,
Optimizer) into one list, so there's a single place to see everything that
needs attention rather than having to visit five pages to check. Powers the
sidebar alert badge and the /alerts Alerts Center page.
"""

from typing import Optional

from sqlalchemy import text

from app.auth import CurrentUser
from app.database import engine
from app.services import (
    audit_service,
    delivery_risk_service,
    settings_service,
    stock_service,
    storage_optimizer,
    supplier_service,
)
from app.services.db_utils import query_records

_SEVERITY_ORDER = {"critical": 0, "serious": 1, "warning": 2}

# dim_alert_resolutions.warehouse_id uses 0 as the "All Warehouses" scope
# instead of NULL - see migrations.py's comment on that table for why.
_ALL_WAREHOUSES_SCOPE = 0


def _resolution_scope(warehouse_id: Optional[int]) -> int:
    return warehouse_id if warehouse_id is not None else _ALL_WAREHOUSES_SCOPE


def _real_warehouses() -> list[dict]:
    """The actual warehouses (never the pseudo "all warehouses" scope) -
    used to fan the alerts feed out per-warehouse when no single warehouse
    is selected, so "All Warehouses" means every warehouse's own alerts
    rather than one blended computation over combined data."""
    return query_records("SELECT warehouse_id, warehouse_name FROM dim_warehouses ORDER BY warehouse_id")


def _hint_for_stock_alert(warehouse_id: Optional[int]) -> Optional[str]:
    """Rule-based (no ML/LLM call) "possible contributing factor" hint for a
    stockout/critical-stock alert: checks whether this warehouse's average
    supplier on-time rate is currently weak, since slow deliveries are a
    common real cause of stock shortages. Best-effort only - returns None
    rather than guessing when there isn't a clear signal."""
    try:
        performance = supplier_service.get_performance(warehouse_id)
        if not performance:
            return None
        avg_on_time = sum(p.get("on_time_delivery_pct", 100) for p in performance) / len(performance)
        medium_threshold = settings_service.get_setting_float("supplier_late_pct_medium_threshold", 15)
        if avg_on_time < (100 - medium_threshold):
            return (
                f"Possible contributing factor: average supplier on-time delivery here is "
                f"{avg_on_time:.0f}% right now - late shipments may be behind some of this."
            )
    except Exception:
        pass
    return None


def _hint_for_delivery_alert(high_delay: list[dict]) -> Optional[str]:
    """Rule-based hint for a delivery-delays-spiking alert: flags when a
    single supplier accounts for a disproportionate share of the recent
    severely-late orders."""
    try:
        supplier_counts: dict = {}
        for r in high_delay:
            name = r.get("supplier_name")
            if name:
                supplier_counts[name] = supplier_counts.get(name, 0) + 1
        if not supplier_counts:
            return None
        top_supplier, top_count = max(supplier_counts.items(), key=lambda kv: kv[1])
        if top_count >= max(2, len(high_delay) // 2):
            return f"Possible contributing factor: {top_supplier} accounts for {top_count} of these {len(high_delay)} delayed orders."
    except Exception:
        pass
    return None


def _hint_for_overstock_alert(warehouse_id: Optional[int]) -> Optional[str]:
    """Rule-based hint for an overstocked-locations alert: cross-references
    the new Dead Stock report to flag when some of that excess is likely
    unsellable rather than just seasonally slow."""
    try:
        dead = stock_service.get_dead_stock(warehouse_id)
        items = dead.get("items", [])
        if items:
            return (
                f"Possible contributing factor: {len(items)} product(s) here show zero recent sales "
                "despite carrying stock value - see the Dead Stock report on Stock Summary."
            )
    except Exception:
        pass
    return None


def _compute_alerts(warehouse_id: Optional[int] = None) -> list[dict]:
    """The raw, unfiltered alert feed - every currently-true threshold check
    across every domain, before any resolved-alert hiding is applied. Split
    out from get_all_alerts() so get_resolved_alerts() can also compute this
    (to report each resolved alert's *current* live count, for the "did this
    already reappear on its own?" status shown in the Resolved tab) without
    duplicating all of the per-domain alert logic.

    warehouse_id=None ("All Warehouses") does NOT recompute every threshold
    against blended, cross-warehouse data - a warehouse-specific problem
    (e.g. Kimmage alone running a high stockout rate) can average away to
    nothing once mixed with two healthy warehouses, and would silently never
    surface to an admin looking at "All Warehouses". Instead this fans out
    to each real warehouse's OWN alerts (recursing into the branch below
    once per warehouse) and merges them, tagging every alert with the real
    warehouse it actually came from - the same alert title can legitimately
    appear more than once, once per warehouse where it's actually true."""
    if warehouse_id is None:
        merged: list[dict] = []
        for w in _real_warehouses():
            wid = w["warehouse_id"]
            for a in _compute_alerts(wid):
                merged.append({**a, "warehouse_id": wid, "warehouse_name": w["warehouse_name"]})
        merged.sort(key=lambda a: (_SEVERITY_ORDER.get(a["level"], 3), a.get("warehouse_name") or ""))
        return merged

    alerts: list[dict] = []

    for a in stock_service.get_alerts(warehouse_id):
        hint = _hint_for_stock_alert(warehouse_id) if a.get("level") == "critical" else None
        alerts.append({**a, "source": "Stock Summary", "link": "/stock", "hint": hint})

    high_threshold = settings_service.get_setting_float("supplier_late_pct_high_threshold", 25)
    try:
        performance = supplier_service.get_performance(warehouse_id)
        high_risk_suppliers = [p for p in performance if p.get("risk_level") == "High"]
        if high_risk_suppliers:
            names = ", ".join(p["supplier_name"] for p in high_risk_suppliers[:5])
            alerts.append(
                {
                    "level": "serious",
                    "title": "High-Risk Suppliers",
                    "detail": f"{len(high_risk_suppliers)} supplier(s) rated High risk (late % > {high_threshold}%): {names}",
                    "count": len(high_risk_suppliers),
                    "source": "Supplier Summary",
                    "link": "/suppliers",
                    "hint": None,
                }
            )
    except Exception:
        pass  # alerts feed should degrade gracefully rather than 500 the whole page

    try:
        risky = delivery_risk_service.get_risky_orders(50, warehouse_id)
        alert_count_threshold = int(settings_service.get_setting_float("delivery_high_risk_alert_count", 3))
        high_delay = [r for r in risky if r.get("risk_level") == "HIGH"]
        if len(high_delay) >= alert_count_threshold:
            alerts.append(
                {
                    "level": "critical",
                    "title": "Delivery Delays Spiking",
                    "detail": f"{len(high_delay)} recent purchase orders were delivered severely late.",
                    "count": len(high_delay),
                    "source": "Delivery Risk Predictor",
                    "link": "/delivery",
                    "hint": _hint_for_delivery_alert(high_delay),
                }
            )
    except delivery_risk_service.ModelNotTrainedError:
        pass
    except Exception:
        pass

    try:
        overstock_threshold = settings_service.get_setting_float("optimizer_overstocked_threshold", 90)
        overstocked = storage_optimizer.get_overstocked(overstock_threshold, warehouse_id)
        if overstocked:
            alerts.append(
                {
                    "level": "warning",
                    "title": "Overstocked Locations",
                    "detail": f"{len(overstocked)} storage location(s) are above {overstock_threshold:.0f}% capacity.",
                    "count": len(overstocked),
                    "source": "Stock Optimizer",
                    "link": "/storage",
                    "hint": _hint_for_overstock_alert(warehouse_id),
                }
            )

        pending = storage_optimizer.get_pending_placement(500)
        if pending:
            alerts.append(
                {
                    "level": "warning",
                    "title": "New Products Awaiting Placement",
                    "detail": f"{len(pending)} product(s) need a storage location assigned.",
                    "count": len(pending),
                    "source": "Stock Optimizer",
                    "link": "/storage",
                    "hint": None,
                }
            )
    except Exception:
        pass

    alerts.sort(key=lambda a: _SEVERITY_ORDER.get(a["level"], 3))
    return alerts


def get_all_alerts(warehouse_id: Optional[int] = None) -> list[dict]:
    alerts = _compute_alerts(warehouse_id)

    if warehouse_id is None:
        # Merged "All Warehouses" feed: each alert already carries the real
        # warehouse it came from (see _compute_alerts), so resolution is
        # checked per THAT real warehouse's own scope rather than the single
        # pseudo "all warehouses" scope 0 - resolving Kimmage's Overstocked
        # Locations alert should never also hide the same alert firing at
        # Finglas. One query for every warehouse's resolutions, grouped by
        # scope, rather than a query per alert.
        rows = query_records("SELECT warehouse_id, alert_title, resolved_count FROM dim_alert_resolutions")
        resolved_by_scope: dict[int, dict[str, int]] = {}
        for r in rows:
            resolved_by_scope.setdefault(r["warehouse_id"], {})[r["alert_title"]] = r["resolved_count"]
        return [
            a
            for a in alerts
            if resolved_by_scope.get(_resolution_scope(a.get("warehouse_id")), {}).get(a["title"]) != a.get("count")
        ]

    # Drop any alert an admin has already resolved for this exact warehouse
    # scope, *unless* its count has since changed - see resolve_alert()
    # below for why a changed count means it comes back automatically.
    resolved = {
        r["alert_title"]: r["resolved_count"]
        for r in query_records(
            "SELECT alert_title, resolved_count FROM dim_alert_resolutions WHERE warehouse_id = :wid",
            {"wid": _resolution_scope(warehouse_id)},
        )
    }
    return [a for a in alerts if resolved.get(a["title"]) != a.get("count")]


def _severity_counts(alerts: list[dict]) -> dict:
    counts = {"critical": 0, "serious": 0, "warning": 0}
    for a in alerts:
        if a["level"] in counts:
            counts[a["level"]] += 1
    counts["total"] = sum(counts.values())
    return counts


def resolve_alert(title: str, warehouse_id: Optional[int], count: int, actor: CurrentUser) -> dict:
    """Admin's acknowledgement of one currently-showing alert. These alerts
    aren't persisted events - each one is a live threshold check recomputed
    on every request (see get_all_alerts above), so there's no row to mark
    resolved the way Supplier Returns does. Instead this snapshots the
    alert's own `count` at the moment it's resolved; get_all_alerts hides
    that alert (matched by title + warehouse scope) for as long as it keeps
    recomputing to exactly this same count, and it reappears on its own the
    moment the count changes in either direction - so a stable,
    already-seen problem stays quiet, but any real movement (better or
    worse) surfaces it again without anyone having to remember to
    re-check."""
    scope = _resolution_scope(warehouse_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_alert_resolutions (alert_title, warehouse_id, resolved_count, resolved_at, resolved_by)
                VALUES (:title, :wid, :count, NOW(), :by)
                ON CONFLICT (alert_title, warehouse_id)
                DO UPDATE SET resolved_count = :count, resolved_at = NOW(), resolved_by = :by
                """
            ),
            {"title": title, "wid": scope, "count": count, "by": actor.username},
        )
    audit_service.log_action(
        actor,
        "RESOLVE_ALERT",
        entity_type="alert",
        entity_id=title,
        details=f"warehouse_id={scope}, count={count}",
    )
    return {"title": title, "warehouse_id": warehouse_id, "resolved_count": count}


def get_resolved_alerts(warehouse_id: Optional[int] = None) -> list[dict]:
    """Every alert an admin has resolved for this warehouse scope, most
    recently resolved first - powers the Alerts Center's "Resolved" tab.
    Each row also reports the alert's *current* live count so the UI can
    show whether it's still quietly hidden, has already reappeared on its
    own (see resolve_alert()'s count-change behavior), or its underlying
    condition has cleared entirely - useful context before an admin decides
    whether rolling one back actually does anything.

    warehouse_id=None ("All Warehouses") lists resolutions across every real
    warehouse (each tagged with which one), matching get_all_alerts()'s own
    per-warehouse merge - a resolution made from the merged Active tab is
    always stored under its own real warehouse, never the legacy pseudo
    "all warehouses" scope 0."""
    if warehouse_id is None:
        rows = query_records(
            """
            SELECT alert_resolution_id, alert_title, warehouse_id, resolved_count, resolved_at, resolved_by
            FROM dim_alert_resolutions
            WHERE warehouse_id != :all_scope
            ORDER BY resolved_at DESC
            """,
            {"all_scope": _ALL_WAREHOUSES_SCOPE},
        )
        if not rows:
            return []
        warehouse_names = {w["warehouse_id"]: w["warehouse_name"] for w in _real_warehouses()}
        current_by_key = {(a.get("warehouse_id"), a["title"]): a.get("count") for a in _compute_alerts(None)}
        result = []
        for r in rows:
            current_count = current_by_key.get((r["warehouse_id"], r["alert_title"]))
            result.append(
                {
                    "alert_resolution_id": r["alert_resolution_id"],
                    "title": r["alert_title"],
                    "warehouse_id": r["warehouse_id"],
                    "warehouse_name": warehouse_names.get(r["warehouse_id"]),
                    "resolved_count": r["resolved_count"],
                    "resolved_at": r["resolved_at"],
                    "resolved_by": r["resolved_by"],
                    "current_count": current_count,
                    "reappeared": current_count is not None and current_count != r["resolved_count"],
                }
            )
        return result

    scope = _resolution_scope(warehouse_id)
    rows = query_records(
        """
        SELECT alert_resolution_id, alert_title, resolved_count, resolved_at, resolved_by
        FROM dim_alert_resolutions
        WHERE warehouse_id = :wid
        ORDER BY resolved_at DESC
        """,
        {"wid": scope},
    )
    if not rows:
        return []
    current_by_title = {a["title"]: a.get("count") for a in _compute_alerts(warehouse_id)}
    result = []
    for r in rows:
        current_count = current_by_title.get(r["alert_title"])
        result.append(
            {
                "alert_resolution_id": r["alert_resolution_id"],
                "title": r["alert_title"],
                "warehouse_id": warehouse_id,
                "resolved_count": r["resolved_count"],
                "resolved_at": r["resolved_at"],
                "resolved_by": r["resolved_by"],
                "current_count": current_count,
                # None -> the alert isn't firing at all right now (its
                # underlying condition cleared). A mismatched number -> it
                # already changed and came back on its own; rolling back is
                # then just history cleanup, not a functional undo.
                "reappeared": current_count is not None and current_count != r["resolved_count"],
            }
        )
    return result


def rollback_alert(title: str, warehouse_id: Optional[int], actor: CurrentUser) -> dict:
    """Undo an earlier resolve_alert() call - e.g. an admin resolved the
    wrong alert by mistake. Deletes the resolution row outright (unlike
    resolve_alert, there's nothing to snapshot), so if the alert's
    underlying condition still holds, it shows up in the Active tab again
    immediately on the next poll."""
    scope = _resolution_scope(warehouse_id)
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM dim_alert_resolutions WHERE alert_title = :title AND warehouse_id = :wid"),
            {"title": title, "wid": scope},
        )
    if result.rowcount == 0:
        raise ValueError("No resolved alert found matching that title and warehouse scope.")
    audit_service.log_action(
        actor,
        "ROLLBACK_ALERT",
        entity_type="alert",
        entity_id=title,
        details=f"warehouse_id={scope}",
    )
    return {"title": title, "warehouse_id": warehouse_id, "rolled_back": True}


def preview_settings_impact(overrides: dict, warehouse_id: Optional[int] = None) -> dict:
    """Powers the Settings page's "what would change" preview: recomputes
    the alert counts once with today's saved thresholds and once with the
    proposed `overrides`, without writing anything. See
    settings_service.override() for how the swap works."""
    current = _severity_counts(get_all_alerts(warehouse_id))
    with settings_service.override(overrides):
        proposed = _severity_counts(get_all_alerts(warehouse_id))
    return {"current": current, "proposed": proposed}
