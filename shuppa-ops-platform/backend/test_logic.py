import sys
import types

import numpy as np
import pandas as pd

sys.path.insert(0, ".")

# Stub sqlalchemy + the DB engine so importing app.database / app.services.*
# doesn't require a real network connection.
fake_sa = types.ModuleType("sqlalchemy")
fake_sa.create_engine = lambda *a, **k: object()
fake_sa.text = lambda s: s
sys.modules["sqlalchemy"] = fake_sa

from app.models.schemas import StorageSuggestRequest, DeliveryRiskRequest
import app.services.storage_optimizer as so
import app.services.delivery_risk_service as drs

# ---------------------------------------------------------------------------
# storage_optimizer._score_location
# ---------------------------------------------------------------------------
loc_good = {
    "current_weight_kg": 50, "max_weight_kg": 200,
    "current_volume_cm3": 40000, "max_volume_cm3": 200000,
    "shelf_tier": 3, "is_overstock_tier": False,
}
score, reasons = so._score_location(loc_good, volume_cm3=15000, weight_kg=5, fragility="HIGH")
print("good location score:", score, reasons)
assert 0 <= score <= 100

loc_overstock = dict(loc_good, is_overstock_tier=True, shelf_tier=0)
score2, reasons2 = so._score_location(loc_overstock, volume_cm3=15000, weight_kg=5, fragility="HIGH")
print("overstock-tier fragile score:", score2, reasons2)
assert score2 < score, "overstock tier + fragile should score worse than active tier"

loc_full = dict(loc_good, current_weight_kg=195, current_volume_cm3=199000)
score3, _ = so._score_location(loc_full, volume_cm3=15000, weight_kg=5, fragility="LOW")
print("nearly-full location score:", score3)
assert score3 < score

# ---------------------------------------------------------------------------
# storage_optimizer.suggest_locations (mock query_df/query_one)
# ---------------------------------------------------------------------------
mock_locations = pd.DataFrame(
    [
        {"location_id": 1, "location_code": 3, "warehouse_id": 1, "storage_type": "AMBIENT",
         "shelf_tier": 3, "sub_location": 1, "is_overstock_tier": False,
         "max_weight_kg": 200, "max_volume_cm3": 200000, "current_weight_kg": 20, "current_volume_cm3": 20000,
         "utilization_pct": 10.0},
        {"location_id": 2, "location_code": 4, "warehouse_id": 1, "storage_type": "AMBIENT",
         "shelf_tier": 0, "sub_location": 1, "is_overstock_tier": True,
         "max_weight_kg": 200, "max_volume_cm3": 200000, "current_weight_kg": 180, "current_volume_cm3": 190000,
         "utilization_pct": 95.0},
        {"location_id": 3, "location_code": 5, "warehouse_id": 1, "storage_type": "AMBIENT",
         "shelf_tier": 1, "sub_location": 1, "is_overstock_tier": False,
         "max_weight_kg": 800, "max_volume_cm3": 600000, "current_weight_kg": 100, "current_volume_cm3": 100000,
         "utilization_pct": 16.0},
    ]
)
so.query_df = lambda sql, params=None: mock_locations
so.query_one = lambda sql, params=None: {
    "length_cm": 10, "width_cm": 10, "height_cm": 10, "volume_cm3": 1000, "weight_kg": 2,
    "fragility": "LOW", "storage_type": "AMBIENT", "product_name": "Test Product",
}

# warehouse_id=1 explicitly: exercises the single-warehouse "top N overall"
# ranking path, unaffected by the Session 10 multi-warehouse change below.
req = StorageSuggestRequest(product_id=1, warehouse_id=1, top_n=2)
result = so.suggest_locations(req)
print("suggest_locations result:", result)
assert len(result["suggestions"]) == 2
assert result["suggestions"][0]["fit_score"] >= result["suggestions"][1]["fit_score"]
assert result["suggestions"][0]["location_id"] == 1, "the roomy active-tier location should win over the overstock one"

# ---------------------------------------------------------------------------
# storage_optimizer.suggest_locations - Session 10 putaway grid:
# warehouse_id=None must return up to top_n candidates PER warehouse (not
# top_n overall regardless of spread, and not just a single best pick per
# warehouse either) - warehouse 1 (3 compatible candidates) should
# contribute its own top 2, while warehouse 2 (only 1 compatible candidate)
# contributes just the 1 it has, without being padded or dropped.
# ---------------------------------------------------------------------------
mock_locations_multi_wh = pd.concat(
    [
        mock_locations,
        pd.DataFrame(
            [
                {"location_id": 4, "location_code": 3, "warehouse_id": 2, "storage_type": "AMBIENT",
                 "shelf_tier": 0, "sub_location": 1, "is_overstock_tier": True,
                 "max_weight_kg": 200, "max_volume_cm3": 200000, "current_weight_kg": 199, "current_volume_cm3": 199500,
                 "utilization_pct": 99.5},
            ]
        ),
    ],
    ignore_index=True,
)
so.query_df = lambda sql, params=None: mock_locations_multi_wh

req_multi = StorageSuggestRequest(product_id=1, top_n=2)  # top_n=2 PER warehouse for this path
result_multi = so.suggest_locations(req_multi)
print("suggest_locations result (putaway grid, top_n per warehouse):", result_multi)
by_warehouse: dict[int, list] = {}
for s in result_multi["suggestions"]:
    by_warehouse.setdefault(s["warehouse_id"], []).append(s)
assert set(by_warehouse) == {1, 2}, "every warehouse must be represented"
assert len(by_warehouse[1]) == 2, "warehouse 1 has 3 candidates and top_n=2 -> exactly 2 back"
assert len(by_warehouse[2]) == 1, "warehouse 2 only has 1 candidate -> 1 back, not padded to 2 or dropped"
assert {s["location_id"] for s in by_warehouse[1]} == {1, 3}, "warehouse 1's best 2 (roomy, active-tier) - not the overstock-tier one (location_id=2)"
assert by_warehouse[2][0]["location_id"] == 4

# storage_type default: no explicit storage_type -> AMBIENT (there's no
# separate bulk/cage location type in the real warehouse layout)
req2 = StorageSuggestRequest(length_cm=60, width_cm=60, height_cm=60, weight_kg=10, top_n=1)
attrs = so._resolve_product_attrs(req2)
print("default storage_type for a manually-specified item:", attrs["storage_type"])
assert attrs["storage_type"] == "AMBIENT"

# ---------------------------------------------------------------------------
# delivery_risk_service.predict (mock load_model + query_one)
# ---------------------------------------------------------------------------
fake_model = {
    "feature_names": ["supplier_on_time_rate", "order_quantity", "lead_time_days", "warehouse_utilization_pct", "order_cost"],
    "means": [0.8, 260.0, 9.5, 50.0, 29000.0],
    "stds": [0.017, 138.0, 4.6, 0.05, 24000.0],
    "intercept": -1.37,
    "coefficients": [-0.11, 0.005, -0.014, -0.017, 0.034],
    "train_accuracy": 0.797, "train_auc": 0.53, "trained_at": "x", "n_training_rows": 20000,
    "supplier_on_time_rate_overall": 0.8, "warehouse_utilization_pct_overall": 50.0,
    "order_quantity_mean": 260.0, "lead_time_days_mean": 9.5,
    "risk_thresholds": {"low_max": 0.20, "medium_max": 0.22},
}
drs.load_model = lambda: fake_model

call_log = []


def fake_query_one(sql, params=None):
    call_log.append(sql)
    if "dim_suppliers" in sql:
        return {"on_time_rate": 0.6, "supplier_name": "Test Supplier"}
    if "fact_inventory_daily" in sql:
        return {"utilization_pct": 92.0, "warehouse_name": "Test Warehouse"}
    if "unit_cost" in sql and "product_id" in sql:
        return {"unit_cost": 10.0, "product_name": "Test Product"}
    if "AVG(unit_cost)" in sql:
        return {"v": 15.0}
    return {}


drs.query_one = fake_query_one

req3 = DeliveryRiskRequest(supplier_id=1, warehouse_id=1, order_quantity=500, lead_time_days=3)
pred = drs.predict(req3)
print("prediction (bad supplier, high util, big order, short lead):", pred)
assert pred["risk_level"] in ("LOW", "MEDIUM", "HIGH")
assert 0 <= pred["risk_probability"] <= 1
assert pred["explanation"][0]["is_unfavorable"] is True  # supplier reliability worse than average

print("\nALL LOGIC TESTS PASSED")

# ---------------------------------------------------------------------------
# storage_optimizer.mark_placed_bulk - validation branches only (the actual
# transactional INSERT/UPDATE SQL was proven separately against a real,
# ephemeral local Postgres instance - see the Session 10 build notes; a
# mocked engine.begin() here would only prove the mock was called
# correctly, not that the SQL itself is right, which the live-Postgres
# smoke test already covers more convincingly).
# ---------------------------------------------------------------------------
try:
    so.mark_placed_bulk(1, [])
    raise AssertionError("empty location_ids should have raised ValueError")
except ValueError as e:
    print("mark_placed_bulk empty list ->", e)

so.query_records = lambda sql, params=None: [
    {"location_id": 1, "warehouse_id": 1},
    {"location_id": 4, "warehouse_id": 2},
]
try:
    so.mark_placed_bulk(1, [1, 4, 999])
    raise AssertionError("a not-found location_id should have raised ValueError")
except ValueError as e:
    print("mark_placed_bulk missing location ->", e)
    assert "999" in str(e)

so.query_records = lambda sql, params=None: [
    {"location_id": 1, "warehouse_id": 1},
    {"location_id": 2, "warehouse_id": 1},  # same warehouse as location_id=1 - not one-per-warehouse
]
try:
    so.mark_placed_bulk(1, [1, 2])
    raise AssertionError("two locations in the same warehouse should have raised ValueError")
except ValueError as e:
    print("mark_placed_bulk duplicate warehouse ->", e)
    assert "distinct warehouses" in str(e)

print("mark_placed_bulk validation checks passed")
