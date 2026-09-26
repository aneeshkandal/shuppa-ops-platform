"""Delivery Risk Predictor service.

Loads the logistic-regression coefficients trained by
scripts/seed_database.py (backend/app/ml_model.json) and scores new
supplier/warehouse/order combinations against them, using live features
pulled from the database (current supplier on-time rate, current warehouse
utilization) so predictions stay fresh as new data lands.

Honesty note: the underlying historical PO/delivery data in this project has
only a weak real correlation between these features and late deliveries
(train AUC ~0.53 - see ml_model.json's train_auc). Absolute probabilities
therefore cluster near the fleet's base late-rate; risk_level is assigned by
percentile rank within the training population (risk_thresholds in the model
file) rather than a fixed 50% cutoff, so the UI still shows a meaningful
relative spread between "safer" and "riskier" orders.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

from app.models.schemas import DeliveryRiskRequest
from app.services.db_utils import (
    compute_deltas,
    date_range_clause,
    query_one,
    query_records,
    resolve_comparison_window,
)

_KPI_DELTA_KEYS = ["total_deliveries", "late_count", "late_rate_pct", "avg_delay_days"]

MODEL_PATH = Path(__file__).resolve().parent.parent / "ml_model.json"


class ModelNotTrainedError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_model() -> dict:
    if not MODEL_PATH.exists():
        raise ModelNotTrainedError(
            f"{MODEL_PATH} not found. Run `python scripts/seed_database.py` first - it "
            "trains this model from your real purchase-order/delivery history and writes "
            "this file."
        )
    with open(MODEL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _kpi_totals(
    warehouse_id: Optional[int], date_from: Optional[str], date_to: Optional[str]
) -> dict:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="d.actual_delivery_date")
    row = query_one(
        f"""
        SELECT
            COUNT(*) AS total_deliveries,
            COUNT(*) FILTER (WHERE d.delivery_status = 'LATE') AS late_count,
            COALESCE(AVG(d.delay_days) FILTER (WHERE d.delivery_status = 'LATE'), 0) AS avg_delay_days
        FROM fact_deliveries d
        JOIN fact_purchase_orders po ON po.po_id = d.po_id
        WHERE 1=1 {wh_clause} {date_clause}
        """,
        {"warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    total = row["total_deliveries"] or 1
    row["late_rate_pct"] = round(100.0 * row["late_count"] / total, 1)
    return row


def get_kpis(
    warehouse_id: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None
) -> dict:
    row = _kpi_totals(warehouse_id, date_from, date_to)
    model = load_model()
    row["model"] = {
        "train_accuracy": model["train_accuracy"],
        "train_auc": model["train_auc"],
        "trained_at": model["trained_at"],
        "n_training_rows": model["n_training_rows"],
    }

    wh_clause = "AND warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    prev_from, prev_to = resolve_comparison_window(
        date_from,
        date_to,
        f"SELECT MAX(actual_delivery_date) AS d FROM fact_deliveries WHERE 1=1 {wh_clause}"
        if warehouse_id is None
        else (
            "SELECT MAX(d.actual_delivery_date) AS d FROM fact_deliveries d "
            "JOIN fact_purchase_orders po ON po.po_id = d.po_id WHERE po.warehouse_id = :warehouse_id"
        ),
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


def get_options(warehouse_id: Optional[int] = None) -> dict:
    if warehouse_id is not None:
        suppliers = query_records(
            "SELECT supplier_id, supplier_name FROM dim_suppliers "
            "WHERE warehouse_id IS NULL OR warehouse_id = :w ORDER BY supplier_name",
            {"w": warehouse_id},
        )
        warehouses = query_records(
            "SELECT warehouse_id, warehouse_name FROM dim_warehouses WHERE warehouse_id = :w", {"w": warehouse_id}
        )
    else:
        suppliers = query_records("SELECT supplier_id, supplier_name FROM dim_suppliers ORDER BY supplier_name")
        warehouses = query_records("SELECT warehouse_id, warehouse_name FROM dim_warehouses ORDER BY warehouse_id")
    products = query_records(
        "SELECT product_id, product_name FROM dim_products ORDER BY product_name LIMIT 500"
    )
    return {"suppliers": suppliers, "warehouses": warehouses, "products": products}


def _risk_level(probability: float, thresholds: dict) -> str:
    if probability <= thresholds["low_max"]:
        return "LOW"
    if probability <= thresholds["medium_max"]:
        return "MEDIUM"
    return "HIGH"


def predict(req: DeliveryRiskRequest) -> dict:
    model = load_model()

    supplier_row = query_one(
        """
        SELECT
            COALESCE(1.0 - AVG((d.delivery_status = 'LATE')::int), :fallback) AS on_time_rate,
            s.supplier_name
        FROM dim_suppliers s
        LEFT JOIN fact_purchase_orders po ON po.supplier_id = s.supplier_id
        LEFT JOIN fact_deliveries d ON d.po_id = po.po_id
        WHERE s.supplier_id = :supplier_id
        GROUP BY s.supplier_name
        """,
        {"supplier_id": req.supplier_id, "fallback": model["supplier_on_time_rate_overall"]},
    )
    if not supplier_row:
        raise ValueError(f"supplier_id {req.supplier_id} not found")

    warehouse_row = query_one(
        """
        SELECT
            COALESCE(AVG(stock_on_hand::float / NULLIF(max_stock_level, 0)) * 100, :fallback) AS utilization_pct,
            (SELECT warehouse_name FROM dim_warehouses WHERE warehouse_id = :warehouse_id) AS warehouse_name
        FROM fact_inventory_daily
        WHERE warehouse_id = :warehouse_id
        """,
        {"warehouse_id": req.warehouse_id, "fallback": model["warehouse_utilization_pct_overall"]},
    )

    if req.product_id is not None:
        product_row = query_one(
            "SELECT unit_cost, product_name FROM dim_products WHERE product_id = :pid", {"pid": req.product_id}
        )
        unit_cost = product_row.get("unit_cost") if product_row else None
    else:
        product_row = {}
        unit_cost = None
    if not unit_cost:
        unit_cost = query_one("SELECT AVG(unit_cost) AS v FROM dim_products")["v"]

    order_cost = float(unit_cost) * req.order_quantity

    features = {
        "supplier_on_time_rate": float(supplier_row["on_time_rate"]),
        "order_quantity": float(req.order_quantity),
        "lead_time_days": float(req.lead_time_days),
        "warehouse_utilization_pct": float(warehouse_row["utilization_pct"]),
        "order_cost": order_cost,
    }

    x = np.array([features[name] for name in model["feature_names"]], dtype=float)
    means = np.array(model["means"])
    stds = np.array(model["stds"])
    # A couple of these features (notably warehouse_utilization_pct) have
    # very little variance in the training data, so their std is tiny and a
    # realistic "near capacity" input can standardize to an extreme z-score.
    # Clip so one out-of-distribution feature can't single-handedly saturate
    # the sigmoid to 0 or 1.
    xs = np.clip((x - means) / stds, -5, 5)
    z = model["intercept"] + float(np.dot(xs, model["coefficients"]))
    probability = float(1.0 / (1.0 + np.exp(-z)))
    risk_level = _risk_level(probability, model["risk_thresholds"])

    def factor(name: str, value: float, overall: float, higher_is_worse: bool, fmt: str) -> dict:
        delta_pct = (value - overall) / overall * 100 if overall else 0
        worse = (delta_pct > 0) == higher_is_worse
        return {
            "name": name,
            "value": round(value, 2),
            "fleet_average": round(overall, 2),
            "comparison": f"{abs(round(delta_pct))}% {'above' if delta_pct > 0 else 'below'} average",
            "is_unfavorable": worse and abs(delta_pct) > 5,
            "display": fmt.format(value),
        }

    explanation = [
        factor(
            "Supplier Reliability",
            features["supplier_on_time_rate"] * 100,
            model["supplier_on_time_rate_overall"] * 100,
            higher_is_worse=False,
            fmt="{:.1f}%",
        ),
        factor(
            "Order Quantity",
            features["order_quantity"],
            model["order_quantity_mean"],
            higher_is_worse=True,
            fmt="{:.0f} units",
        ),
        factor(
            "Warehouse Utilization",
            features["warehouse_utilization_pct"],
            model["warehouse_utilization_pct_overall"],
            higher_is_worse=True,
            fmt="{:.1f}%",
        ),
        factor(
            "Lead Time",
            features["lead_time_days"],
            model["lead_time_days_mean"],
            higher_is_worse=False,
            fmt="{:.0f} days",
        ),
    ]

    return {
        "supplier_name": supplier_row.get("supplier_name"),
        "warehouse_name": warehouse_row.get("warehouse_name"),
        "product_name": product_row.get("product_name") if product_row else None,
        "risk_probability": round(probability, 3),
        "risk_level": risk_level,
        "explanation": explanation,
        "note": (
            "Historical PO data in this dataset has limited predictive signal "
            f"(train AUC {model['train_auc']}), so treat this as a directional, explainable "
            "risk score rather than a precise probability."
        ),
    }


def get_risky_orders(
    limit: int = 15,
    warehouse_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    wh_clause = "AND po.warehouse_id = :warehouse_id" if warehouse_id is not None else ""
    date_clause = date_range_clause(date_from, date_to, column="d.actual_delivery_date")
    rows = query_records(
        f"""
        SELECT
            po.po_id, s.supplier_name, p.product_name, w.warehouse_name,
            po.order_quantity, d.delay_days, d.actual_delivery_date
        FROM fact_deliveries d
        JOIN fact_purchase_orders po ON po.po_id = d.po_id
        JOIN dim_suppliers s ON s.supplier_id = po.supplier_id
        JOIN dim_products p ON p.product_id = po.product_id
        JOIN dim_warehouses w ON w.warehouse_id = po.warehouse_id
        WHERE d.delivery_status = 'LATE' {wh_clause} {date_clause}
        ORDER BY d.delay_days DESC, d.actual_delivery_date DESC
        LIMIT :limit
        """,
        {"limit": limit, "warehouse_id": warehouse_id, "date_from": date_from, "date_to": date_to},
    )
    for row in rows:
        if row["delay_days"] >= 7:
            row["risk_level"] = "HIGH"
        elif row["delay_days"] >= 3:
            row["risk_level"] = "MEDIUM"
        else:
            row["risk_level"] = "LOW"
    return rows
