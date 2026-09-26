from typing import Optional

from sqlalchemy import text

from app.auth import CurrentUser
from app.database import engine
from app.models.schemas import DraftPurchaseOrderRequest
from app.services import audit_service, settings_service
from app.services.db_utils import (
    compute_deltas,
    date_range_clause,
    query_df,
    query_one,
    query_records,
    resolve_comparison_window,
    warehouse_filter_clause,
)

_KPI_DELTA_KEYS = [
    "total_inventory_value",
    "stockout_pct",
    "stockout_count",
    "healthy_pct",
    "healthy_count",
    "critical_count",
    "inventory_at_risk_value",
    "excess_inventory_value",
]


def _latest_date(warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None) -> str:
    clause = warehouse_filter_clause(warehouse_id) + date_range_clause(date_from, date_to)
    row = query_one(
        f"SELECT MAX(date_id) AS d FROM fact_inventory_daily WHERE 1=1 {clause}",
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    return row["d"]


def _snapshot_at(as_of, warehouse_id: Optional[int] = None) -> dict:
    clause = warehouse_filter_clause(warehouse_id)
    row = query_one(
        f"""
        SELECT
            COUNT(*) AS total_products,
            COUNT(*) FILTER (WHERE stock_status = 'HEALTHY') AS healthy_count,
            COUNT(*) FILTER (WHERE stock_status = 'LOW') AS low_count,
            COUNT(*) FILTER (WHERE stock_status = 'CRITICAL') AS critical_count,
            COUNT(*) FILTER (WHERE stock_status = 'OVERSTOCK') AS overstock_count,
            COUNT(*) FILTER (WHERE stock_on_hand = 0) AS stockout_count,
            COALESCE(SUM(stock_value) FILTER (WHERE stock_status IN ('LOW','CRITICAL')), 0) AS inventory_at_risk_value,
            COALESCE(SUM(stock_value) FILTER (WHERE stock_status = 'OVERSTOCK'), 0) AS excess_inventory_value,
            COALESCE(SUM(stock_value), 0) AS total_inventory_value
        FROM fact_inventory_daily
        WHERE date_id = :as_of {clause}
        """,
        {"as_of": as_of, "warehouse_id": warehouse_id},
    )
    total = row["total_products"] or 1
    row["stockout_pct"] = round(100.0 * row["stockout_count"] / total, 2)
    row["healthy_pct"] = round(100.0 * row["healthy_count"] / total, 2)
    row["low_pct"] = round(100.0 * row["low_count"] / total, 2)
    row["critical_pct"] = round(100.0 * row["critical_count"] / total, 2)
    row["overstock_pct"] = round(100.0 * row["overstock_count"] / total, 2)
    return row


def get_summary(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    as_of = _latest_date(warehouse_id, date_from, date_to)
    row = _snapshot_at(as_of, warehouse_id)
    row["as_of"] = as_of

    # This is a point-in-time snapshot (not a range aggregate), so "vs
    # previous period" compares against the snapshot nearest the end of the
    # previous window rather than re-aggregating over a range.
    clause = warehouse_filter_clause(warehouse_id)
    prev_from, prev_to = resolve_comparison_window(
        date_from,
        date_to,
        f"SELECT MAX(date_id) AS d FROM fact_inventory_daily WHERE 1=1 {clause}",
        {"warehouse_id": warehouse_id},
    )
    if prev_to:
        nearest = query_one(
            f"SELECT MAX(date_id) AS d FROM fact_inventory_daily WHERE date_id <= :prev_to {clause}",
            {"prev_to": prev_to, "warehouse_id": warehouse_id},
        )
        prev_as_of = nearest.get("d") if nearest else None
        if prev_as_of and str(prev_as_of) != str(as_of):
            prev_row = _snapshot_at(prev_as_of, warehouse_id)
            row["comparison"] = {
                "previous_as_of": prev_as_of,
                "deltas": compute_deltas(row, prev_row, _KPI_DELTA_KEYS),
            }
        else:
            row["comparison"] = None
    else:
        row["comparison"] = None
    return row


def get_alerts(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    summary = get_summary(warehouse_id, date_from, date_to)
    stockout_threshold = settings_service.get_setting_float("stockout_pct_threshold", 5.0)
    overstock_threshold = settings_service.get_setting_float("overstock_value_threshold", 200_000)
    alerts = []
    if summary["stockout_pct"] > stockout_threshold:
        alerts.append(
            {
                "level": "critical",
                "title": "Stockout Warning",
                "detail": f"Stockout rate is {summary['stockout_pct']}% (exceeds the {stockout_threshold}% threshold).",
                "count": summary["stockout_count"],
            }
        )
    if summary["excess_inventory_value"] > overstock_threshold:
        alerts.append(
            {
                "level": "serious",
                "title": "Excess Inventory Alert",
                "detail": f"Overstock value is €{summary['excess_inventory_value']:,.0f} (exceeds €{overstock_threshold:,.0f}).",
                "count": summary["overstock_count"],
            }
        )
    if summary["critical_count"] > 0:
        alerts.append(
            {
                "level": "critical",
                "title": "Critical Stock Alert",
                "detail": f"{summary['critical_count']} product/warehouse lines are critically low on stock.",
                "count": summary["critical_count"],
            }
        )
    return alerts


def get_trend(
    days: int = 31,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id)
    if date_from or date_to:
        window_clause = date_range_clause(date_from, date_to)
        return query_records(
            f"""
            SELECT
                date_id,
                COUNT(*) FILTER (WHERE stock_status = 'HEALTHY') AS healthy,
                COUNT(*) FILTER (WHERE stock_status = 'LOW') AS low,
                COUNT(*) FILTER (WHERE stock_status = 'OVERSTOCK') AS overstock,
                COUNT(*) FILTER (WHERE stock_status = 'CRITICAL') AS critical
            FROM fact_inventory_daily
            WHERE 1=1 {clause} {window_clause}
            GROUP BY date_id
            ORDER BY date_id
            """,
            {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
        )
    return query_records(
        f"""
        WITH bounds AS (SELECT MAX(date_id) AS max_d FROM fact_inventory_daily)
        SELECT
            date_id,
            COUNT(*) FILTER (WHERE stock_status = 'HEALTHY') AS healthy,
            COUNT(*) FILTER (WHERE stock_status = 'LOW') AS low,
            COUNT(*) FILTER (WHERE stock_status = 'OVERSTOCK') AS overstock,
            COUNT(*) FILTER (WHERE stock_status = 'CRITICAL') AS critical
        FROM fact_inventory_daily, bounds
        WHERE date_id > max_d - (:days || ' days')::interval {clause}
        GROUP BY date_id
        ORDER BY date_id
        """,
        {"days": days, "warehouse_id": warehouse_id},
    )


def get_distribution(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    as_of = _latest_date(warehouse_id, date_from, date_to)
    clause = warehouse_filter_clause(warehouse_id)
    return query_records(
        f"""
        SELECT stock_status, COUNT(*) AS count
        FROM fact_inventory_daily
        WHERE date_id = :as_of {clause}
        GROUP BY stock_status
        """,
        {"as_of": as_of, "warehouse_id": warehouse_id},
    )


def get_low_stock(
    limit: int = 20,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    as_of = _latest_date(warehouse_id, date_from, date_to)
    clause = warehouse_filter_clause(warehouse_id, "i.warehouse_id")
    df = query_df(
        f"""
        WITH recent_sales AS (
            SELECT product_id, warehouse_id, AVG(units_sold) AS avg_daily_units
            FROM fact_sales_daily
            WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days'
            GROUP BY product_id, warehouse_id
        )
        SELECT
            p.product_name,
            i.warehouse_id,
            i.stock_status,
            i.stock_on_hand,
            i.reorder_point,
            i.stock_value,
            COALESCE(s.avg_daily_units, 0) AS avg_daily_units
        FROM fact_inventory_daily i
        JOIN dim_products p ON p.product_id = i.product_id
        LEFT JOIN recent_sales s ON s.product_id = i.product_id AND s.warehouse_id = i.warehouse_id
        WHERE i.date_id = :as_of AND i.stock_status IN ('LOW', 'CRITICAL') {clause}
        ORDER BY i.stock_on_hand ASC
        LIMIT :limit
        """,
        {"as_of": as_of, "limit": limit, "warehouse_id": warehouse_id},
    )
    if df.empty:
        return []
    df["days_of_stock_left"] = df.apply(
        lambda r: round(r["stock_on_hand"] / r["avg_daily_units"], 1) if r["avg_daily_units"] > 0 else None,
        axis=1,
    )
    records = df.to_dict(orient="records")
    # `df.apply` above mixes real numbers with `None` in the same column,
    # which makes pandas upcast the whole column to float64 - silently
    # turning every intended `None` (products with zero recent sales) into
    # `NaN` instead. FastAPI/Starlette's default JSONResponse raises
    # `ValueError: Out of range float values are not JSON compliant` the
    # moment a NaN reaches json.dumps(), and since that happens while the
    # response body is being serialized (after this function has already
    # returned), nothing in the router's own try/except catches it - the
    # connection just drops, which the browser reports as a bare "Failed to
    # fetch" rather than a normal error. `v != v` is a plain, import-free way
    # to detect NaN (it's the only float that isn't equal to itself);
    # converting it back to a real `None` here fixes this field and guards
    # any other numeric column in this response against the same failure.
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and v != v:
                r[k] = None
    return records


def get_rebalancing_suggestions(limit: int = 50, warehouse_id: Optional[int] = None) -> list[dict]:
    """Cross-warehouse view: for every product that's LOW/CRITICAL in one
    warehouse, checks whether either of the other two warehouses is
    carrying a comfortable surplus of the same product right now (OVERSTOCK,
    or stock on hand more than 1.5x its own reorder point) - a manual
    transfer between warehouses could resolve a shortfall faster than
    waiting on a new purchase order from a supplier.

    This only *suggests* a transfer - nothing here moves stock or creates a
    real inter-warehouse shipment. `warehouse_id` filters the results to
    shortfalls in that one warehouse (this is how a WAREHOUSE-role login
    sees it, via effective_warehouse_id) while leaving None shows every
    warehouse's shortfalls, which only ADMIN logins can see.
    """
    as_of = query_one("SELECT MAX(date_id) AS d FROM fact_inventory_daily").get("d")
    df = query_df(
        """
        SELECT i.product_id, p.product_name, i.warehouse_id, i.stock_status,
               i.stock_on_hand, i.reorder_point
        FROM fact_inventory_daily i
        JOIN dim_products p ON p.product_id = i.product_id
        WHERE i.date_id = :as_of
        """,
        {"as_of": as_of},
    )
    if df.empty:
        return []

    results = []
    for product_id, group in df.groupby("product_id"):
        short = group[group["stock_status"].isin(["LOW", "CRITICAL"])]
        if short.empty:
            continue
        surplus = group[
            (group["stock_status"] == "OVERSTOCK")
            | (group["stock_on_hand"] > (group["reorder_point"].fillna(0) * 1.5))
        ]
        for _, s in short.iterrows():
            candidates = surplus[surplus["warehouse_id"] != s["warehouse_id"]]
            if candidates.empty:
                continue
            best = candidates.sort_values("stock_on_hand", ascending=False).iloc[0]
            transferable = int(max(0, best["stock_on_hand"] - (best["reorder_point"] or 0)))
            if transferable <= 0:
                continue
            needed = int(max(0, (s["reorder_point"] or 0) - s["stock_on_hand"]))
            results.append(
                {
                    "product_id": int(product_id),
                    "product_name": s["product_name"],
                    "short_warehouse_id": int(s["warehouse_id"]),
                    "short_stock_status": s["stock_status"],
                    "short_stock_on_hand": int(s["stock_on_hand"]),
                    "needed_units": needed,
                    "surplus_warehouse_id": int(best["warehouse_id"]),
                    "surplus_stock_on_hand": int(best["stock_on_hand"]),
                    "suggested_transfer_qty": min(transferable, needed) if needed > 0 else transferable,
                }
            )

    if warehouse_id is not None:
        results = [r for r in results if r["short_warehouse_id"] == warehouse_id]
    results.sort(key=lambda r: r["needed_units"], reverse=True)
    return results[:limit]


def get_dead_stock(warehouse_id: Optional[int] = None, limit: int = 50) -> dict:
    """Products carrying stock value but with (near) zero sales over the
    trailing `dead_stock_days_threshold` days (default 60, Admin ->
    Settings) - money and shelf space tied up in inventory nobody's buying.
    Sorted by stock value tied up, descending, so the biggest offenders
    surface first. Returns both the list and a total-value-tied-up rollup
    for a headline stat."""
    days = int(settings_service.get_setting_float("dead_stock_days_threshold", 60))
    as_of = query_one("SELECT MAX(date_id) AS d FROM fact_inventory_daily").get("d")
    clause = warehouse_filter_clause(warehouse_id, "i.warehouse_id")
    df = query_df(
        f"""
        WITH recent_sales AS (
            SELECT product_id, warehouse_id, SUM(units_sold) AS units_sold_recent
            FROM fact_sales_daily
            WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '{days} days'
            GROUP BY product_id, warehouse_id
        )
        SELECT i.product_id, p.product_name, p.category, i.warehouse_id,
               i.stock_on_hand, i.stock_value,
               COALESCE(r.units_sold_recent, 0) AS units_sold_recent
        FROM fact_inventory_daily i
        JOIN dim_products p ON p.product_id = i.product_id
        LEFT JOIN recent_sales r ON r.product_id = i.product_id AND r.warehouse_id = i.warehouse_id
        WHERE i.date_id = :as_of AND i.stock_on_hand > 0 AND COALESCE(r.units_sold_recent, 0) = 0 {clause}
        ORDER BY i.stock_value DESC
        LIMIT :limit
        """,
        {"as_of": as_of, "limit": limit, "warehouse_id": warehouse_id},
    )
    if df.empty:
        return {"items": [], "total_value_tied_up": 0, "dead_stock_days_threshold": days}
    return {
        "items": df.to_dict(orient="records"),
        "total_value_tied_up": round(float(df["stock_value"].sum()), 2),
        "dead_stock_days_threshold": days,
    }


def get_margin_density(limit: int = 50, category: Optional[str] = None) -> list[dict]:
    """Profit per cm3 of a product's OWN volume (gross_profit / volume_cm3) -
    flags bulky, low-margin products that occupy a lot of space for little
    return, versus compact, high-margin ones. Sorted ascending (worst
    space-efficiency first) since that's the actionable end of the list.

    This is deliberately a product-level metric, not a literal
    "per-shelf-slot" figure - this app has no product-to-slot assignment
    table recording which exact location holds which product, so there's no
    way to compute "the margin this specific slot is generating" for real.
    """
    where = "WHERE d.volume_cm3 > 0" + (" AND p.category = :category" if category else "")
    df = query_df(
        f"""
        SELECT p.product_id, p.product_name, p.category, p.gross_profit,
               d.volume_cm3, d.length_cm, d.width_cm, d.height_cm
        FROM dim_products p
        JOIN dim_product_dimensions d ON d.product_id = p.product_id
        {where}
        """,
        {"category": category},
    )
    if df.empty:
        return []
    df["margin_per_cm3"] = (df["gross_profit"] / df["volume_cm3"]).round(4)
    df = df.sort_values("margin_per_cm3", ascending=True)
    return df.head(limit).to_dict(orient="records")


def create_draft_po(req: DraftPurchaseOrderRequest, actor: CurrentUser) -> dict:
    """One-click "Draft PO" action on a Reorder Suggestion row. Records
    intent only (who/what/how much/for which warehouse) in
    dim_draft_purchase_orders, which is separate from fact_purchase_orders
    (historical actuals loaded from CSV, not a live order queue) - nothing
    here places a real order with a supplier."""
    product = query_one("SELECT product_name FROM dim_products WHERE product_id = :pid", {"pid": req.product_id})
    if not product:
        raise ValueError(f"product_id {req.product_id} not found")
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO dim_draft_purchase_orders
                    (created_by, product_id, supplier_id, warehouse_id, quantity, note)
                VALUES (:by, :pid, :sid, :wh, :qty, :note)
                RETURNING draft_po_id
                """
            ),
            {
                "by": actor.username,
                "pid": req.product_id,
                "sid": req.supplier_id,
                "wh": req.warehouse_id,
                "qty": req.quantity,
                "note": req.note,
            },
        )
        draft_po_id = result.scalar()
    audit_service.log_action(
        actor, "create_draft_po", "draft_po", draft_po_id, f"{req.quantity} x {product['product_name']}"
    )
    return {
        "draft_po_id": draft_po_id,
        "product_id": req.product_id,
        "product_name": product["product_name"],
        "supplier_id": req.supplier_id,
        "warehouse_id": req.warehouse_id,
        "quantity": req.quantity,
        "status": "DRAFT",
    }


def list_draft_pos(warehouse_id: Optional[int] = None, limit: int = 100) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id, "dpo.warehouse_id")
    return query_records(
        f"""
        SELECT dpo.draft_po_id, dpo.created_at, dpo.created_by, dpo.product_id, p.product_name,
               dpo.supplier_id, s.supplier_name, dpo.warehouse_id, dpo.quantity, dpo.status, dpo.note
        FROM dim_draft_purchase_orders dpo
        JOIN dim_products p ON p.product_id = dpo.product_id
        LEFT JOIN dim_suppliers s ON s.supplier_id = dpo.supplier_id
        WHERE 1=1 {clause}
        ORDER BY dpo.created_at DESC
        LIMIT :limit
        """,
        {"warehouse_id": warehouse_id, "limit": limit},
    )


def get_reorder_suggestions(
    limit: int = 50,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Auto-suggested reorder quantities for every LOW/CRITICAL product line,
    plus the best-performing historical supplier for that exact product (by
    on-time delivery rate among suppliers who have actually shipped it
    before). Powers the Stock Optimizer's reorder suggestions panel.

    Suggested quantity is a simple, explainable "replenish to N days of
    stock" target: target_stock = avg_daily_units * reorder_target_days_of_stock,
    suggested_qty = max(target_stock - stock_on_hand, 0). Where a product has
    no recent sales velocity to go on (a brand-new or very slow mover), it
    falls back to topping up to 2x the reorder point instead, flagged with
    is_estimate=true so the UI can show it's a rougher guess.
    """
    as_of = _latest_date(warehouse_id, date_from, date_to)
    clause = warehouse_filter_clause(warehouse_id, "i.warehouse_id")
    stock_df = query_df(
        f"""
        WITH recent_sales AS (
            SELECT product_id, warehouse_id, AVG(units_sold) AS avg_daily_units
            FROM fact_sales_daily
            WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days'
            GROUP BY product_id, warehouse_id
        )
        SELECT
            i.product_id,
            p.product_name,
            i.warehouse_id,
            i.stock_status,
            i.stock_on_hand,
            i.reorder_point,
            COALESCE(s.avg_daily_units, 0) AS avg_daily_units
        FROM fact_inventory_daily i
        JOIN dim_products p ON p.product_id = i.product_id
        LEFT JOIN recent_sales s ON s.product_id = i.product_id AND s.warehouse_id = i.warehouse_id
        WHERE i.date_id = :as_of AND i.stock_status IN ('LOW', 'CRITICAL') {clause}
        ORDER BY i.stock_on_hand ASC
        LIMIT :limit
        """,
        {"as_of": as_of, "limit": limit, "warehouse_id": warehouse_id},
    )
    if stock_df.empty:
        return []

    target_days = settings_service.get_setting_float("reorder_target_days_of_stock", 30)

    def suggest_qty(row) -> tuple[float, bool]:
        if row["avg_daily_units"] and row["avg_daily_units"] > 0:
            target_stock = row["avg_daily_units"] * target_days
            return max(round(target_stock - row["stock_on_hand"]), 0), False
        # No sales velocity to go on - fall back to a rough "top up to 2x
        # the reorder point" estimate rather than suggesting 0.
        fallback_target = (row["reorder_point"] or 0) * 2
        return max(round(fallback_target - row["stock_on_hand"]), 0), True

    quantities = stock_df.apply(suggest_qty, axis=1)
    stock_df["suggested_reorder_qty"] = [q[0] for q in quantities]
    stock_df["is_estimate"] = [q[1] for q in quantities]

    product_ids = stock_df["product_id"].unique().tolist()
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    supplier_df = query_df(
        f"""
        SELECT
            po.product_id,
            s.supplier_id,
            s.supplier_name,
            COUNT(*) AS orders_completed,
            COUNT(*) FILTER (WHERE d.delivery_status = 'ON_TIME') AS on_time_count
        FROM fact_purchase_orders po
        JOIN fact_deliveries d ON d.po_id = po.po_id
        JOIN dim_suppliers s ON s.supplier_id = po.supplier_id
        WHERE po.product_id = ANY(:product_ids) {wh_clause}
        GROUP BY po.product_id, s.supplier_id, s.supplier_name
        """,
        {"product_ids": product_ids, "warehouse_id": warehouse_id},
    )

    best_supplier_by_product: dict = {}
    if not supplier_df.empty:
        supplier_df["on_time_pct"] = round(100 * supplier_df["on_time_count"] / supplier_df["orders_completed"], 1)
        for product_id, group in supplier_df.groupby("product_id"):
            best = group.sort_values(
                ["on_time_pct", "orders_completed"], ascending=[False, False]
            ).iloc[0]
            best_supplier_by_product[product_id] = {
                "supplier_id": int(best["supplier_id"]),
                "supplier_name": best["supplier_name"],
                "on_time_delivery_pct": float(best["on_time_pct"]),
                "orders_completed": int(best["orders_completed"]),
            }

    results = []
    for _, row in stock_df.iterrows():
        suggestion = row.to_dict()
        best_supplier = best_supplier_by_product.get(row["product_id"])
        suggestion["best_supplier"] = best_supplier
        suggestion["best_supplier_note"] = (
            None if best_supplier else "No prior purchase-order history for this product - pick a supplier manually."
        )
        results.append(suggestion)
    return results
