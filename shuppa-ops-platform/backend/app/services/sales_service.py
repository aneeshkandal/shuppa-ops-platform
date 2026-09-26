import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.database import engine
from app.services.db_utils import (
    compute_deltas,
    date_range_clause,
    query_df,
    query_one,
    query_records,
    resolve_comparison_window,
    warehouse_filter_clause,
)

_KPI_DELTA_KEYS = ["total_revenue", "total_units_sold", "total_profit", "distinct_products_sold"]

# --- Synthetic order + customer layer (dim_customers / fact_orders) ------
#
# fact_sales_daily is daily-grain only (product x warehouse x day) - there
# has never been a real order_id, a time-of-day, or a customer entity
# anywhere in Shuppa's data. This layer originally only needed to fabricate
# an order COUNT (for "True Order Trends" / "Peak Order Time Analysis",
# stored in a now-retired fact_orders_hourly bucket table). Customer Growth
# & Retention, last-mile Delivery & Fulfillment Performance, and Return &
# Cancellation Insights all need real per-ORDER *and* per-CUSTOMER identity
# on top of that, which the bucket table deliberately didn't have - so
# fact_orders (one row per individual synthetic order, linked to a synthetic
# customer) now supersedes it as the single source of truth for every
# order-based figure in the app, including Order Trend/Peak Time, so two
# synthetic layers can never quietly disagree with each other.
#
# See backfill_synthetic_orders()'s docstring for exactly what's real
# (each day's total revenue/units) vs. estimated (everything else: order
# count, hour, customer identity, delivery outcome).

# Documented assumption, not fitted to anything: a typical quick-commerce
# grocery basket size. Used only to turn a day's real total units_sold into
# an estimated order count (units / this = orders) - changing this constant
# rescales every order count/avg order value figure in the app uniformly.
SYNTHETIC_AVG_ITEMS_PER_ORDER = 2.4

# Documented assumption, not derived from any real hourly data (none
# exists): a generic quick-commerce demand curve applied identically to
# every day - overnight trough, a late-morning ramp, a lunch peak (~1pm), an
# afternoon dip, and the day's highest peak at dinner (~7pm). Index i is
# hour i (0 = 12am-1am ... 23 = 11pm-midnight). Arbitrary units - normalized
# to shares that sum to 1.0 below, so the absolute numbers only matter
# relative to each other.
_HOURLY_WEIGHTS = [
    0.5, 0.3, 0.2, 0.2, 0.2, 0.3, 0.8, 1.5, 2.5, 3.5, 4.5, 6.0,
    8.5, 9.0, 7.5, 5.0, 4.5, 5.5, 8.0, 10.0, 8.5, 6.0, 3.5, 1.5,
]
_HOURLY_SHARE = [w / sum(_HOURLY_WEIGHTS) for w in _HOURLY_WEIGHTS]

# Documented assumption: how often a typical repeat customer reorders over a
# full year. Sets how large the fabricated customer pool is (total orders /
# this = customer count) - there's no real customer count anywhere to
# calibrate against, so this is a plausible quick-commerce default, not a
# measurement.
AVG_ORDERS_PER_CUSTOMER_PER_YEAR = 15.0

# Pareto shape parameter for how unevenly orders are spread across the
# customer pool. Lower = more skewed toward a small number of very frequent
# repeat customers, higher = closer to every customer ordering equally
# often. 1.5 gives a realistic-looking "a minority of customers account for
# a disproportionate share of orders" pattern rather than a flat uniform
# distribution, which would make "returning customer" numbers look
# artificially smooth.
CUSTOMER_REPEAT_SKEW = 1.5

# Documented assumption: last-mile (customer-facing) delivery outcome rates.
# Grocery/quick-commerce items are rarely "returned" in the retail-apparel
# sense (a bag of snacks or a fresh product isn't usually sent back), so
# RETURNED is kept deliberately small relative to CANCELLED (a customer or
# the store cancelling before the order ever goes out - out of stock, a
# picking issue - is the more realistic failure mode for this kind of
# business). No real returns/cancellations data exists anywhere in the
# source to calibrate these against.
_DELIVERY_OUTCOME_RATES = {
    "ON_TIME": 0.90,
    "LATE": 0.06,
    "CANCELLED": 0.03,
    "RETURNED": 0.01,
}
_DELIVERY_STATUSES = list(_DELIVERY_OUTCOME_RATES.keys())
_DELIVERY_PROBS = list(_DELIVERY_OUTCOME_RATES.values())


def _split_hourly(total: int, shares: list[float]) -> list[int]:
    """Splits an integer `total` across len(shares) buckets using the
    largest-remainder method, so the result sums EXACTLY to `total` (naively
    rounding each share's own share independently can drift the sum by a
    unit or two either way, which would make a hover-over hour total
    disagree with the day's real order count)."""
    raw = [total * s for s in shares]
    floors = [int(x) for x in raw]
    remainder = total - sum(floors)
    order = sorted(range(len(raw)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def _insert_chunked(
    insert_prefix: str,
    rows: list[dict],
    label: str,
    conflict_clause: str = "",
    chunk_size: int = 20000,
    batch_size: int = 1000,
) -> None:
    """Batched INSERT using multi-row VALUES statements (`batch_size` rows
    per round trip), NOT a plain `conn.execute(text(sql), rows)` call with a
    single-row template.

    That naive form is what this function originally did, and it's a real
    performance bug, not just a style choice: passing a list of parameter
    dicts to a raw textual `text()` statement makes SQLAlchemy hand the list
    straight to the DBAPI's own `cursor.executemany()` - and psycopg2's
    `executemany()` is a documented, well-known trap: its default
    implementation issues ONE NETWORK ROUND TRIP PER ROW, not a real batch
    (SQLAlchemy's fast "insertmanyvalues" rewriting only applies to Core
    `insert()` constructs, never to opaque `text()` SQL, which is what every
    query in this file uses). Against this project's local/negligible-
    latency test Postgres that's invisible - a few hundred thousand
    near-instant round trips still finish in seconds. Against the real
    Neon database, at even a modest ~30-50ms per round trip, one row at a
    time turns an ~800k-row one-time backfill into multiple HOURS instead of
    roughly a minute - this is what actually produced the "stuck" symptom
    reported right after this function first shipped, not a genuine hang or
    a slow Neon cold start.

    Fix: build one INSERT with `batch_size` VALUES tuples per round trip
    (each row's params given unique suffixed keys, e.g. `:customer_id_0`,
    `:customer_id_1`, ...) instead of relying on the DBAPI's per-row loop -
    cuts the round-trip count by ~`batch_size`x. `chunk_size` still controls
    how often progress is printed (each chunk is its own set of
    `chunk_size / batch_size` round trips), independent of the smaller
    network-batch size, so progress visibility is unchanged.

    `insert_prefix` is everything up to (and including) the INSERT's column
    list, e.g. "INSERT INTO dim_customers (customer_id, warehouse_id,
    first_order_date)" - NOT a full single-row VALUES(...) template like
    this function used to take. `conflict_clause` is an optional trailing
    clause (e.g. "ON CONFLICT (customer_id) DO NOTHING")."""
    if not rows:
        return
    total = len(rows)
    columns = list(rows[0].keys())
    # Sanity-check that insert_prefix's explicit column list actually
    # matches the row dicts' keys/order - a silent mismatch here would
    # scramble which value lands in which column with no error at all.
    prefix_columns = [c.strip() for c in insert_prefix.split("(", 1)[1].rsplit(")", 1)[0].split(",")]
    assert prefix_columns == columns, (
        f"_insert_chunked({label}): insert_prefix columns {prefix_columns} don't match row dict keys {columns}"
    )
    with engine.begin() as conn:
        for start in range(0, total, chunk_size):
            chunk = rows[start : start + chunk_size]
            for sub_start in range(0, len(chunk), batch_size):
                sub = chunk[sub_start : sub_start + batch_size]
                value_groups = []
                params: dict = {}
                for i, row in enumerate(sub):
                    value_groups.append("(" + ", ".join(f":{col}_{i}" for col in columns) + ")")
                    for col in columns:
                        params[f"{col}_{i}"] = row[col]
                sql = f"{insert_prefix} VALUES {', '.join(value_groups)} {conflict_clause}"
                conn.execute(text(sql), params)
            print(f"[synthetic-orders]   {label}: inserted {min(start + chunk_size, total)}/{total}", flush=True)


def backfill_synthetic_orders() -> int:
    """One-time generation of dim_customers + fact_orders - individual
    order-grain rows, each linked to a synthetic customer, replacing the
    coarser fact_orders_hourly bucket table entirely.

    What's REAL: each day's total revenue and total units_sold per
    warehouse, read from fact_sales_daily (every order's value is derived
    from these and sums back to the real daily total). What's ESTIMATED,
    with NO real basis anywhere in the source data: how many orders that
    represents (SYNTHETIC_AVG_ITEMS_PER_ORDER), which hour of the day each
    landed in (_HOURLY_WEIGHTS), how many distinct customers exist and how
    often they reorder (AVG_ORDERS_PER_CUSTOMER_PER_YEAR,
    CUSTOMER_REPEAT_SKEW - a Pareto distribution so a minority of customers
    place a disproportionate share of orders, rather than every customer
    ordering equally often), and each order's delivery outcome
    (_DELIVERY_OUTCOME_RATES). A customer's `first_order_date` is simply the
    earliest date any order got assigned to them during generation - there
    is no real signup date to model.

    Unlike a per-(date, warehouse) self-healing fill, sizing a believable
    customer pool needs the WHOLE year's order volume for a warehouse up
    front, which doesn't compose with filling in a handful of new days
    later - so this is a ONE-TIME batch run, guarded by a dim_settings
    sentinel ('synthetic_customer_orders_v1'), same pattern as the
    placement-scoring one-time upgrade elsewhere in this file's neighbour
    migrations.py. A genuine later re-run only happens after a full reseed,
    which drops both tables empty first (see scripts/seed_database.py), so
    this always starts from a clean slate rather than trying to merge into
    an existing customer pool.
    """
    already_done = query_one("SELECT 1 AS x FROM dim_settings WHERE setting_key = 'synthetic_customer_orders_v1'")
    if already_done:
        return 0

    print("[synthetic-orders] first run - generating customers and individual orders (one-time)...", flush=True)
    t0 = time.monotonic()

    daily = query_df(
        """
        SELECT date_id, warehouse_id, SUM(units_sold) AS total_units, SUM(revenue) AS total_revenue
        FROM fact_sales_daily
        GROUP BY date_id, warehouse_id
        ORDER BY date_id
        """
    )
    print(f"[synthetic-orders] {len(daily)} (date, warehouse) group(s) to process.", flush=True)
    if daily.empty:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO dim_settings (setting_key, setting_value) VALUES "
                    "('synthetic_customer_orders_v1', 'done') ON CONFLICT (setting_key) DO NOTHING"
                )
            )
        return 0

    rng = np.random.default_rng(42)

    daily["order_count"] = daily.apply(
        lambda r: max(1, round(r["total_units"] / SYNTHETIC_AVG_ITEMS_PER_ORDER)) if r["total_units"] > 0 else 0,
        axis=1,
    )
    orders_per_warehouse = daily.groupby("warehouse_id")["order_count"].sum()

    # Build each warehouse's customer pool, sized off its own total order
    # volume, with a Pareto-skewed sampling weight per customer.
    customer_pools: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    customer_rows = []
    next_customer_id = 1
    for warehouse_id, total_orders in orders_per_warehouse.items():
        pool_size = max(1, round(total_orders / AVG_ORDERS_PER_CUSTOMER_PER_YEAR))
        ids = np.arange(next_customer_id, next_customer_id + pool_size)
        next_customer_id += pool_size
        weights = rng.pareto(CUSTOMER_REPEAT_SKEW, size=pool_size) + 1
        probs = weights / weights.sum()
        customer_pools[int(warehouse_id)] = (ids, probs)
        for cid in ids:
            customer_rows.append({"customer_id": int(cid), "warehouse_id": int(warehouse_id)})
    print(
        f"[synthetic-orders] generated {len(customer_rows)} synthetic customer(s) across "
        f"{len(customer_pools)} warehouse(s).",
        flush=True,
    )

    first_order_date: dict[int, str] = {}
    order_rows = []
    for row in daily.itertuples():
        order_count = int(row.order_count)
        if order_count == 0:
            continue
        warehouse_id = int(row.warehouse_id)
        total_revenue = float(row.total_revenue or 0)
        ids, probs = customer_pools[warehouse_id]
        assigned_customers = rng.choice(ids, size=order_count, p=probs)

        hourly_counts = _split_hourly(order_count, _HOURLY_SHARE)
        hours = np.repeat(np.arange(24), hourly_counts)
        rng.shuffle(hours)  # which specific order lands in which hour within the day is arbitrary

        item_counts = rng.integers(1, 6, size=order_count)  # 1-5 line items/order, documented assumption
        order_values = np.round(total_revenue * (item_counts / item_counts.sum()), 2)

        statuses = rng.choice(_DELIVERY_STATUSES, size=order_count, p=_DELIVERY_PROBS)
        on_time_or_returned = np.isin(statuses, ["ON_TIME", "RETURNED"])
        late = statuses == "LATE"
        minutes = np.full(order_count, None, dtype=object)
        minutes[on_time_or_returned] = rng.integers(10, 31, size=int(on_time_or_returned.sum()))
        minutes[late] = rng.integers(31, 61, size=int(late.sum()))
        # CANCELLED orders never went out for delivery - minutes stays None.

        date_str = row.date_id.isoformat() if hasattr(row.date_id, "isoformat") else str(row.date_id)
        for i in range(order_count):
            cid = int(assigned_customers[i])
            order_rows.append(
                {
                    "customer_id": cid,
                    "warehouse_id": warehouse_id,
                    "order_date": row.date_id,
                    "order_hour": int(hours[i]),
                    "order_value": float(order_values[i]),
                    "item_count": int(item_counts[i]),
                    "delivery_status": str(statuses[i]),
                    "delivery_minutes": None if minutes[i] is None else int(minutes[i]),
                }
            )
            if cid not in first_order_date or date_str < first_order_date[cid]:
                first_order_date[cid] = date_str

    for c in customer_rows:
        c["first_order_date"] = first_order_date.get(c["customer_id"])
    # A pool slot that never actually got sampled for any order (possible
    # with a heavy Pareto skew on a small pool) has no real first order -
    # drop it rather than insert a "customer" who never ordered anything.
    customer_rows = [c for c in customer_rows if c["first_order_date"] is not None]

    print(
        f"[synthetic-orders] generated {len(order_rows)} individual order(s) from {len(customer_rows)} "
        f"active customer(s) ({time.monotonic() - t0:.1f}s elapsed) - inserting...",
        flush=True,
    )

    _insert_chunked(
        "INSERT INTO dim_customers (customer_id, warehouse_id, first_order_date)",
        customer_rows,
        label="dim_customers",
        conflict_clause="ON CONFLICT (customer_id) DO NOTHING",
    )
    _insert_chunked(
        "INSERT INTO fact_orders (customer_id, warehouse_id, order_date, order_hour, order_value, "
        "item_count, delivery_status, delivery_minutes)",
        order_rows,
        label="fact_orders",
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dim_settings (setting_key, setting_value) VALUES "
                "('synthetic_customer_orders_v1', 'done') ON CONFLICT (setting_key) DO NOTHING"
            )
        )

    print(f"[synthetic-orders] done ({time.monotonic() - t0:.1f}s total).", flush=True)
    return len(order_rows)


def _resolve_order_window(date_from: Optional[str], date_to: Optional[str], days: int) -> tuple:
    """Resolves an explicit or implicit (date_from, date_to) window against
    fact_orders' own latest date, mirroring db_utils.previous_period_window's
    "anchor to the data's own MAX(date), not wall-clock today" reasoning -
    fact_orders is seeded historical data, not necessarily current."""
    if date_from or date_to:
        return date_from, date_to
    max_row = query_one("SELECT MAX(order_date) AS d FROM fact_orders")
    max_d = max_row.get("d") if max_row else None
    if not max_d:
        return None, None
    if isinstance(max_d, str):
        max_d = datetime.strptime(max_d[:10], "%Y-%m-%d").date()
    elif isinstance(max_d, datetime):
        max_d = max_d.date()
    from_d = max_d - timedelta(days=days - 1)
    return from_d.isoformat(), max_d.isoformat()


def get_order_trend(
    granularity: str = "day",
    days: int = 31,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Order-count / order-revenue trend from the synthetic fact_orders
    layer (see backfill_synthetic_orders' docstring for what's real vs.
    estimated) - mirrors get_trend()'s shape so the frontend can render both
    with the same TrendLine component."""
    clause = warehouse_filter_clause(warehouse_id)
    bucket = "DATE_TRUNC('month', order_date)::date" if granularity == "month" else "order_date"
    if date_from or date_to:
        window = date_range_clause(date_from, date_to, column="order_date")
    else:
        window = (
            ""
            if granularity == "month"
            else f"AND order_date > (SELECT MAX(order_date) FROM fact_orders) - INTERVAL '{int(days)} days'"
        )
    return query_records(
        f"""
        SELECT {bucket} AS bucket, COUNT(*) AS order_count, COALESCE(SUM(order_value), 0) AS order_revenue
        FROM fact_orders
        WHERE 1=1 {clause} {window}
        GROUP BY 1
        ORDER BY 1
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_order_time_distribution(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    """Order volume by hour of day, summed over the selected window - powers
    the Peak Order Time chart. Because the underlying curve
    (backfill_synthetic_orders' _HOURLY_WEIGHTS) is applied identically to
    every day, the shape here will closely track that fixed curve regardless
    of which warehouse/date range is selected; only the magnitude (not the
    shape) genuinely varies with the filter."""
    clause = warehouse_filter_clause(warehouse_id) + date_range_clause(date_from, date_to, column="order_date")
    return query_records(
        f"""
        SELECT order_hour AS hour_of_day, COUNT(*) AS order_count, COALESCE(SUM(order_value), 0) AS order_revenue
        FROM fact_orders
        WHERE 1=1 {clause}
        GROUP BY order_hour
        ORDER BY order_hour
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_customer_growth(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, days: int = 90
) -> dict:
    """New-vs-returning customer counts and a daily new-customer trend, from
    the synthetic dim_customers/fact_orders layer. Customer identity itself
    has no real basis anywhere in the source data (see
    backfill_synthetic_orders' docstring) - this is a plausible estimate for
    exploration, not a measurement of Shuppa's real customer base.

    "New" = a customer whose very first-ever order falls inside the selected
    window. "Returning" = active in the window but first ordered before it
    started. Defaults to the trailing `days` days (anchored to fact_orders'
    own latest date) when no explicit date filter is set, same convention
    every other KPI-style function in this file uses.
    """
    eff_from, eff_to = _resolve_order_window(date_from, date_to, days)
    wh_clause = warehouse_filter_clause(warehouse_id, "fo.warehouse_id")
    window = date_range_clause(eff_from, eff_to, column="fo.order_date")
    params = {"warehouse_id": warehouse_id, "date_from": eff_from, "date_to": eff_to}

    trend = query_records(
        f"""
        SELECT fo.order_date AS bucket,
               COUNT(DISTINCT fo.customer_id) FILTER (WHERE dc.first_order_date = fo.order_date) AS new_customers,
               COUNT(DISTINCT fo.customer_id) AS active_customers
        FROM fact_orders fo
        JOIN dim_customers dc ON dc.customer_id = fo.customer_id
        WHERE 1=1 {wh_clause} {window}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )

    summary = query_one(
        f"""
        SELECT
            COUNT(DISTINCT fo.customer_id) AS active_customers,
            COUNT(DISTINCT fo.customer_id) FILTER (WHERE dc.first_order_date >= :date_from) AS new_customers,
            COUNT(*) AS total_orders
        FROM fact_orders fo
        JOIN dim_customers dc ON dc.customer_id = fo.customer_id
        WHERE 1=1 {wh_clause} {window}
        """,
        params,
    )

    active = int(summary.get("active_customers") or 0)
    new = int(summary.get("new_customers") or 0)
    returning = max(0, active - new)
    total_orders = int(summary.get("total_orders") or 0)
    return {
        "trend": trend,
        "active_customers": active,
        "new_customers": new,
        "returning_customers": returning,
        "returning_pct": round(100 * returning / active, 1) if active else None,
        "avg_orders_per_active_customer": round(total_orders / active, 2) if active else None,
    }


def get_delivery_performance(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, days: int = 31
) -> dict:
    """Last-mile (customer-facing) delivery performance from the synthetic
    fact_orders layer - see backfill_synthetic_orders' docstring for the
    delivery-outcome assumptions used (_DELIVERY_OUTCOME_RATES).

    Deliberately a SEPARATE concept from the Delivery Risk Predictor page:
    that page models real supplier-to-warehouse purchase-order deliveries
    (fact_purchase_orders/fact_deliveries) - this models the fabricated
    warehouse-to-customer leg, which the source data has never captured at
    all. Do not merge these two in the UI; they measure different things
    off different (one real, one synthetic) datasets.
    """
    eff_from, eff_to = _resolve_order_window(date_from, date_to, days)
    wh_clause = warehouse_filter_clause(warehouse_id)
    window = date_range_clause(eff_from, eff_to, column="order_date")
    params = {"warehouse_id": warehouse_id, "date_from": eff_from, "date_to": eff_to}

    summary = query_one(
        f"""
        SELECT
            COUNT(*) AS total_orders,
            COUNT(*) FILTER (WHERE delivery_status = 'ON_TIME') AS on_time,
            COUNT(*) FILTER (WHERE delivery_status = 'LATE') AS late,
            COUNT(*) FILTER (WHERE delivery_status = 'CANCELLED') AS cancelled,
            COUNT(*) FILTER (WHERE delivery_status = 'RETURNED') AS returned,
            ROUND(AVG(delivery_minutes) FILTER (WHERE delivery_minutes IS NOT NULL)::numeric, 1) AS avg_delivery_minutes
        FROM fact_orders
        WHERE 1=1 {wh_clause} {window}
        """,
        params,
    )
    trend = query_records(
        f"""
        SELECT order_date AS bucket,
               ROUND(100.0 * COUNT(*) FILTER (WHERE delivery_status = 'ON_TIME') / NULLIF(COUNT(*), 0), 1) AS on_time_pct,
               ROUND(AVG(delivery_minutes) FILTER (WHERE delivery_minutes IS NOT NULL)::numeric, 1) AS avg_delivery_minutes
        FROM fact_orders
        WHERE 1=1 {wh_clause} {window}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )

    total = int(summary.get("total_orders") or 0)
    on_time = int(summary.get("on_time") or 0)
    return {
        "total_orders": total,
        "on_time_pct": round(100 * on_time / total, 1) if total else None,
        "late": int(summary.get("late") or 0),
        "cancelled": int(summary.get("cancelled") or 0),
        "returned": int(summary.get("returned") or 0),
        "avg_delivery_minutes": (
            float(summary["avg_delivery_minutes"]) if summary.get("avg_delivery_minutes") is not None else None
        ),
        "trend": trend,
    }


def get_return_cancellation_insights(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, days: int = 31
) -> dict:
    """Return/cancellation rate and estimated lost revenue from the
    synthetic fact_orders layer - see backfill_synthetic_orders' docstring
    for the fabricated rates used (_DELIVERY_OUTCOME_RATES); there is no
    real returns/cancellations data anywhere in Shuppa's source data."""
    eff_from, eff_to = _resolve_order_window(date_from, date_to, days)
    wh_clause = warehouse_filter_clause(warehouse_id)
    window = date_range_clause(eff_from, eff_to, column="order_date")
    params = {"warehouse_id": warehouse_id, "date_from": eff_from, "date_to": eff_to}

    summary = query_one(
        f"""
        SELECT
            COUNT(*) AS total_orders,
            COUNT(*) FILTER (WHERE delivery_status = 'RETURNED') AS returned,
            COUNT(*) FILTER (WHERE delivery_status = 'CANCELLED') AS cancelled,
            COALESCE(SUM(order_value) FILTER (WHERE delivery_status IN ('RETURNED', 'CANCELLED')), 0) AS lost_revenue
        FROM fact_orders
        WHERE 1=1 {wh_clause} {window}
        """,
        params,
    )
    trend = query_records(
        f"""
        SELECT order_date AS bucket,
               ROUND(100.0 * COUNT(*) FILTER (WHERE delivery_status = 'RETURNED') / NULLIF(COUNT(*), 0), 2) AS return_pct,
               ROUND(100.0 * COUNT(*) FILTER (WHERE delivery_status = 'CANCELLED') / NULLIF(COUNT(*), 0), 2) AS cancellation_pct
        FROM fact_orders
        WHERE 1=1 {wh_clause} {window}
        GROUP BY 1
        ORDER BY 1
        """,
        params,
    )

    total = int(summary.get("total_orders") or 0)
    returned = int(summary.get("returned") or 0)
    cancelled = int(summary.get("cancelled") or 0)
    return {
        "total_orders": total,
        "return_pct": round(100 * returned / total, 2) if total else None,
        "cancellation_pct": round(100 * cancelled / total, 2) if total else None,
        "returned": returned,
        "cancelled": cancelled,
        "lost_revenue": float(summary.get("lost_revenue") or 0),
        "trend": trend,
    }


def _kpi_totals(
    warehouse_id: Optional[int], date_from: Optional[str], date_to: Optional[str]
) -> dict:
    clause = warehouse_filter_clause(warehouse_id) + date_range_clause(date_from, date_to)
    return query_one(
        f"""
        SELECT
            COALESCE(SUM(revenue), 0) AS total_revenue,
            COALESCE(SUM(units_sold), 0) AS total_units_sold,
            COALESCE(SUM(profit), 0) AS total_profit,
            COUNT(DISTINCT product_id) AS distinct_products_sold
        FROM fact_sales_daily
        WHERE 1=1 {clause}
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_kpis(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    row = _kpi_totals(warehouse_id, date_from, date_to)
    top_clause = warehouse_filter_clause(warehouse_id, "s.warehouse_id") + date_range_clause(
        date_from, date_to, column="s.date_id"
    )
    top = query_one(
        f"""
        SELECT p.product_name, SUM(s.units_sold) AS units_sold
        FROM fact_sales_daily s
        JOIN dim_products p ON p.product_id = s.product_id
        WHERE 1=1 {top_clause}
        GROUP BY p.product_name
        ORDER BY units_sold DESC
        LIMIT 1
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    row["top_product_name"] = top.get("product_name")
    row["top_product_units"] = top.get("units_sold")

    max_date_clause = warehouse_filter_clause(warehouse_id)
    prev_from, prev_to = resolve_comparison_window(
        date_from,
        date_to,
        f"SELECT MAX(date_id) AS d FROM fact_sales_daily WHERE 1=1 {max_date_clause}",
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


def get_forecast(
    forecast_days: int = 7,
    history_days: int = 30,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> dict:
    """Naive demand forecast for the Sales Analytics trend chart: fits a
    simple linear trend (numpy least-squares, no external ML dependency) over
    the trailing `history_days` of daily revenue and units, then extrapolates
    `forecast_days` forward.

    This is intentionally simple (a straight-line projection, not a
    seasonal/ARIMA model) - it's meant to give the dashboard a directional
    "where is this headed" signal, not a precise demand plan. Returns both
    the historical points actually used and the forecast points so the chart
    can render the whole series continuously.

    `category` optionally scopes the whole forecast to one product category
    (e.g. "Snacks") instead of the warehouse-wide total - useful for
    spotting a category-specific trend that's masked in the aggregate. This
    is still the same straight-line projection fit against a narrower slice
    of history - it does not add weekly-seasonality modelling, which would
    be a materially bigger change (a naive linear fit is a poor match for a
    seasonal signal) and is intentionally left out of this pass.
    """
    history = get_trend("day", history_days, warehouse_id, date_from, date_to, category)
    if len(history) < 2:
        return {
            "history": history,
            "forecast": [],
            "category": category,
            "note": "Not enough history to fit a trend.",
        }

    x = np.arange(len(history), dtype=float)
    revenue = np.array([float(h["revenue"] or 0) for h in history])
    units = np.array([float(h["units_sold"] or 0) for h in history])

    rev_slope, rev_intercept = np.polyfit(x, revenue, 1)
    unit_slope, unit_intercept = np.polyfit(x, units, 1)

    last_date = history[-1]["bucket"]
    forecast = []
    for step in range(1, forecast_days + 1):
        idx = len(history) - 1 + step
        forecast.append(
            {
                "bucket": (_add_days(last_date, step)),
                "revenue": max(0, round(rev_slope * idx + rev_intercept, 2)),
                "units_sold": max(0, round(unit_slope * idx + unit_intercept, 1)),
                "is_forecast": True,
            }
        )
    return {
        "history": history,
        "forecast": forecast,
        "category": category,
        "trend_direction": "up" if rev_slope > 0 else ("down" if rev_slope < 0 else "flat"),
    }


def _add_days(base_date, days: int) -> str:
    if isinstance(base_date, str):
        base_date = datetime.strptime(base_date[:10], "%Y-%m-%d").date()
    elif isinstance(base_date, datetime):
        base_date = base_date.date()
    return (base_date + timedelta(days=days)).isoformat()


def get_trend(
    granularity: str = "day",
    days: int = 31,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id, "s.warehouse_id" if category else "warehouse_id")
    bucket = "DATE_TRUNC('month', date_id)::date" if granularity == "month" else "date_id"
    if date_from or date_to:
        window = date_range_clause(date_from, date_to, column="s.date_id" if category else "date_id")
    else:
        date_col = "s.date_id" if category else "date_id"
        window = (
            ""
            if granularity == "month"
            else f"AND {date_col} > (SELECT MAX({date_col}) FROM fact_sales_daily {'s' if category else ''}) - INTERVAL '{int(days)} days'"
        )

    if category:
        # Category filtering needs a join to dim_products, so this branch
        # aliases the fact table as `s` and qualifies every column - kept
        # separate from the (much more common) unfiltered query below rather
        # than always joining, so the common case stays a single-table scan.
        bucket_col = "DATE_TRUNC('month', s.date_id)::date" if granularity == "month" else "s.date_id"
        return query_records(
            f"""
            SELECT {bucket_col} AS bucket, SUM(s.revenue) AS revenue, SUM(s.units_sold) AS units_sold
            FROM fact_sales_daily s
            JOIN dim_products p ON p.product_id = s.product_id
            WHERE p.category = :category {clause} {window}
            GROUP BY 1
            ORDER BY 1
            """,
            {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to, "category": category},
        )

    return query_records(
        f"""
        SELECT {bucket} AS bucket, SUM(revenue) AS revenue, SUM(units_sold) AS units_sold
        FROM fact_sales_daily
        WHERE 1=1 {clause} {window}
        GROUP BY 1
        ORDER BY 1
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_categories() -> list[str]:
    """Distinct product categories, for the Sales Analytics forecast
    category-filter dropdown."""
    rows = query_records("SELECT DISTINCT category FROM dim_products WHERE category IS NOT NULL ORDER BY category")
    return [r["category"] for r in rows]


_CORRELATION_THRESHOLD = 0.4


def _compute_correlated(pivot: "pd.DataFrame", product_id: int, limit: int) -> list[tuple[int, float]]:
    """Pure math half of get_correlated_products, split out so it can be
    unit-tested against a small hand-built pivot table without a database.

    `pivot` is a (date x product_id) table of daily units_sold. Returns
    [(other_product_id, correlation)] for products whose daily sales
    pattern correlates above _CORRELATION_THRESHOLD with the target
    product's, strongest first.
    """
    if product_id not in pivot.columns or pivot.shape[0] < 10:
        return []
    corr = pivot.corrwith(pivot[product_id]).drop(index=product_id, errors="ignore")
    corr = corr.dropna()
    corr = corr[corr > _CORRELATION_THRESHOLD].sort_values(ascending=False).head(limit)
    return [(int(pid), round(float(val), 2)) for pid, val in corr.items()]


def get_correlated_products(product_id: int, warehouse_id: Optional[int] = None, limit: int = 5, days: int = 90) -> dict:
    """Products whose daily sales move similarly to the given product over
    the trailing `days` days (Pearson correlation of daily units_sold).

    IMPORTANT - this is NOT real market-basket / "customers who bought this
    also bought" analysis. This dataset has no order-level transaction table
    (fact_sales_daily is daily totals per product per warehouse, with no
    order_id), so there's no way to know which items were actually bought
    together in the same basket. This is a weaker, honest proxy: products
    whose daily demand tends to rise and fall together (e.g. two snacks
    that both spike on Fridays), which can still be a useful hint for
    co-location, but should never be presented to a user as real
    co-purchase data.
    """
    clause = warehouse_filter_clause(warehouse_id)
    df = query_df(
        f"""
        SELECT date_id, product_id, SUM(units_sold) AS units_sold
        FROM fact_sales_daily
        WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '{int(days)} days' {clause}
        GROUP BY date_id, product_id
        """,
        {"warehouse_id": warehouse_id},
    )
    if df.empty or product_id not in df["product_id"].unique():
        return {
            "product_id": product_id,
            "correlated": [],
            "note": "Not enough sales history for this product to compare demand patterns.",
        }

    pivot = df.pivot_table(index="date_id", columns="product_id", values="units_sold", fill_value=0)
    pairs = _compute_correlated(pivot, product_id, limit)
    if not pairs:
        return {
            "product_id": product_id,
            "correlated": [],
            "note": "No products with a similar demand pattern found over this window.",
        }

    ids = [pid for pid, _ in pairs]
    names = query_records(
        "SELECT product_id, product_name, category FROM dim_products WHERE product_id = ANY(:ids)",
        {"ids": ids},
    )
    name_map = {n["product_id"]: n for n in names}
    correlated = [
        {
            "product_id": pid,
            "product_name": name_map.get(pid, {}).get("product_name", f"Product {pid}"),
            "category": name_map.get(pid, {}).get("category"),
            "correlation": corr_val,
        }
        for pid, corr_val in pairs
    ]
    return {"product_id": product_id, "correlated": correlated}


def get_top_products(
    limit: int = 10,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id, "s.warehouse_id") + date_range_clause(
        date_from, date_to, column="s.date_id"
    )
    return query_records(
        f"""
        SELECT p.product_name, SUM(s.revenue) AS revenue, SUM(s.units_sold) AS units_sold
        FROM fact_sales_daily s
        JOIN dim_products p ON p.product_id = s.product_id
        WHERE 1=1 {clause}
        GROUP BY p.product_name
        ORDER BY revenue DESC
        LIMIT :limit
        """,
        {"limit": limit, "warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_by_category(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id, "s.warehouse_id") + date_range_clause(
        date_from, date_to, column="s.date_id"
    )
    return query_records(
        f"""
        SELECT p.category, SUM(s.revenue) AS revenue
        FROM fact_sales_daily s
        JOIN dim_products p ON p.product_id = s.product_id
        WHERE 1=1 {clause}
        GROUP BY p.category
        ORDER BY revenue DESC
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )


def get_by_warehouse(date_from: Optional[str] = None, date_to: Optional[str] = None) -> list[dict]:
    clause = date_range_clause(date_from, date_to, column="s.date_id")
    return query_records(
        f"""
        SELECT w.warehouse_name, w.city, SUM(s.revenue) AS revenue
        FROM fact_sales_daily s
        JOIN dim_warehouses w ON w.warehouse_id = s.warehouse_id
        WHERE 1=1 {clause}
        GROUP BY w.warehouse_name, w.city
        ORDER BY revenue DESC
        """,
        {"date_from": date_from, "date_to": date_to},
    )


def get_avg_order_value(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    """Average order value, computed from the synthetic per-order estimate in
    fact_orders (see backfill_synthetic_orders' docstring for what's real vs.
    estimated). Replaces the earlier per-sales-line proxy (average revenue
    per product/warehouse/day row) now that a proper, if still estimated,
    order-level figure exists - that proxy's own docstring flagged it as a
    stand-in for exactly this. Originally read the now-retired
    fact_orders_hourly bucket table; re-pointed at fact_orders when that
    table was superseded by the customer/order-grain layer."""
    clause = warehouse_filter_clause(warehouse_id) + date_range_clause(date_from, date_to, column="order_date")
    row = query_one(
        f"""
        SELECT COALESCE(SUM(order_value), 0) AS total_revenue, COUNT(*) AS total_orders
        FROM fact_orders
        WHERE 1=1 {clause}
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    total_orders = int(row.get("total_orders") or 0)
    total_revenue = float(row.get("total_revenue") or 0)
    avg_order_value = round(total_revenue / total_orders, 2) if total_orders else None
    return {"avg_order_value": avg_order_value, "total_orders": total_orders}
