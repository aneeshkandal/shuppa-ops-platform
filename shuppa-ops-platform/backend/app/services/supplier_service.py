from typing import Optional

from app.services import settings_service
from app.services.db_utils import (
    compute_deltas,
    date_range_clause,
    query_df,
    query_one,
    query_records,
    resolve_comparison_window,
)

_KPI_DELTA_KEYS = ["total_orders", "total_order_value", "on_time_delivery_pct", "late_delivery_pct"]


def _kpi_totals(
    warehouse_id: Optional[int], date_from: Optional[str], date_to: Optional[str]
) -> dict:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="po.order_date")
    row = query_one(
        f"""
        SELECT
            COUNT(*) AS total_orders,
            COALESCE(SUM(po.order_cost), 0) AS total_order_value,
            COUNT(*) FILTER (WHERE d.delivery_status = 'ON_TIME') AS on_time_count,
            COUNT(*) FILTER (WHERE d.delivery_status = 'LATE') AS late_count
        FROM fact_purchase_orders po
        JOIN fact_deliveries d ON d.po_id = po.po_id
        WHERE 1=1 {wh_clause} {date_clause}
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    total = (row["on_time_count"] or 0) + (row["late_count"] or 0) or 1
    row["on_time_delivery_pct"] = round(100.0 * row["on_time_count"] / total, 1)
    row["late_delivery_pct"] = round(100.0 * row["late_count"] / total, 1)
    return row


def get_kpis(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    row = _kpi_totals(warehouse_id, date_from, date_to)

    wh_clause = "AND warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    prev_from, prev_to = resolve_comparison_window(
        date_from,
        date_to,
        f"SELECT MAX(order_date) AS d FROM fact_purchase_orders WHERE 1=1 {wh_clause}",
        {"warehouse_id": warehouse_id},
    )
    if prev_from and prev_to:
        prev_row = _kpi_totals(warehouse_id, prev_from, prev_to)
        row["comparison"] = {
            "previous_from": prev_from,
            "previous_to": prev_to,
            "deltas": compute_deltas(row, prev_row, _KPI_DELTA_KEYS),
        }
    else:
        row["comparison"] = None
    return row


def get_performance(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="po.order_date")
    # Suppliers scoped to a warehouse should only include common suppliers
    # (warehouse_id IS NULL) plus that warehouse's own exclusive suppliers.
    supplier_scope = (
        "AND (s.warehouse_id IS NULL OR s.warehouse_id = :warehouse_id)" if warehouse_id is not None else ""
    )
    df = query_df(
        f"""
        SELECT
            s.supplier_id,
            s.supplier_name,
            COUNT(*) AS orders_completed,
            COALESCE(SUM(po.order_cost), 0) AS order_value,
            COUNT(*) FILTER (WHERE d.delivery_status = 'ON_TIME') AS on_time_count,
            COUNT(*) FILTER (WHERE d.delivery_status = 'LATE') AS late_count,
            COALESCE(AVG(d.delay_days) FILTER (WHERE d.delivery_status = 'LATE'), 0) AS avg_delay_days
        FROM fact_purchase_orders po
        JOIN fact_deliveries d ON d.po_id = po.po_id
        JOIN dim_suppliers s ON s.supplier_id = po.supplier_id
        WHERE 1=1 {wh_clause} {date_clause} {supplier_scope}
        GROUP BY s.supplier_id, s.supplier_name
        ORDER BY order_value DESC
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    if df.empty:
        return []
    df["on_time_delivery_pct"] = round(100 * df["on_time_count"] / df["orders_completed"], 1)
    df["late_delivery_pct"] = round(100 * df["late_count"] / df["orders_completed"], 1)

    medium_threshold = settings_service.get_setting_float("supplier_late_pct_medium_threshold", 15)
    high_threshold = settings_service.get_setting_float("supplier_late_pct_high_threshold", 25)

    def label(pct: float) -> str:
        if pct <= medium_threshold:
            return "Low"
        if pct <= high_threshold:
            return "Medium"
        return "High"

    df["risk_level"] = df["late_delivery_pct"].apply(label)
    return df.to_dict(orient="records")


def get_trend(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="po.order_date")
    return query_records(
        f"""
        SELECT
            DATE_TRUNC('month', po.order_date)::date AS month,
            ROUND(100.0 * COUNT(*) FILTER (WHERE d.delivery_status = 'ON_TIME') / COUNT(*), 1) AS on_time_pct
        FROM fact_purchase_orders po
        JOIN fact_deliveries d ON d.po_id = po.po_id
        WHERE 1=1 {wh_clause} {date_clause}
        GROUP BY 1
        ORDER BY 1
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_risk_distribution(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    performance = get_performance(warehouse_id, date_from, date_to)
    buckets = {"Low": 0, "Medium": 0, "High": 0}
    for row in performance:
        buckets[row["risk_level"]] += 1
    total = sum(buckets.values()) or 1
    return [
        {"risk_level": level, "supplier_count": count, "pct": round(100 * count / total, 1)}
        for level, count in buckets.items()
    ]


def get_top_by_value(
    limit: int = 5,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="po.order_date")
    return query_records(
        f"""
        SELECT s.supplier_id, s.supplier_name, SUM(po.order_cost) AS order_value
        FROM fact_purchase_orders po
        JOIN dim_suppliers s ON s.supplier_id = po.supplier_id
        WHERE 1=1 {wh_clause} {date_clause}
        GROUP BY s.supplier_id, s.supplier_name
        ORDER BY order_value DESC
        LIMIT :limit
        """,
        {"limit": limit, "warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_recent_late(
    limit: int = 10,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    supplier_id: Optional[int] = None,
) -> list[dict]:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    supplier_clause = "AND po.supplier_id = :supplier_id" if supplier_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="d.actual_delivery_date")
    return query_records(
        f"""
        SELECT
            po.po_id,
            s.supplier_name,
            p.product_name,
            w.warehouse_name,
            d.delay_days,
            d.actual_delivery_date
        FROM fact_deliveries d
        JOIN fact_purchase_orders po ON po.po_id = d.po_id
        JOIN dim_suppliers s ON s.supplier_id = po.supplier_id
        JOIN dim_products p ON p.product_id = po.product_id
        JOIN dim_warehouses w ON w.warehouse_id = po.warehouse_id
        WHERE d.delivery_status = 'LATE' {wh_clause} {date_clause} {supplier_clause}
        ORDER BY d.actual_delivery_date DESC
        LIMIT :limit
        """,
        {
            "limit": limit,
            "warehouse_id": warehouse_id,
            "date_from": date_from,
            "date_to": date_to,
            "supplier_id": supplier_id,
        },
    )
