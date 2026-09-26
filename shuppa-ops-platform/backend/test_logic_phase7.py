"""Logic tests for the Phase 7 features (settings-preview override, audit log
filtering, login lockout math helpers, rate limiting, reorder suggestions,
category-scoped forecast). Same style as test_logic.py: stub sqlalchemy so
importing app.services.* doesn't need a real DB connection, then exercise
pure logic with plain asserts. Run with `python3 test_logic_phase7.py`.
"""

import asyncio
import sys
import types

sys.path.insert(0, ".")

# Stub sqlalchemy so importing app.database / app.services.* doesn't require
# a real network connection (same approach as test_logic.py).
fake_sa = types.ModuleType("sqlalchemy")
fake_sa.create_engine = lambda *a, **k: object()
fake_sa.text = lambda s: s
sys.modules["sqlalchemy"] = fake_sa

# app.auth (imported transitively by app.services.audit_service/admin_service
# for the CurrentUser type hint) needs fastapi/jose/passlib, none of which are
# installed in this sandbox (see test_imports.py's identical stubs) - only
# the handful of names app.auth actually references are stubbed.
fake_fastapi = types.ModuleType("fastapi")
fake_fastapi.Depends = lambda x=None: x
fake_fastapi.HTTPException = type("HTTPException", (Exception,), {
    "__init__": lambda self, status_code=None, detail=None, headers=None: (
        setattr(self, "status_code", status_code), setattr(self, "detail", detail), setattr(self, "headers", headers)
    )[-1]
})
# Only used as a type annotation on app.auth.get_current_user - never
# instantiated here, so a bare placeholder class is enough to satisfy
# `from fastapi import Request`.
fake_fastapi.Request = type("Request", (), {})


class _FakeStatus:
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403


fake_fastapi.status = _FakeStatus
sys.modules["fastapi"] = fake_fastapi

fake_fastapi_security = types.ModuleType("fastapi.security")
fake_fastapi_security.OAuth2PasswordBearer = lambda *a, **k: (lambda *a2, **k2: None)
sys.modules["fastapi.security"] = fake_fastapi_security

fake_jose = types.ModuleType("jose")
fake_jose.JWTError = type("JWTError", (Exception,), {})
fake_jose.jwt = types.SimpleNamespace(
    encode=lambda payload, key, algorithm=None: "faketoken",
    decode=lambda token, key, algorithms=None: {"sub": "admin", "user_id": 1, "role": "ADMIN", "warehouse_id": None},
)
sys.modules["jose"] = fake_jose

fake_passlib = types.ModuleType("passlib")
fake_passlib_context = types.ModuleType("passlib.context")


class _FakeCryptContext:
    def __init__(self, *a, **k):
        pass

    def hash(self, password):
        return f"fakehash${password}"

    def verify(self, plain, hashed):
        return hashed == f"fakehash${plain}"


fake_passlib_context.CryptContext = _FakeCryptContext
sys.modules["passlib"] = fake_passlib
sys.modules["passlib.context"] = fake_passlib_context

import pandas as pd  # noqa: E402

from app.services.db_utils import compute_deltas, previous_period_window  # noqa: E402

# ---------------------------------------------------------------------------
# db_utils.compute_deltas
# ---------------------------------------------------------------------------
deltas = compute_deltas(
    {"total_revenue": 150.0, "stockout_pct": 2.0},
    {"total_revenue": 100.0, "stockout_pct": 0.0},
    ["total_revenue", "stockout_pct", "missing_key"],
)
print("compute_deltas:", deltas)
assert deltas["total_revenue"]["absolute"] == 50.0
assert deltas["total_revenue"]["pct"] == 50.0
assert deltas["stockout_pct"]["pct"] is None, "division by a zero previous value should give pct=None, not raise"
assert deltas["missing_key"] is None, "a key present in neither dict should be omitted (None), not KeyError"

# ---------------------------------------------------------------------------
# db_utils.previous_period_window
# ---------------------------------------------------------------------------
prev_from, prev_to = previous_period_window("2026-09-01", "2026-09-10")
print("previous_period_window (Between mode):", prev_from, prev_to)
assert prev_from == "2026-08-22" and prev_to == "2026-08-31", "previous window should be the same 10-day length, immediately before"

prev_from2, prev_to2 = previous_period_window(None, None)
assert prev_from2 is None and prev_to2 is None, "no explicit range -> caller anchors to the data's own MAX(date) instead"

# ---------------------------------------------------------------------------
# settings_service.override (contextvar-scoped threshold overrides)
# ---------------------------------------------------------------------------
import app.services.settings_service as settings_service  # noqa: E402

settings_service.query_records = lambda sql, params=None: [{"setting_value": "5"}]
assert settings_service.get_setting("stockout_pct_threshold", "0") == "5", "without an override, reads the real stored value"

with settings_service.override({"stockout_pct_threshold": 25}):
    assert settings_service.get_setting("stockout_pct_threshold", "0") == "25", "inside the override block, the hypothetical value wins"
    assert settings_service.get_setting("some_other_key", "42") == "5", "a key not present in the override falls back to the real stored value"

# override must not leak once the `with` block exits
assert settings_service.get_setting("stockout_pct_threshold", "0") == "5", "override must not leak outside its `with` block"


async def _concurrency_check():
    """Overrides are per-request (contextvar), not global - two concurrent
    'requests' with different override values must not see each other's
    values. This is the whole reason override() uses a ContextVar instead of
    a plain module-level dict."""
    results = {}

    async def request_a():
        with settings_service.override({"stockout_pct_threshold": 10}):
            await asyncio.sleep(0.01)
            results["a"] = settings_service.get_setting("stockout_pct_threshold", "0")

    async def request_b():
        with settings_service.override({"stockout_pct_threshold": 90}):
            await asyncio.sleep(0.01)
            results["b"] = settings_service.get_setting("stockout_pct_threshold", "0")

    await asyncio.gather(request_a(), request_b())
    return results


concurrency_results = asyncio.run(_concurrency_check())
print("concurrent override isolation:", concurrency_results)
assert concurrency_results == {"a": "10", "b": "90"}, "concurrent overrides must not leak into each other"

# ---------------------------------------------------------------------------
# alerts_service.get_all_alerts graceful degradation
# ---------------------------------------------------------------------------
import app.services.alerts_service as alerts_service  # noqa: E402
import app.services.stock_service as stock_service  # noqa: E402
import app.services.supplier_service as supplier_service  # noqa: E402
import app.services.delivery_risk_service as delivery_risk_service  # noqa: E402
import app.services.storage_optimizer as storage_optimizer  # noqa: E402

stock_service.get_alerts = lambda warehouse_id=None: [
    {"level": "critical", "title": "Stockout Warning", "detail": "x", "count": 1}
]


def _boom(*a, **k):
    raise RuntimeError("supplier table temporarily unavailable")


supplier_service.get_performance = _boom
delivery_risk_service.get_risky_orders = _boom
delivery_risk_service.ModelNotTrainedError = type("ModelNotTrainedError", (Exception,), {})
storage_optimizer.get_overstocked = _boom
storage_optimizer.get_pending_placement = _boom

alerts = alerts_service.get_all_alerts(warehouse_id=1)
print("alerts with 3 of 4 signals broken:", alerts)
assert len(alerts) == 1, "the alerts feed should degrade gracefully - one broken signal must not take down the others"
assert alerts[0]["title"] == "Stockout Warning"

# ---------------------------------------------------------------------------
# alerts_service.preview_settings_impact (settings-preview endpoint's logic)
# ---------------------------------------------------------------------------
# Simulate the currently-stored threshold as a high value (50) that doesn't
# trigger an alert, then propose a much lower one (1) that does.
settings_service.query_records = lambda sql, params=None: [{"setting_value": "50"}]


def _alerts_by_threshold(warehouse_id=None):
    threshold = float(settings_service.get_setting("stockout_pct_threshold", "5"))
    # Simulate: a lower threshold means more alerts fire.
    return [{"level": "critical"}] if threshold < 20 else []


alerts_service.get_all_alerts = _alerts_by_threshold
preview = alerts_service.preview_settings_impact({"stockout_pct_threshold": 1}, warehouse_id=1)
print("preview_settings_impact:", preview)
assert preview["current"]["total"] == 0, "current stored threshold (50) shouldn't be firing"
assert preview["proposed"]["total"] == 1, "the proposed (lower) threshold should fire more alerts"

# ---------------------------------------------------------------------------
# sales_service.get_forecast: linear-fit math + category passthrough
# ---------------------------------------------------------------------------
import app.services.sales_service as sales_service  # noqa: E402

flat_history = [{"bucket": f"2026-08-{d:02d}", "revenue": 100.0, "units_sold": 10.0} for d in range(1, 11)]
rising_history = [{"bucket": f"2026-08-{d:02d}", "revenue": 100.0 + d * 10, "units_sold": 10.0 + d} for d in range(1, 11)]

sales_service.get_trend = lambda *a, **k: flat_history
flat_result = sales_service.get_forecast(forecast_days=5, history_days=10)
print("flat trend forecast:", flat_result["trend_direction"], flat_result["forecast"][0])
# A perfectly flat series' least-squares slope can land as a tiny non-zero
# float (rounding noise, not a real trend), so check the projected value
# stays essentially unchanged rather than asserting trend_direction == "flat".
assert abs(flat_result["forecast"][0]["revenue"] - 100.0) < 0.5, "a flat history should project forward roughly flat"

sales_service.get_trend = lambda *a, **k: rising_history
rising_result = sales_service.get_forecast(forecast_days=5, history_days=10, category="Snacks")
print("rising trend forecast (Snacks):", rising_result["trend_direction"], rising_result["category"])
assert rising_result["trend_direction"] == "up"
assert rising_result["category"] == "Snacks"
assert rising_result["forecast"][-1]["revenue"] > rising_result["history"][-1]["revenue"]

short_history = [{"bucket": "2026-08-01", "revenue": 100.0, "units_sold": 10.0}]
sales_service.get_trend = lambda *a, **k: short_history
short_result = sales_service.get_forecast(forecast_days=5, history_days=10)
assert short_result["forecast"] == [] and "Not enough history" in short_result["note"]

# ---------------------------------------------------------------------------
# stock_service.get_reorder_suggestions: velocity target, fallback estimate,
# and best-historical-supplier tie-break
# ---------------------------------------------------------------------------
stock_service._latest_date = lambda *a, **k: "2026-09-01"
stock_service.settings_service.get_setting_float = lambda key, default: 30.0

reorder_stock_df = pd.DataFrame(
    [
        {
            "product_id": 1, "product_name": "Widget", "warehouse_id": 1, "stock_status": "CRITICAL",
            "stock_on_hand": 5, "reorder_point": 20, "avg_daily_units": 2.0,
        },
        {
            "product_id": 2, "product_name": "Gadget", "warehouse_id": 1, "stock_status": "LOW",
            "stock_on_hand": 3, "reorder_point": 10, "avg_daily_units": 0.0,
        },
    ]
)
reorder_supplier_df = pd.DataFrame(
    [
        {"product_id": 1, "supplier_id": 10, "supplier_name": "Acme", "orders_completed": 5, "on_time_count": 4},
        {"product_id": 1, "supplier_id": 11, "supplier_name": "Beta", "orders_completed": 3, "on_time_count": 3},
    ]
)


def fake_query_df(sql, params=None):
    return reorder_stock_df if "recent_sales" in sql else reorder_supplier_df


stock_service.query_df = fake_query_df
suggestions = stock_service.get_reorder_suggestions(limit=50, warehouse_id=1)
by_product = {s["product_id"]: s for s in suggestions}
print("reorder suggestions:", suggestions)

assert by_product[1]["suggested_reorder_qty"] == 55, "velocity target: 2.0/day * 30 days - 5 on hand = 55"
assert by_product[1]["is_estimate"] is False
assert by_product[1]["best_supplier"]["supplier_name"] == "Beta", "Beta (100% on-time) should beat Acme (80% on-time)"

assert by_product[2]["is_estimate"] is True, "no sales velocity -> falls back to the reorder-point estimate, flagged as such"
assert by_product[2]["suggested_reorder_qty"] == 17, "fallback: 2x reorder point (20) - 3 on hand = 17"
assert by_product[2]["best_supplier"] is None
assert "No prior purchase-order history" in by_product[2]["best_supplier_note"]

# ---------------------------------------------------------------------------
# audit_service.get_audit_log: dynamic WHERE clause construction
# ---------------------------------------------------------------------------
import app.services.audit_service as audit_service  # noqa: E402

captured_audit_sql = []
audit_service.query_records = lambda sql, params=None: captured_audit_sql.append((sql, params)) or []

audit_service.get_audit_log(limit=50)
audit_service.get_audit_log(limit=50, username="admin", action="add_product", date_from="2026-09-01", date_to="2026-09-10")

no_filter_sql, no_filter_params = captured_audit_sql[0]
assert "WHERE" not in no_filter_sql, "no filters supplied -> no WHERE clause at all"

filtered_sql, filtered_params = captured_audit_sql[1]
print("filtered audit-log SQL:", filtered_sql.strip())
assert "username = :username" in filtered_sql
assert "action = :action" in filtered_sql
assert "created_at >= :date_from" in filtered_sql
assert "created_at < (:date_to::date + INTERVAL '1 day')" in filtered_sql, "date_to should be inclusive of the whole day"
assert filtered_params == {
    "limit": 50, "username": "admin", "action": "add_product",
    "date_from": "2026-09-01", "date_to": "2026-09-10",
}

# ---------------------------------------------------------------------------
# rate_limit.RateLimitMiddleware: fixed-window per-IP limiting
# ---------------------------------------------------------------------------
from app.rate_limit import RateLimitMiddleware  # noqa: E402


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeURL:
    def __init__(self, path):
        self.path = path


class _FakeRequest:
    def __init__(self, host="1.2.3.4", path="/stock/summary"):
        self.client = _FakeClient(host)
        self.url = _FakeURL(path)


class _FakeResponse:
    status_code = 200


async def _rate_limit_checks():
    mw = RateLimitMiddleware(app=None, requests=3, window_seconds=60)

    async def call_next(req):
        return _FakeResponse()

    statuses = [
        (await mw.dispatch(_FakeRequest(), call_next)).status_code for _ in range(5)
    ]

    # A different client IP gets its own independent bucket.
    other_client_status = (await mw.dispatch(_FakeRequest(host="9.9.9.9"), call_next)).status_code

    # /health is exempt from limiting even after the bucket is exhausted.
    health_status = (await mw.dispatch(_FakeRequest(path="/health"), call_next)).status_code

    return statuses, other_client_status, health_status


statuses, other_client_status, health_status = asyncio.run(_rate_limit_checks())
print("rate limit statuses:", statuses, "other client:", other_client_status, "health:", health_status)
assert statuses == [200, 200, 200, 429, 429], "first `requests` calls pass, the rest 429 until the window rolls over"
assert other_client_status == 200, "a different client IP must have its own independent bucket"
assert health_status == 200, "/health must be exempt from rate limiting even when the caller's bucket is exhausted"

print("\nALL PHASE 7 LOGIC TESTS PASSED")
