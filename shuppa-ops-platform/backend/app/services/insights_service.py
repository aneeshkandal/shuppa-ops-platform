"""Key Business Insights service.

Generates the short natural-language callouts shown in each dashboard
page's own "Key Business Insights" card (Stock Summary, Sales Analytics,
Supplier Summary, Stock Optimizer, Delivery Risk Predictor). This is
deliberately NOT a new data source: every insight here is computed purely
by calling the same page-level service functions (stock_service,
sales_service, supplier_service, storage_optimizer, delivery_risk_service)
and alerts_service's existing "possible contributing factor" pattern that
already power each page's own KPIs/tables/charts - no new tables, no new
ML model, nothing tracked here that isn't already visible elsewhere on that
same page. See the project's build notes ("Sales Analytics gap analysis")
for the brainstorm this was built from and why each page's insight list
ended up the way it did (the full list was deliberately kept, not trimmed
to 2-4 per page, per the user's explicit request).

Each get_*_insights() function returns {"insights": [{"key", "label",
"text"}, ...]} - one entry per pill the frontend's KeyInsightsCard renders
as a tab. `text` is plain text (the frontend renders it directly, no
markup). Every insight is defensive about missing/empty data (a brand-new
warehouse with no sales yet, a period with no late deliveries, etc.) -
each one degrades to an honest "not enough data" style sentence rather than
raising, since one insight failing shouldn't break the whole card.
"""

from typing import Optional

from app.services import (
    admin_service,
    alerts_service,
    delivery_risk_service,
    sales_service,
    stock_service,
    storage_optimizer,
    supplier_service,
)
from app.services.db_utils import query_records


def _delta_word(pct: Optional[float]) -> str:
    """Same +/-0.5% "flat" deadband used across this app's KPI-delta pills
    (see lib/format.ts's formatDelta on the frontend) so an insight's wording
    never disagrees with the KPI card sitting right next to it."""
    if pct is None:
        return "changed"
    if pct > 0.5:
        return "up"
    if pct < -0.5:
        return "down"
    return "flat"


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_eur(value) -> str:
    try:
        return f"€{float(value):,.0f}"
    except (TypeError, ValueError):
        return "€0"


def _warehouse_name_map() -> dict:
    return {w["warehouse_id"]: w["warehouse_name"] for w in admin_service.list_warehouses()}


# ---------------------------------------------------------------------------
# Stock Summary
# ---------------------------------------------------------------------------

def _worst_warehouse_by_risk(date_from: Optional[str], date_to: Optional[str]) -> Optional[tuple]:
    """Which warehouse currently has the worst inventory-at-risk share
    (LOW + CRITICAL stock-status lines, as a % of that warehouse's own
    catalog) - only meaningful when comparing across warehouses, so this is
    always computed dashboard-wide regardless of the page's own warehouse
    filter. Returns (warehouse_name, risk_pct) for the worst one, or None if
    there's no warehouse/inventory data at all."""
    warehouses = admin_service.list_warehouses()
    worst = None
    for w in warehouses:
        summary = stock_service.get_summary(w["warehouse_id"], date_from, date_to)
        if not summary:
            continue
        risk_pct = (summary.get("low_pct") or 0) + (summary.get("critical_pct") or 0)
        if worst is None or risk_pct > worst[1]:
            worst = (w["warehouse_name"], risk_pct)
    return worst


def _estimate_reorder_cost(reorder_rows: list[dict]) -> float:
    """get_reorder_suggestions() returns a suggested quantity per product but
    no cost (it's a stock-levels view, not a pricing one) - this joins in
    dim_products.unit_cost for just the products involved, in one query,
    rather than pulling cost into stock_service itself for a single insight."""
    if not reorder_rows:
        return 0.0
    product_ids = list({r["product_id"] for r in reorder_rows})
    costs = query_records(
        "SELECT product_id, unit_cost FROM dim_products WHERE product_id = ANY(:ids)", {"ids": product_ids}
    )
    cost_map = {c["product_id"]: c["unit_cost"] for c in costs}
    total = 0.0
    for r in reorder_rows:
        unit_cost = cost_map.get(r["product_id"]) or 0
        total += (r.get("suggested_reorder_qty") or 0) * float(unit_cost)
    return total


def get_stock_insights(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    insights = []

    summary = stock_service.get_summary(warehouse_id, date_from, date_to)
    stockout_delta = (summary.get("comparison") or {}).get("deltas", {}).get("stockout_pct")
    if stockout_delta and stockout_delta.get("pct") is not None:
        direction = _delta_word(stockout_delta["pct"])
        text = (
            f"Stockout risk is at {_fmt_pct(summary.get('stockout_pct'))}, {direction} from "
            f"{_fmt_pct(stockout_delta['previous'])} last period."
        )
    else:
        text = f"Stockout risk is currently {_fmt_pct(summary.get('stockout_pct'))} of products."
    insights.append({"key": "stockout_risk", "label": "Stockout Risk Trend", "text": text})

    dead = stock_service.get_dead_stock(warehouse_id)
    items = dead.get("items", [])
    if items:
        by_category: dict = {}
        for item in items:
            cat = item.get("category") or "Uncategorized"
            by_category[cat] = by_category.get(cat, 0) + (item.get("stock_value") or 0)
        top_category = max(by_category, key=by_category.get) if by_category else None
        cat_text = f", mostly in {top_category}" if top_category else ""
        text = (
            f"{_fmt_eur(dead.get('total_value_tied_up'))} worth of stock has had zero sales in "
            f"{dead.get('dead_stock_days_threshold')}+ days{cat_text}."
        )
    else:
        text = "No dead stock detected right now - every carried product has recent sales."
    insights.append({"key": "dead_stock", "label": "Dead Stock", "text": text})

    worst = _worst_warehouse_by_risk(date_from, date_to)
    if worst and worst[1] > 0:
        text = f"{worst[0]} has the worst inventory-at-risk share right now, at {_fmt_pct(worst[1])}."
    elif worst:
        text = "No warehouse currently has a meaningful inventory-at-risk share - stock levels look healthy across the board."
    else:
        text = "No warehouse inventory data available to compare."
    insights.append({"key": "inventory_at_risk_by_warehouse", "label": "Inventory at Risk by Warehouse", "text": text})

    reorder_rows = stock_service.get_reorder_suggestions(500, warehouse_id, date_from, date_to)
    if reorder_rows:
        cost = _estimate_reorder_cost(reorder_rows)
        text = (
            f"{len(reorder_rows)} product(s) are below their reorder point right now. Restocking all of them "
            f"would cost an estimated {_fmt_eur(cost)}."
        )
    else:
        text = "Nothing is currently below its reorder point."
    insights.append({"key": "reorder_needs", "label": "Reorder Needs", "text": text})

    hint = alerts_service._hint_for_stock_alert(warehouse_id)
    text = hint or "No strong supplier-driven contributing factor detected for current stock risk levels."
    insights.append({"key": "root_cause", "label": "Root Cause", "text": text})

    return {"insights": insights}


# ---------------------------------------------------------------------------
# Sales Analytics
# ---------------------------------------------------------------------------

def get_sales_insights(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    insights = []

    kpis = sales_service.get_kpis(warehouse_id, date_from, date_to)
    comparison = kpis.get("comparison")
    revenue_delta = (comparison or {}).get("deltas", {}).get("total_revenue") if comparison else None

    best_driver = None
    if comparison:
        current_cat = sales_service.get_by_category(warehouse_id, date_from, date_to)
        prev_cat = sales_service.get_by_category(warehouse_id, comparison["previous_from"], comparison["previous_to"])
        prev_map = {c["category"]: c.get("revenue") or 0 for c in prev_cat}
        for c in current_cat:
            cat = c.get("category")
            if not cat:
                continue
            diff = (c.get("revenue") or 0) - prev_map.get(cat, 0)
            if best_driver is None or abs(diff) > abs(best_driver[1]):
                best_driver = (cat, diff)

    if revenue_delta and revenue_delta.get("pct") is not None:
        direction = _delta_word(revenue_delta["pct"])
        text = f"Revenue is {direction} {_fmt_pct(abs(revenue_delta['pct']))} vs last period"
    else:
        text = f"Total revenue this period is {_fmt_eur(kpis.get('total_revenue'))}"
    if best_driver and best_driver[0]:
        cat, diff = best_driver
        if diff > 0:
            text += f", driven mainly by {cat} (+{_fmt_eur(diff)})."
        elif diff < 0:
            text += f"; {cat} pulled back the most ({_fmt_eur(diff)})."
        else:
            text += "."
    else:
        text += "."
    insights.append({"key": "revenue_driver", "label": "Revenue Driver", "text": text})

    by_wh = sales_service.get_by_warehouse(date_from, date_to)
    if by_wh:
        total = sum((w.get("revenue") or 0) for w in by_wh) or 1
        top = by_wh[0]
        share = 100 * (top.get("revenue") or 0) / total
        text = f"{top['warehouse_name']} contributed the largest share of total revenue at {_fmt_pct(share)}."
    else:
        text = "No warehouse revenue data available for this period."
    insights.append({"key": "warehouse_contribution", "label": "Warehouse Contribution", "text": text})

    avg = sales_service.get_avg_order_value(warehouse_id, date_from, date_to)
    avg_val = avg.get("avg_order_value")
    if comparison and avg_val is not None:
        prev_avg = sales_service.get_avg_order_value(
            warehouse_id, comparison["previous_from"], comparison["previous_to"]
        )
        prev_val = prev_avg.get("avg_order_value")
        if prev_val:
            pct = (float(avg_val) - float(prev_val)) / float(prev_val) * 100
            direction = _delta_word(pct)
            text = f"Average order value is {_fmt_eur(avg_val)}, {direction} {_fmt_pct(abs(pct))} vs last period."
        else:
            text = f"Average order value is {_fmt_eur(avg_val)}."
    elif avg_val is not None:
        text = f"Average order value is {_fmt_eur(avg_val)}."
    else:
        text = "Not enough order data to compute an average order value."
    insights.append({"key": "avg_order_value", "label": "Avg. Order Value", "text": text})

    forecast = sales_service.get_forecast(7, 30, warehouse_id, date_from, date_to)
    direction = forecast.get("trend_direction")
    forecast_points = forecast.get("forecast") or []
    if direction and forecast_points:
        total_forecast_rev = sum((f.get("revenue") or 0) for f in forecast_points)
        if direction == "up":
            text = f"The 7-day forecast points upward, projecting roughly {_fmt_eur(total_forecast_rev)} in revenue ahead."
        elif direction == "down":
            text = f"The 7-day forecast points downward, projecting roughly {_fmt_eur(total_forecast_rev)} in revenue ahead."
        else:
            text = f"The 7-day forecast is essentially flat, projecting roughly {_fmt_eur(total_forecast_rev)} in revenue ahead."
    else:
        text = forecast.get("note") or "Not enough history to project a forecast yet."
    insights.append({"key": "forecast_outlook", "label": "Forecast Outlook", "text": text})

    return {"insights": insights}


# ---------------------------------------------------------------------------
# Supplier Summary
# ---------------------------------------------------------------------------

def get_supplier_insights(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    insights = []

    performance = supplier_service.get_performance(warehouse_id, date_from, date_to)
    if performance:
        worst = min(performance, key=lambda p: p.get("on_time_delivery_pct", 100))
        text = (
            f"{worst['supplier_name']} has the lowest on-time rate at "
            f"{_fmt_pct(worst.get('on_time_delivery_pct'))} ({worst.get('orders_completed')} orders)."
        )
    else:
        text = "No supplier delivery data available for this period."
    insights.append({"key": "worst_supplier", "label": "Worst On-Time Supplier", "text": text})

    kpis = supplier_service.get_kpis(warehouse_id, date_from, date_to)
    comparison = kpis.get("comparison")
    late_delta = (comparison or {}).get("deltas", {}).get("late_delivery_pct") if comparison else None
    if late_delta and late_delta.get("pct") is not None:
        direction = _delta_word(late_delta["pct"])
        text = (
            f"Late deliveries are {direction}, now at {_fmt_pct(kpis.get('late_delivery_pct'))} of orders "
            f"(was {_fmt_pct(late_delta['previous'])})."
        )
    else:
        text = f"Late deliveries are currently {_fmt_pct(kpis.get('late_delivery_pct'))} of orders."
    insights.append({"key": "late_delivery_trend", "label": "Late Delivery Trend", "text": text})

    value_delta = (comparison or {}).get("deltas", {}).get("total_order_value") if comparison else None
    if value_delta and value_delta.get("pct") is not None:
        direction = _delta_word(value_delta["pct"])
        text = (
            f"Total order value this period is {_fmt_eur(kpis.get('total_order_value'))}, {direction} "
            f"{_fmt_pct(abs(value_delta['pct']))} vs last period."
        )
    else:
        text = f"Total order value this period is {_fmt_eur(kpis.get('total_order_value'))}."
    insights.append({"key": "order_value_trend", "label": "Order Value Trend", "text": text})

    return {"insights": insights}


# ---------------------------------------------------------------------------
# Stock Optimizer
# ---------------------------------------------------------------------------

def get_storage_insights(warehouse_id: Optional[int] = None) -> dict:
    insights = []

    heatmap = storage_optimizer.get_heatmap(warehouse_id)
    if heatmap:
        by_wh: dict = {}
        for loc in heatmap:
            by_wh.setdefault(loc["warehouse_id"], []).append(loc.get("utilization_pct") or 0)
        avg_util = {wid: (sum(vals) / len(vals)) for wid, vals in by_wh.items() if vals}
        if avg_util:
            names = _warehouse_name_map()
            fullest_wid = max(avg_util, key=avg_util.get)
            emptiest_wid = min(avg_util, key=avg_util.get)
            fullest_pct = avg_util[fullest_wid]
            emptiest_pct = avg_util[emptiest_wid]
            if fullest_pct >= 80:
                text = (
                    f"{names.get(fullest_wid, f'Warehouse {fullest_wid}')} is at {_fmt_pct(fullest_pct)} average "
                    "utilization - approaching capacity."
                )
            elif emptiest_pct <= 30:
                text = (
                    f"{names.get(emptiest_wid, f'Warehouse {emptiest_wid}')} is only {_fmt_pct(emptiest_pct)} "
                    "utilized - the most underutilized warehouse right now."
                )
            else:
                text = f"Utilization is currently balanced across warehouses, {_fmt_pct(emptiest_pct)} to {_fmt_pct(fullest_pct)}."
        else:
            text = "No utilization data available."
    else:
        text = "No storage location data available."
    insights.append({"key": "capacity_watch", "label": "Capacity Watch", "text": text})

    top_movers = storage_optimizer.get_top_movers(warehouse_id, limit=1)
    if top_movers:
        m = top_movers[0]
        text = f"{m['product_name']} had the fastest turnover this period, averaging {m.get('avg_daily_units')} units/day."
    else:
        text = "No sales velocity data available for this period."
    insights.append({"key": "top_mover", "label": "Top Mover", "text": text})

    pending = storage_optimizer.get_pending_placement(500)
    if pending:
        text = f"{len(pending)} newly added product(s) are still awaiting a storage location."
    else:
        text = "Nothing is currently waiting on placement - every catalogued product has a slot."
    insights.append({"key": "pending_putaway", "label": "Pending Putaway", "text": text})

    return {"insights": insights}


# ---------------------------------------------------------------------------
# Delivery Risk Predictor
# ---------------------------------------------------------------------------

def get_delivery_insights(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    """May raise delivery_risk_service.ModelNotTrainedError (propagated
    from get_kpis' load_model() call) - the router catches this the same
    way every other /delivery endpoint does, since without a trained model
    there's nothing meaningful to say here either."""
    insights = []

    kpis = delivery_risk_service.get_kpis(warehouse_id, date_from, date_to)
    comparison = kpis.get("comparison")

    risky_current = delivery_risk_service.get_risky_orders(500, warehouse_id, date_from, date_to)
    high_current = len([r for r in risky_current if r.get("risk_level") == "HIGH"])
    trend_text = ""
    if comparison:
        risky_prev = delivery_risk_service.get_risky_orders(
            500, warehouse_id, comparison["previous_from"], comparison["previous_to"]
        )
        high_prev = len([r for r in risky_prev if r.get("risk_level") == "HIGH"])
        diff = high_current - high_prev
        if diff > 0:
            trend_text = f", up from {high_prev} last period"
        elif diff < 0:
            trend_text = f", down from {high_prev} last period"
        else:
            trend_text = " (unchanged from last period)"
    text = f"{high_current} purchase order(s) are currently flagged HIGH risk for late delivery{trend_text}."
    insights.append({"key": "high_risk_trend", "label": "High Risk Trend", "text": text})

    avg_delay = kpis.get("avg_delay_days")
    delay_delta = (comparison or {}).get("deltas", {}).get("avg_delay_days") if comparison else None
    if avg_delay is not None and delay_delta and delay_delta.get("pct") is not None:
        direction = _delta_word(delay_delta["pct"])
        text = (
            f"Average delay for late deliveries is {float(avg_delay):.1f} days, {direction} from "
            f"{float(delay_delta['previous']):.1f} days last period."
        )
    elif avg_delay is not None and avg_delay > 0:
        text = f"Average delay for late deliveries is {float(avg_delay):.1f} days this period."
    else:
        text = "No delayed deliveries recorded this period."
    insights.append({"key": "avg_delay_trend", "label": "Average Delay Trend", "text": text})

    by_supplier: dict = {}
    for r in risky_current:
        name = r.get("supplier_name")
        if name:
            by_supplier.setdefault(name, []).append(r.get("delay_days") or 0)
    if by_supplier:
        worst_name = max(by_supplier, key=lambda n: len(by_supplier[n]))
        delays = by_supplier[worst_name]
        avg_delay_worst = sum(delays) / len(delays)
        text = (
            f"{worst_name} accounts for the most late deliveries this period "
            f"({len(delays)} orders, avg delay {avg_delay_worst:.1f} days)."
        )
    else:
        text = "No late deliveries recorded this period."
    insights.append({"key": "riskiest_supplier", "label": "Riskiest Supplier", "text": text})

    return {"insights": insights}
