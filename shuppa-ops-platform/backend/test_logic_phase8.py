"""Logic tests for the Phase 8 features (velocity-aware placement scoring +
Top Movers, sales-correlation co-location proxy, multi-warehouse
rebalancing, dead stock, margin density, alert root-cause hints). Same
style as test_logic.py/test_logic_phase7.py: stub sqlalchemy/fastapi/jose/
passlib so importing app.services.* doesn't need a real DB connection or
those packages installed, then exercise logic with plain asserts and
monkeypatched query_df/query_one (matching test_logic_phase7.py's
get_reorder_suggestions test pattern). Run with `python3 test_logic_phase8.py`.

Not covered here, consistent with this sandbox's existing coverage: the
engine.begin()-based INSERT in stock_service.create_draft_po (same gap as
admin_service's add_supplier/add_product/add_location, which have never had
DB-write-path unit tests in this harness either - there is no real
sqlalchemy engine to exercise here). Its request-validation is covered via
a plain pydantic check below.
"""

import sys
import types

sys.path.insert(0, ".")

# Stub sqlalchemy so importing app.database / app.services.* doesn't require
# a real network connection (same approach as test_logic.py).
fake_sa = types.ModuleType("sqlalchemy")
fake_sa.create_engine = lambda *a, **k: object()
fake_sa.text = lambda s: s
sys.modules["sqlalchemy"] = fake_sa

# app.auth (imported transitively by app.services.audit_service/stock_service
# for the CurrentUser type hint) needs fastapi/jose/passlib, none of which are
# installed in this sandbox (see test_imports.py's identical stubs) - only
# the handful of names app.auth actually references are stubbed.
fake_fastapi = types.ModuleType("fastapi")
fake_fastapi.Depends = lambda x=None: x
fake_fastapi.HTTPException = type(
    "HTTPException",
    (Exception,),
    {
        "__init__": lambda self, status_code=None, detail=None, headers=None: (
            setattr(self, "status_code", status_code),
            setattr(self, "detail", detail),
            setattr(self, "headers", headers),
        )[-1]
    },
)
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

# ---------------------------------------------------------------------------
# storage_optimizer._score_location: velocity-aware 5th factor
# ---------------------------------------------------------------------------
import app.services.storage_optimizer as storage_optimizer  # noqa: E402

good_loc = {
    "current_weight_kg": 5, "max_weight_kg": 20, "current_volume_cm3": 2000, "max_volume_cm3": 20000,
    "shelf_tier": 2, "is_overstock_tier": False,
}

score_plain, reasons_plain = storage_optimizer._score_location(good_loc, volume_cm3=1000, weight_kg=2, fragility="LOW")
print("plain score (no velocity):", score_plain, reasons_plain)
assert not any("dispatch" in r for r in reasons_plain), "non-top-mover call shouldn't mention dispatch proximity at all"

score_close, reasons_close = storage_optimizer._score_location(
    good_loc, volume_cm3=1000, weight_kg=2, fragility="LOW", is_top_mover=True, proximity_score=95.0
)
print("top-mover, close to dispatch:", score_close, reasons_close)
assert any("close to dispatch" in r for r in reasons_close)

score_far, reasons_far = storage_optimizer._score_location(
    good_loc, volume_cm3=1000, weight_kg=2, fragility="LOW", is_top_mover=True, proximity_score=5.0
)
print("top-mover, far from dispatch:", score_far, reasons_far)
assert any("further from dispatch" in r for r in reasons_far)
assert score_close > score_far, "the exact same location/product should score higher when proximity is favorable"

not_mover_score, not_mover_reasons = storage_optimizer._score_location(
    good_loc, volume_cm3=1000, weight_kg=2, fragility="LOW", is_top_mover=False, proximity_score=95.0
)
assert not_mover_score == score_plain, "proximity_score should be ignored entirely when is_top_mover is False"

# ---------------------------------------------------------------------------
# storage_optimizer.suggest_locations: end-to-end with a fast mover
# ---------------------------------------------------------------------------
from app.models.schemas import StorageSuggestRequest  # noqa: E402

candidates_df = pd.DataFrame(
    [
        {
            "location_id": 1, "location_code": 1, "warehouse_id": 1, "storage_type": "AMBIENT", "shelf_tier": 2,
            "sub_location": 1, "is_overstock_tier": False, "utilization_pct": 20.0,
            "max_weight_kg": 20, "current_weight_kg": 2, "max_volume_cm3": 20000, "current_volume_cm3": 2000,
        },
        {
            "location_id": 2, "location_code": 50, "warehouse_id": 1, "storage_type": "AMBIENT", "shelf_tier": 2,
            "sub_location": 1, "is_overstock_tier": False, "utilization_pct": 20.0,
            "max_weight_kg": 20, "current_weight_kg": 2, "max_volume_cm3": 20000, "current_volume_cm3": 2000,
        },
    ]
)
storage_optimizer.query_df = lambda sql, params=None: candidates_df
storage_optimizer.query_one = lambda sql, params=None: (
    {"t": 10.0} if "PERCENTILE_CONT" in sql else {"v": 50.0}
)
storage_optimizer._resolve_product_attrs = lambda req: {
    "length_cm": 10, "width_cm": 10, "height_cm": 10, "volume_cm3": 1000, "weight_kg": 2,
    "fragility": "LOW", "storage_type": "AMBIENT", "product_name": "Fast Mover",
}

req = StorageSuggestRequest(product_id=1, warehouse_id=1, top_n=2)
result = storage_optimizer.suggest_locations(req)
print("suggest_locations result (top mover):", result)
assert result["product"]["is_top_mover"] is True, "avg velocity (50) >= 75th-percentile threshold (10) -> top mover"
# location_code=1 is the lowest code in the pool -> highest proximity score -> should rank first
assert result["suggestions"][0]["location_code"] == 1

# ---------------------------------------------------------------------------
# sales_service._compute_correlated: pure pandas correlation math
# ---------------------------------------------------------------------------
import app.services.sales_service as sales_service  # noqa: E402

pivot = pd.DataFrame(
    {
        100: [10, 12, 8, 15, 9, 11, 14, 7, 13, 10, 16, 6],
        101: [11, 13, 9, 16, 10, 12, 15, 8, 14, 11, 17, 7],  # tracks 100 closely
        102: [5, 4, 6, 3, 5, 4, 3, 6, 4, 5, 3, 6],  # inversely related
        103: [3, 9, 1, 7, 12, 2, 8, 5, 6, 4, 10, 1],  # unrelated noise
    }
)
pairs = sales_service._compute_correlated(pivot, 100, limit=5)
print("correlated pairs:", pairs)
pair_ids = [pid for pid, _ in pairs]
assert 101 in pair_ids, "product 101 tracks product 100's daily pattern almost exactly - should be flagged"
assert 100 not in pair_ids, "a product should never correlate against itself"
assert pairs[0][0] == 101, "the strongest correlation should be first"

too_short_pivot = pd.DataFrame({100: [1, 2, 3], 101: [1, 2, 3]})
assert sales_service._compute_correlated(too_short_pivot, 100, limit=5) == [], "fewer than 10 days -> not enough history, no results"

# ---------------------------------------------------------------------------
# stock_service.get_rebalancing_suggestions
# ---------------------------------------------------------------------------
import app.services.stock_service as stock_service  # noqa: E402

stock_service.query_one = lambda sql, params=None: {"d": "2026-09-01"}
rebalance_df = pd.DataFrame(
    [
        {"product_id": 1, "product_name": "Widget", "warehouse_id": 1, "stock_status": "CRITICAL", "stock_on_hand": 5, "reorder_point": 20},
        {"product_id": 1, "product_name": "Widget", "warehouse_id": 2, "stock_status": "OVERSTOCK", "stock_on_hand": 100, "reorder_point": 20},
        {"product_id": 1, "product_name": "Widget", "warehouse_id": 3, "stock_status": "HEALTHY", "stock_on_hand": 25, "reorder_point": 20},
        {"product_id": 2, "product_name": "Gadget", "warehouse_id": 1, "stock_status": "HEALTHY", "stock_on_hand": 30, "reorder_point": 10},
        {"product_id": 2, "product_name": "Gadget", "warehouse_id": 2, "stock_status": "HEALTHY", "stock_on_hand": 12, "reorder_point": 10},
    ]
)
stock_service.query_df = lambda sql, params=None: rebalance_df
rebalancing = stock_service.get_rebalancing_suggestions(limit=50)
print("rebalancing suggestions:", rebalancing)
assert len(rebalancing) == 1, "only product 1 has both a shortfall and a surplus elsewhere"
r = rebalancing[0]
assert r["short_warehouse_id"] == 1 and r["surplus_warehouse_id"] == 2, "warehouse 2's OVERSTOCK should beat warehouse 3's merely-healthy stock"
assert r["needed_units"] == 15, "reorder_point 20 - stock_on_hand 5 = 15"
assert r["suggested_transfer_qty"] == 15, "capped at what's actually needed, even though warehouse 2 could spare more"

scoped = stock_service.get_rebalancing_suggestions(limit=50, warehouse_id=1)
assert len(scoped) == 1
scoped_none = stock_service.get_rebalancing_suggestions(limit=50, warehouse_id=2)
assert scoped_none == [], "warehouse_id filter scopes to shortfalls IN that warehouse, not surpluses"

# ---------------------------------------------------------------------------
# stock_service.get_dead_stock
# ---------------------------------------------------------------------------
stock_service.settings_service.get_setting_float = lambda key, default: 60.0
dead_df = pd.DataFrame(
    [
        {"product_id": 1, "product_name": "Stale Widget", "category": "Misc", "warehouse_id": 1, "stock_on_hand": 40, "stock_value": 800.0, "units_sold_recent": 0},
        {"product_id": 2, "product_name": "Slow Gadget", "category": "Misc", "warehouse_id": 1, "stock_on_hand": 10, "stock_value": 200.0, "units_sold_recent": 0},
    ]
)
stock_service.query_df = lambda sql, params=None: dead_df
dead = stock_service.get_dead_stock()
print("dead stock:", dead)
assert dead["total_value_tied_up"] == 1000.0
assert dead["items"][0]["product_name"] == "Stale Widget", "sorted by stock value tied up, descending"
assert dead["dead_stock_days_threshold"] == 60

stock_service.query_df = lambda sql, params=None: pd.DataFrame()
empty_dead = stock_service.get_dead_stock()
assert empty_dead == {"items": [], "total_value_tied_up": 0, "dead_stock_days_threshold": 60}

# ---------------------------------------------------------------------------
# stock_service.get_margin_density
# ---------------------------------------------------------------------------
margin_df = pd.DataFrame(
    [
        {"product_id": 1, "product_name": "Bulky Low-Margin", "category": "Snacks", "gross_profit": 1.0, "volume_cm3": 5000, "length_cm": 50, "width_cm": 10, "height_cm": 10},
        {"product_id": 2, "product_name": "Compact High-Margin", "category": "Snacks", "gross_profit": 5.0, "volume_cm3": 100, "length_cm": 5, "width_cm": 5, "height_cm": 4},
    ]
)
stock_service.query_df = lambda sql, params=None: margin_df
density = stock_service.get_margin_density(limit=10)
print("margin density:", density)
assert density[0]["product_name"] == "Bulky Low-Margin", "worst space-efficiency (lowest profit/cm3) should sort first"
assert density[0]["margin_per_cm3"] < density[1]["margin_per_cm3"]

# ---------------------------------------------------------------------------
# DraftPurchaseOrderRequest: plain pydantic validation, no DB involved
# ---------------------------------------------------------------------------
from app.models.schemas import DraftPurchaseOrderRequest  # noqa: E402

draft_req = DraftPurchaseOrderRequest(product_id=1, warehouse_id=2, quantity=25, supplier_id=None, note="test")
assert draft_req.quantity == 25 and draft_req.warehouse_id == 2

try:
    DraftPurchaseOrderRequest(product_id=1, warehouse_id=2, quantity=0)
    raise AssertionError("quantity must be > 0 - this should have raised a validation error")
except Exception as e:
    assert "ValidationError" in type(e).__name__ or "validation" in str(e).lower()

# ---------------------------------------------------------------------------
# alerts_service: rule-based root-cause hints
# ---------------------------------------------------------------------------
import app.services.alerts_service as alerts_service  # noqa: E402

alerts_service.supplier_service.get_performance = lambda warehouse_id=None: [
    {"supplier_name": "Acme", "on_time_delivery_pct": 60.0},
    {"supplier_name": "Beta", "on_time_delivery_pct": 70.0},
]
alerts_service.settings_service.get_setting_float = lambda key, default=None: (
    15.0 if key == "supplier_late_pct_medium_threshold" else default
)
hint = alerts_service._hint_for_stock_alert(warehouse_id=1)
print("stock alert hint:", hint)
assert hint is not None and "65" in hint, "average on-time (65%) is below the 85% bar (100 - 15 threshold) -> should hint"

alerts_service.supplier_service.get_performance = lambda warehouse_id=None: [
    {"supplier_name": "Acme", "on_time_delivery_pct": 98.0},
]
assert alerts_service._hint_for_stock_alert(warehouse_id=1) is None, "healthy on-time rate -> no hint"

high_delay = [
    {"supplier_name": "Acme", "delay_days": 10},
    {"supplier_name": "Acme", "delay_days": 8},
    {"supplier_name": "Beta", "delay_days": 9},
]
delay_hint = alerts_service._hint_for_delivery_alert(high_delay)
print("delivery alert hint:", delay_hint)
assert delay_hint is not None and "Acme" in delay_hint and "2" in delay_hint

no_pattern_delay = [
    {"supplier_name": "Acme", "delay_days": 10},
    {"supplier_name": "Beta", "delay_days": 9},
    {"supplier_name": "Gamma", "delay_days": 8},
]
assert alerts_service._hint_for_delivery_alert(no_pattern_delay) is None, "no single supplier dominates -> no hint"

alerts_service.stock_service.get_dead_stock = lambda warehouse_id=None: {"items": [{"product_id": 1}, {"product_id": 2}]}
overstock_hint = alerts_service._hint_for_overstock_alert(warehouse_id=1)
print("overstock alert hint:", overstock_hint)
assert overstock_hint is not None and "2" in overstock_hint

alerts_service.stock_service.get_dead_stock = lambda warehouse_id=None: {"items": []}
assert alerts_service._hint_for_overstock_alert(warehouse_id=1) is None

print("\nALL PHASE 8 LOGIC TESTS PASSED")
