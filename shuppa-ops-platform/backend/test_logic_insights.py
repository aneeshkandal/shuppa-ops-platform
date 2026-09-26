"""Stub-based logic tests for insights_service.py (Key Business Insights).

Follows the same pattern as test_logic.py: stub out sqlalchemy so importing
app.database/app.services.* doesn't need a real DB connection, then
monkeypatch each underlying service function that insights_service calls
(stock_service.get_summary, sales_service.get_kpis, etc.) with fixed
in-memory return values, so every get_*_insights() function can be exercised
purely in-process. This checks the TEXT-GENERATION logic (formatting,
picking the worst/best of a set, handling empty data gracefully) - not the
underlying SQL, which each service function already owns and is tested (or
smoke-tested against a real Postgres) separately.
"""

import sys
import types

sys.path.insert(0, ".")

fake_sa = types.ModuleType("sqlalchemy")
fake_sa.create_engine = lambda *a, **k: object()
fake_sa.text = lambda s: s
sys.modules["sqlalchemy"] = fake_sa

# insights_service pulls in admin_service and stock_service, both of which
# import app.auth - and app.auth imports fastapi/jose/passlib, none of which
# are installed in this sandbox (only used for local syntax/logic checks;
# the real environment on the user's machine has the full venv - see
# requirements.txt). None of these need to be functionally correct here:
# these tests never exercise login/token/password-hashing code paths, only
# insights_service's own text-generation logic, so the stubs just need to
# keep app.auth's module-level statements (class CurrentUser(BaseModel),
# pwd_context = CryptContext(...), oauth2_scheme = OAuth2PasswordBearer(...),
# Depends(...) as a default arg) from raising ImportError/TypeError.
fake_jose = types.ModuleType("jose")


class _FakeJWTError(Exception):
    pass


fake_jose.JWTError = _FakeJWTError
fake_jose.jwt = types.SimpleNamespace(encode=lambda *a, **k: "", decode=lambda *a, **k: {})
sys.modules["jose"] = fake_jose

fake_passlib = types.ModuleType("passlib")
fake_passlib_context = types.ModuleType("passlib.context")


class _FakeCryptContext:
    def __init__(self, *a, **k):
        pass

    def hash(self, *a, **k):
        return ""

    def verify(self, *a, **k):
        return False


fake_passlib_context.CryptContext = _FakeCryptContext
sys.modules["passlib"] = fake_passlib
sys.modules["passlib.context"] = fake_passlib_context

fake_fastapi = types.ModuleType("fastapi")
fake_fastapi.Depends = lambda x=None: x


class _FakeHTTPException(Exception):
    def __init__(self, status_code=500, detail=None, headers=None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


fake_fastapi.HTTPException = _FakeHTTPException
fake_fastapi.Request = object
fake_fastapi.status = types.SimpleNamespace(HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403)
fake_fastapi.Query = lambda *a, **k: None
fake_fastapi_security = types.ModuleType("fastapi.security")


class _FakeOAuth2PasswordBearer:
    def __init__(self, *a, **k):
        pass


fake_fastapi_security.OAuth2PasswordBearer = _FakeOAuth2PasswordBearer
sys.modules["fastapi"] = fake_fastapi
sys.modules["fastapi.security"] = fake_fastapi_security

import app.services.insights_service as ins
from app.services import (
    admin_service,
    alerts_service,
    delivery_risk_service,
    sales_service,
    stock_service,
    storage_optimizer,
    supplier_service,
)

# ---------------------------------------------------------------------------
# Pure formatting helpers
# ---------------------------------------------------------------------------
assert ins._delta_word(5.0) == "up"
assert ins._delta_word(-5.0) == "down"
assert ins._delta_word(0.1) == "flat"
assert ins._delta_word(None) == "changed"
assert ins._fmt_pct(8.2) == "8.2%"
assert ins._fmt_pct(None) == "n/a"
assert ins._fmt_eur(18420) == "€18,420"
assert ins._fmt_eur("not a number") == "€0"
print("formatting helpers OK")

# ---------------------------------------------------------------------------
# get_stock_insights
# ---------------------------------------------------------------------------
admin_service.list_warehouses = lambda: [
    {"warehouse_id": 1, "warehouse_name": "Lombard"},
    {"warehouse_id": 2, "warehouse_name": "Kimmage"},
]


def fake_get_summary(warehouse_id=None, date_from=None, date_to=None):
    # Warehouse 2 has a much worse risk share than warehouse 1 or the
    # combined (warehouse_id=None) view.
    if warehouse_id == 2:
        return {
            "stockout_pct": 8.2, "low_pct": 30.0, "critical_pct": 10.0,
            "comparison": {"deltas": {"stockout_pct": {"previous": 6.9, "pct": 18.8}}},
        }
    return {
        "stockout_pct": 8.2, "low_pct": 5.0, "critical_pct": 2.0,
        "comparison": {"deltas": {"stockout_pct": {"previous": 6.9, "pct": 18.8}}},
    }


stock_service.get_summary = fake_get_summary
stock_service.get_dead_stock = lambda warehouse_id=None: {
    "items": [
        {"category": "Electronics", "stock_value": 15000},
        {"category": "Dairy", "stock_value": 3420},
    ],
    "total_value_tied_up": 18420,
    "dead_stock_days_threshold": 45,
}
stock_service.get_reorder_suggestions = lambda limit, warehouse_id=None, date_from=None, date_to=None: [
    {"product_id": 1, "suggested_reorder_qty": 100},
    {"product_id": 2, "suggested_reorder_qty": 50},
]
ins.query_records = lambda sql, params=None: [
    {"product_id": 1, "unit_cost": 2.0},
    {"product_id": 2, "unit_cost": 5.0},
]
alerts_service._hint_for_stock_alert = lambda warehouse_id=None: (
    "Possible contributing factor: average supplier on-time delivery here is 78% right now - "
    "late shipments may be behind some of this."
)

stock_insights = ins.get_stock_insights(None)["insights"]
by_key = {i["key"]: i["text"] for i in stock_insights}
assert len(stock_insights) == 5
assert "up from 6.9%" in by_key["stockout_risk"]
assert "€18,420" in by_key["dead_stock"] and "Electronics" in by_key["dead_stock"]
assert "Kimmage" in by_key["inventory_at_risk_by_warehouse"]
assert "€450" in by_key["reorder_needs"]  # 100*2.0 + 50*5.0 = 450
assert "supplier on-time delivery" in by_key["root_cause"]
print("get_stock_insights OK:", by_key)

# Empty-data branches shouldn't raise.
stock_service.get_dead_stock = lambda warehouse_id=None: {"items": [], "total_value_tied_up": 0, "dead_stock_days_threshold": 60}
stock_service.get_reorder_suggestions = lambda limit, warehouse_id=None, date_from=None, date_to=None: []
alerts_service._hint_for_stock_alert = lambda warehouse_id=None: None
empty_stock = ins.get_stock_insights(None)["insights"]
empty_by_key = {i["key"]: i["text"] for i in empty_stock}
assert "No dead stock" in empty_by_key["dead_stock"]
assert "Nothing is currently below" in empty_by_key["reorder_needs"]
assert "No strong" in empty_by_key["root_cause"]
print("get_stock_insights empty-data branches OK")

# ---------------------------------------------------------------------------
# get_sales_insights
# ---------------------------------------------------------------------------
sales_service.get_kpis = lambda warehouse_id=None, date_from=None, date_to=None: {
    "total_revenue": 120000,
    "comparison": {
        "previous_from": "2026-01-01", "previous_to": "2026-01-31",
        "deltas": {"total_revenue": {"previous": 107000, "pct": 12.1}},
    },
}


def fake_by_category(warehouse_id=None, date_from=None, date_to=None):
    if date_from == "2026-01-01":  # previous period
        return [{"category": "Dairy", "revenue": 20000}, {"category": "Snacks", "revenue": 15000}]
    return [{"category": "Dairy", "revenue": 28300}, {"category": "Snacks", "revenue": 15200}]


sales_service.get_by_category = fake_by_category
sales_service.get_by_warehouse = lambda date_from=None, date_to=None: [
    {"warehouse_name": "Kimmage", "revenue": 49200},
    {"warehouse_name": "Lombard", "revenue": 40000},
    {"warehouse_name": "Finglas", "revenue": 30800},
]


def fake_avg_order_value(warehouse_id=None, date_from=None, date_to=None):
    if date_from == "2026-01-01":
        return {"avg_order_value": 18.50, "total_orders": 900}
    return {"avg_order_value": 19.90, "total_orders": 950}


sales_service.get_avg_order_value = fake_avg_order_value
sales_service.get_forecast = lambda *a, **k: {
    "trend_direction": "up",
    "forecast": [{"revenue": 4000}, {"revenue": 4200}],
}

sales_insights = ins.get_sales_insights(None)["insights"]
sales_by_key = {i["key"]: i["text"] for i in sales_insights}
assert len(sales_insights) == 4
assert "up 12.1%" in sales_by_key["revenue_driver"] and "Dairy" in sales_by_key["revenue_driver"]
assert "Kimmage" in sales_by_key["warehouse_contribution"] and "41.0%" in sales_by_key["warehouse_contribution"]
assert "€20" in sales_by_key["avg_order_value"] and "up" in sales_by_key["avg_order_value"]
assert "upward" in sales_by_key["forecast_outlook"] and "€8,200" in sales_by_key["forecast_outlook"]
print("get_sales_insights OK:", sales_by_key)

# ---------------------------------------------------------------------------
# get_supplier_insights
# ---------------------------------------------------------------------------
supplier_service.get_performance = lambda warehouse_id=None, date_from=None, date_to=None: [
    {"supplier_name": "Dublin Fresh Foods", "on_time_delivery_pct": 61.0, "orders_completed": 40},
    {"supplier_name": "Emerald Wholesale", "on_time_delivery_pct": 88.0, "orders_completed": 25},
]
supplier_service.get_kpis = lambda warehouse_id=None, date_from=None, date_to=None: {
    "late_delivery_pct": 19.0,
    "total_order_value": 55000,
    "comparison": {
        "deltas": {
            "late_delivery_pct": {"previous": 15.0, "pct": 26.7},
            "total_order_value": {"previous": 60000, "pct": -8.3},
        }
    },
}

supplier_insights = ins.get_supplier_insights(None)["insights"]
supplier_by_key = {i["key"]: i["text"] for i in supplier_insights}
assert len(supplier_insights) == 3
assert "Dublin Fresh Foods" in supplier_by_key["worst_supplier"] and "61.0%" in supplier_by_key["worst_supplier"]
assert "up" in supplier_by_key["late_delivery_trend"]
assert "down" in supplier_by_key["order_value_trend"]
print("get_supplier_insights OK:", supplier_by_key)

# ---------------------------------------------------------------------------
# get_storage_insights
# ---------------------------------------------------------------------------
storage_optimizer.get_heatmap = lambda warehouse_id=None: [
    {"warehouse_id": 1, "utilization_pct": 92.0},
    {"warehouse_id": 1, "utilization_pct": 88.0},
    {"warehouse_id": 2, "utilization_pct": 20.0},
]
storage_optimizer.get_top_movers = lambda warehouse_id=None, limit=1: [
    {"product_name": "Greek Yogurt 500g", "avg_daily_units": 42.5}
]
storage_optimizer.get_pending_placement = lambda limit=500: [{"product_id": 1}, {"product_id": 2}]

storage_insights = ins.get_storage_insights(None)["insights"]
storage_by_key = {i["key"]: i["text"] for i in storage_insights}
assert len(storage_insights) == 3
assert "Lombard" in storage_by_key["capacity_watch"] and "capacity" in storage_by_key["capacity_watch"]
assert "Greek Yogurt 500g" in storage_by_key["top_mover"]
assert "2 newly added" in storage_by_key["pending_putaway"]
print("get_storage_insights OK:", storage_by_key)

storage_optimizer.get_pending_placement = lambda limit=500: []
storage_insights_empty = ins.get_storage_insights(None)["insights"]
empty_pending_text = {i["key"]: i["text"] for i in storage_insights_empty}["pending_putaway"]
assert "Nothing is currently waiting" in empty_pending_text
print("get_storage_insights empty pending OK")

# ---------------------------------------------------------------------------
# get_delivery_insights
# ---------------------------------------------------------------------------
delivery_risk_service.get_kpis = lambda warehouse_id=None, date_from=None, date_to=None: {
    "avg_delay_days": 4.2,
    "comparison": {
        "previous_from": "2026-01-01", "previous_to": "2026-01-31",
        "deltas": {"avg_delay_days": {"previous": 3.1, "pct": 35.5}},
    },
}


def fake_risky_orders(limit, warehouse_id=None, date_from=None, date_to=None):
    if date_from == "2026-01-01":  # previous period
        return [
            {"supplier_name": "Dublin Fresh Foods", "delay_days": 8, "risk_level": "HIGH"},
        ]
    return [
        {"supplier_name": "Dublin Fresh Foods", "delay_days": 9, "risk_level": "HIGH"},
        {"supplier_name": "Dublin Fresh Foods", "delay_days": 7, "risk_level": "HIGH"},
        {"supplier_name": "Emerald Wholesale", "delay_days": 4, "risk_level": "MEDIUM"},
    ]


delivery_risk_service.get_risky_orders = fake_risky_orders

delivery_insights = ins.get_delivery_insights(None)["insights"]
delivery_by_key = {i["key"]: i["text"] for i in delivery_insights}
assert len(delivery_insights) == 3
assert "2 purchase order(s)" in delivery_by_key["high_risk_trend"] and "up from 1" in delivery_by_key["high_risk_trend"]
assert "4.2 days" in delivery_by_key["avg_delay_trend"] and "up from 3.1" in delivery_by_key["avg_delay_trend"]
assert "Dublin Fresh Foods" in delivery_by_key["riskiest_supplier"] and "2 orders" in delivery_by_key["riskiest_supplier"]
print("get_delivery_insights OK:", delivery_by_key)

# No late deliveries at all this period - shouldn't raise, should degrade gracefully.
delivery_risk_service.get_kpis = lambda warehouse_id=None, date_from=None, date_to=None: {
    "avg_delay_days": 0, "comparison": None,
}
delivery_risk_service.get_risky_orders = lambda limit, warehouse_id=None, date_from=None, date_to=None: []
no_risk_insights = ins.get_delivery_insights(None)["insights"]
no_risk_by_key = {i["key"]: i["text"] for i in no_risk_insights}
assert "0 purchase order(s)" in no_risk_by_key["high_risk_trend"]
assert "No delayed deliveries" in no_risk_by_key["avg_delay_trend"]
assert "No late deliveries" in no_risk_by_key["riskiest_supplier"]
print("get_delivery_insights empty-data branches OK")

print("ALL insights_service tests passed")
