"""Stock Optimizer / Storage Optimization & Space Planner service.

Implements the "Smart Placement Advisor": given a product's physical
attributes (or an existing product_id), score every compatible storage
location and return the best-fit candidates. Reads location capacity/
occupancy through v_storage_location_occupancy (a view created in
app/migrations.py) rather than dim_storage_locations directly - see that
view's migration comment and backfill_scored_placements()'s docstring below
for why: occupancy is computed live from dim_product_placements so it can
never disagree with what the heatmap/location-detail popup shows.

This is a transparent, weighted rules engine (not a black-box ML model) so
every suggestion can be explained to the warehouse operator - which mirrors
what the Stock Optimizer mockup shows (a fit score + short reasoning per
suggested location).
"""

from typing import Optional

import pandas as pd
from sqlalchemy import text

from app.database import engine
from app.models.schemas import StorageSuggestRequest
from app.services.db_utils import query_df, query_one, query_records, warehouse_filter_clause


def get_tree(warehouse_id: Optional[int] = None) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id)
    return query_records(
        f"""
        SELECT
            storage_type,
            COUNT(*) AS location_count,
            COUNT(DISTINCT location_code) AS distinct_codes,
            ROUND(AVG(utilization_pct)::numeric, 1) AS avg_utilization_pct,
            ARRAY_AGG(DISTINCT location_code ORDER BY location_code) AS location_codes
        FROM v_storage_location_occupancy
        WHERE 1=1 {clause}
        GROUP BY storage_type
        ORDER BY storage_type
        """,
        {"warehouse_id": warehouse_id},
    )


def get_products(search: Optional[str] = None, limit: int = 50) -> list[dict]:
    where = "WHERE p.product_name ILIKE :search" if search else ""
    return query_records(
        f"""
        SELECT
            p.product_id, p.product_name, p.category,
            d.length_cm, d.width_cm, d.height_cm, d.volume_cm3, d.weight_kg,
            d.storage_type, d.fragility, d.stackable
        FROM dim_product_dimensions d
        JOIN dim_products p ON p.product_id = d.product_id
        {where}
        ORDER BY p.product_id
        LIMIT :limit
        """,
        {"search": f"%{search}%" if search else None, "limit": limit},
    )


def get_heatmap(warehouse_id: Optional[int] = None) -> list[dict]:
    # Reads v_storage_location_occupancy (app/migrations.py), not
    # dim_storage_locations directly - utilization_pct there is computed live
    # from real dim_product_placements rows, not the base table's synthetic
    # seed-time value, so a cell's color always matches what its own
    # click-to-inspect popup shows. See that view's migration comment.
    clause = warehouse_filter_clause(warehouse_id)
    return query_records(
        f"""
        SELECT location_id, location_code, warehouse_id, storage_type, shelf_tier,
               sub_location, is_overstock_tier, utilization_pct
        FROM v_storage_location_occupancy
        WHERE 1=1 {clause}
        ORDER BY location_code, shelf_tier, sub_location
        """,
        {"warehouse_id": warehouse_id},
    )


def get_overstocked(threshold: float = 90, warehouse_id: Optional[int] = None) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id)
    return query_records(
        f"""
        SELECT location_id, location_code, warehouse_id, storage_type, shelf_tier, utilization_pct
        FROM v_storage_location_occupancy
        WHERE utilization_pct > :threshold {clause}
        ORDER BY utilization_pct DESC
        """,
        {"threshold": threshold, "warehouse_id": warehouse_id},
    )


def get_underutilized(threshold: float = 30, warehouse_id: Optional[int] = None) -> list[dict]:
    clause = warehouse_filter_clause(warehouse_id)
    return query_records(
        f"""
        SELECT location_id, location_code, warehouse_id, storage_type, shelf_tier, utilization_pct
        FROM v_storage_location_occupancy
        WHERE utilization_pct < :threshold {clause}
        ORDER BY utilization_pct ASC
        """,
        {"threshold": threshold, "warehouse_id": warehouse_id},
    )


def get_top_movers(warehouse_id: Optional[int] = None, limit: int = 20) -> list[dict]:
    """Highest sales-velocity products over the trailing 30 days - a ranking
    of demand only, used to flag which items would most benefit from being
    checked against the Smart Placement Advisor with velocity-aware scoring
    (see suggest_locations below). This is NOT "these products are
    currently misplaced" - the app has no product-to-slot assignment table,
    so it can't know where a product is actually sitting today, only what
    the ideal placement would score out as if you ran the advisor now."""
    clause = warehouse_filter_clause(warehouse_id)
    return query_records(
        f"""
        SELECT s.product_id, p.product_name, p.category,
               ROUND(AVG(s.units_sold)::numeric, 2) AS avg_daily_units,
               SUM(s.units_sold) AS total_units_30d
        FROM fact_sales_daily s
        JOIN dim_products p ON p.product_id = s.product_id
        WHERE s.date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days' {clause}
        GROUP BY s.product_id, p.product_name, p.category
        ORDER BY avg_daily_units DESC
        LIMIT :limit
        """,
        {"warehouse_id": warehouse_id, "limit": limit},
    )


def _product_velocity(product_id: int, warehouse_id: Optional[int] = None) -> float:
    clause = warehouse_filter_clause(warehouse_id)
    row = query_one(
        f"""
        SELECT COALESCE(AVG(units_sold), 0) AS v
        FROM fact_sales_daily
        WHERE product_id = :pid
          AND date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days' {clause}
        """,
        {"pid": product_id, "warehouse_id": warehouse_id},
    )
    return float(row.get("v") or 0)


def _velocity_percentile_threshold(warehouse_id: Optional[int] = None, percentile: float = 0.75) -> float:
    """The Nth percentile of trailing-30-day average daily units across the
    whole catalog, used as the "fast mover" cutoff for velocity-aware
    placement scoring - relative to the current catalog rather than a fixed
    number, so it stays meaningful as sales volume changes over time."""
    clause = warehouse_filter_clause(warehouse_id)
    row = query_one(
        f"""
        WITH per_product AS (
            SELECT product_id, AVG(units_sold) AS v
            FROM fact_sales_daily
            WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days' {clause}
            GROUP BY product_id
        )
        SELECT PERCENTILE_CONT(:p) WITHIN GROUP (ORDER BY v) AS t FROM per_product
        """,
        {"warehouse_id": warehouse_id, "p": percentile},
    )
    return float(row.get("t") or 0)


def get_pending_placement(limit: int = 100) -> list[dict]:
    """Products added via the Admin UI (or freshly loaded with no assigned
    slot yet) that need someone to run the Smart Placement Advisor for them.
    Products aren't warehouse-scoped in the catalog, so this list is the
    same for every login - each warehouse's operator runs the advisor
    against their own warehouse_id when they act on one."""
    return query_records(
        """
        SELECT p.product_id, p.product_name, p.category,
               d.length_cm, d.width_cm, d.height_cm, d.weight_kg,
               d.storage_type, d.fragility
        FROM dim_product_dimensions d
        JOIN dim_products p ON p.product_id = d.product_id
        WHERE d.pending_placement = true
        ORDER BY p.product_id DESC
        LIMIT :limit
        """,
        {"limit": limit},
    )


def mark_placed(product_id: int, location_id: int) -> dict:
    """Confirms a product was actually placed at a specific location -
    records it in dim_product_placements (one row per product+warehouse, see
    migrations.py for why) in addition to clearing pending_placement, so
    "what's stored at this location" (get_location_detail below) has a real
    answer for placements made through this flow, not just a reconstructed
    guess. warehouse_id is derived from the location itself rather than
    trusted from the caller, so a mismatched pair can't be sent by mistake."""
    loc = query_one("SELECT warehouse_id FROM dim_storage_locations WHERE location_id = :lid", {"lid": location_id})
    if not loc:
        raise ValueError(f"location_id {location_id} not found")
    warehouse_id = loc["warehouse_id"]
    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE dim_product_dimensions SET pending_placement = false WHERE product_id = :pid"),
            {"pid": product_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"product_id {product_id} not found")
        conn.execute(
            text("UPDATE dim_products SET pending_placement = false WHERE product_id = :pid"),
            {"pid": product_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO dim_product_placements (product_id, warehouse_id, location_id, assigned_at, is_backfilled)
                VALUES (:pid, :wid, :lid, NOW(), false)
                ON CONFLICT (product_id, warehouse_id)
                DO UPDATE SET location_id = EXCLUDED.location_id, assigned_at = NOW(), is_backfilled = false
                """
            ),
            {"pid": product_id, "wid": warehouse_id, "lid": location_id},
        )
    return {"product_id": product_id, "warehouse_id": warehouse_id, "location_id": location_id, "pending_placement": False}


def mark_placed_bulk(product_id: int, location_ids: list[int]) -> dict:
    """"Confirm Putaway for All Locations" - the New Products Awaiting
    Placement panel's putaway grid lets an operator pick one candidate
    location per warehouse (see suggest_locations's per-warehouse grid
    above) and confirm every warehouse's choice together in a single
    action, instead of repeating mark_placed once per warehouse from the
    frontend. Same effect as calling mark_placed() once per location_id,
    but as one atomic transaction (all placements succeed together or none
    are written) and one audit-log-worthy action instead of several, which
    also avoids a partially-placed product if a later call in a sequence of
    separate requests were to fail.

    location_ids must belong to distinct warehouses - two locations in the
    same warehouse would silently overwrite each other in
    dim_product_placements (one row per product+warehouse), which almost
    certainly means the caller sent something other than "one choice per
    warehouse," so that's rejected rather than guessed about."""
    if not location_ids:
        raise ValueError("location_ids must not be empty")

    locations = query_records(
        "SELECT location_id, warehouse_id FROM dim_storage_locations WHERE location_id = ANY(:ids)",
        {"ids": location_ids},
    )
    found_ids = {loc["location_id"] for loc in locations}
    missing = [lid for lid in location_ids if lid not in found_ids]
    if missing:
        raise ValueError(f"location_id(s) not found: {missing}")

    warehouse_ids = [loc["warehouse_id"] for loc in locations]
    if len(set(warehouse_ids)) != len(warehouse_ids):
        raise ValueError("location_ids must belong to distinct warehouses - one choice per warehouse")

    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE dim_product_dimensions SET pending_placement = false WHERE product_id = :pid"),
            {"pid": product_id},
        )
        if result.rowcount == 0:
            raise ValueError(f"product_id {product_id} not found")
        conn.execute(
            text("UPDATE dim_products SET pending_placement = false WHERE product_id = :pid"),
            {"pid": product_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO dim_product_placements (product_id, warehouse_id, location_id, assigned_at, is_backfilled)
                VALUES (:pid, :wid, :lid, NOW(), false)
                ON CONFLICT (product_id, warehouse_id)
                DO UPDATE SET location_id = EXCLUDED.location_id, assigned_at = NOW(), is_backfilled = false
                """
            ),
            [{"pid": product_id, "wid": loc["warehouse_id"], "lid": loc["location_id"]} for loc in locations],
        )

    return {
        "product_id": product_id,
        "placements": [{"warehouse_id": loc["warehouse_id"], "location_id": loc["location_id"]} for loc in locations],
        "pending_placement": False,
    }


def get_location_detail(location_id: int) -> Optional[dict]:
    """Powers the heatmap's click-to-inspect popup: this location's own
    capacity/utilization data plus every product genuinely on record as
    placed there (dim_product_placements). is_backfilled on a product row
    means nobody actually chose that slot for it through the Placement
    Advisor - it's a reconstruction from migrations.py/storage_optimizer's
    backfill_scored_placements(), run because real historical placement was
    never tracked before Session 8. current_stock_on_hand comes from the
    same warehouse's most recent fact_inventory_daily row for that product -
    real data, not synthetic - so it can be None if that product/warehouse
    pair has no inventory history (shouldn't normally happen, since only
    stocked pairs get backfilled, but a manually-confirmed placement isn't
    restricted to only ever-stocked products).

    current_weight_kg/current_volume_cm3/utilization_pct come from
    v_storage_location_occupancy, not dim_storage_locations directly - they
    reflect the real products list returned below (each one's own weight_kg/
    volume_cm3, summed), so this location's stats and its product list can
    never contradict each other the way they used to when utilization was a
    disconnected synthetic seed value. is_synthetic_capacity now describes
    only max_weight_kg/max_volume_cm3 (the ceiling - still no real per-slot
    maximum-capacity data exists), not the current/utilization figures."""
    loc = query_one(
        """
        SELECT sl.location_id, sl.location_code, sl.warehouse_id, w.warehouse_name,
               sl.storage_type, sl.shelf_tier, sl.sub_location, sl.is_overstock_tier,
               sl.max_weight_kg, sl.max_volume_cm3, sl.current_weight_kg, sl.current_volume_cm3,
               sl.utilization_pct, sl.is_synthetic_capacity, sl.is_layout_synthetic
        FROM v_storage_location_occupancy sl
        JOIN dim_warehouses w ON w.warehouse_id = sl.warehouse_id
        WHERE sl.location_id = :id
        """,
        {"id": location_id},
    )
    if not loc:
        return None
    products = query_records(
        """
        SELECT p.product_id, p.product_name, p.category,
               d.weight_kg, d.length_cm, d.width_cm, d.height_cm,
               pp.assigned_at, pp.is_backfilled,
               latest_inv.stock_on_hand AS current_stock_on_hand
        FROM dim_product_placements pp
        JOIN dim_products p ON p.product_id = pp.product_id
        JOIN dim_product_dimensions d ON d.product_id = pp.product_id
        LEFT JOIN LATERAL (
            SELECT stock_on_hand
            FROM fact_inventory_daily f
            WHERE f.product_id = pp.product_id AND f.warehouse_id = pp.warehouse_id
            ORDER BY f.date_id DESC
            LIMIT 1
        ) latest_inv ON true
        WHERE pp.location_id = :id
        ORDER BY p.product_name
        """,
        {"id": location_id},
    )
    return {"location": loc, "products": products}


def backfill_scored_placements() -> int:
    """Fills in dim_product_placements for every (product, warehouse) pair
    that's genuinely stocked (has a fact_inventory_daily row), isn't
    pending_placement, and has NO placement row yet - using the exact same
    fit-score logic (_score_location, below) that a live Smart Placement
    Advisor suggestion uses, instead of the original launch-day placeholder
    (an arbitrary product_id-modulo round robin). Called from
    app/migrations.py on every startup, so this is also what keeps newly
    stocked products auto-placed going forward - see migrations.py's
    comment for how the one-time "redo the old round-robin rows" upgrade
    and this ordinary incremental fill fit together.

    Deliberately NOT a per-product loop calling suggest_locations() - at
    real-data scale (~3,000 products x up to 3 warehouses) that would mean
    tens of thousands of individual SQL round-trips during a blocking
    FastAPI startup event. Instead everything eligible, every storage
    location, and every product's trailing-30-day sales velocity are each
    fetched in ONE query, all scoring happens in-process against those
    DataFrames (still calling _score_location() itself so the math can
    never drift from what a live suggestion would say), and the results go
    back in a single batched INSERT.

    This simulates capacity filling up as it assigns products within the
    same run (a location's running current_weight_kg/current_volume_cm3
    increase in memory as products land on it, purely to stop every product
    that shares a fragility/size profile from all being told the same
    single "best" slot). The starting point for that simulation is
    v_storage_location_occupancy (app/migrations.py), not
    dim_storage_locations directly - i.e. real occupancy, computed from
    whatever's already in dim_product_placements (both prior real
    confirmations and any already-backfilled rows from an earlier run),
    not the base table's disconnected synthetic seed-time value. That
    matters: scoring against a fake "this shelf is already 92% full" number
    used to make the backfill avoid shelves for reasons that had nothing to
    do with what was actually recorded there, and it's what caused
    high-utilization heatmap cells to systematically end up with zero
    tracked products while low ones absorbed everything - fixed by making
    scoring and display agree on the same real numbers. The in-memory
    running total built up during this loop is never written back to the
    database - only inserted dim_product_placements rows persist - but
    since v_storage_location_occupancy recomputes live from that table on
    every read, the next call (or the next request to suggest_locations())
    sees this run's results automatically, without needing a manual sync.
    """
    eligible = query_df(
        """
        SELECT DISTINCT f.product_id, f.warehouse_id, d.storage_type,
               d.volume_cm3, d.weight_kg, d.fragility
        FROM fact_inventory_daily f
        JOIN dim_product_dimensions d ON d.product_id = f.product_id
        WHERE d.pending_placement = false
          AND NOT EXISTS (
              SELECT 1 FROM dim_product_placements pp
              WHERE pp.product_id = f.product_id AND pp.warehouse_id = f.warehouse_id
          )
        ORDER BY f.product_id
        """
    )
    if eligible.empty:
        return 0

    locations = query_df("SELECT * FROM v_storage_location_occupancy")
    if locations.empty:
        return 0

    # Trailing-30-day sales velocity per (product, warehouse), and the
    # catalog's 75th-percentile "fast mover" cutoff per warehouse - the
    # same two queries _product_velocity/_velocity_percentile_threshold run
    # per-product, batched here into one query each across every product so
    # the 5-factor (fast-mover + proximity) scoring path stays available
    # without a query per product.
    velocity_df = query_df(
        """
        SELECT product_id, warehouse_id, AVG(units_sold) AS v
        FROM fact_sales_daily
        WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days'
        GROUP BY product_id, warehouse_id
        """
    )
    velocity_lookup = {
        (int(r.product_id), int(r.warehouse_id)): float(r.v or 0) for r in velocity_df.itertuples()
    }

    threshold_df = query_df(
        """
        WITH per_product AS (
            SELECT product_id, warehouse_id, AVG(units_sold) AS v
            FROM fact_sales_daily
            WHERE date_id > (SELECT MAX(date_id) FROM fact_sales_daily) - INTERVAL '30 days'
            GROUP BY product_id, warehouse_id
        )
        SELECT warehouse_id, PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY v) AS t
        FROM per_product
        GROUP BY warehouse_id
        """
    )
    threshold_lookup = {int(r.warehouse_id): float(r.t or 0) for r in threshold_df.itertuples()}

    # Group candidate locations by (warehouse_id, storage_type) - the same
    # compatible-locations pool suggest_locations() queries per call - and
    # precompute the same location_code-based proximity ranking once per
    # pool instead of once per product.
    loc_state: dict[int, dict] = {}
    groups: dict[tuple, list[int]] = {}
    proximity_lookup: dict[tuple, dict] = {}
    for (wid, stype), group in locations.groupby(["warehouse_id", "storage_type"]):
        codes_sorted = sorted(group["location_code"].unique().tolist())
        n_codes = max(len(codes_sorted) - 1, 1)
        proximity_lookup[(wid, stype)] = {
            code: round(100 * (1 - rank / n_codes), 1) for rank, code in enumerate(codes_sorted)
        }
        ids = []
        for rec in group.to_dict("records"):
            loc_state[rec["location_id"]] = rec
            ids.append(rec["location_id"])
        groups[(wid, stype)] = ids

    rows_to_insert = []
    for row in eligible.itertuples():
        key = (row.warehouse_id, row.storage_type)
        loc_ids = groups.get(key)
        if not loc_ids:
            continue

        velocity = velocity_lookup.get((row.product_id, row.warehouse_id), 0.0)
        threshold = threshold_lookup.get(row.warehouse_id, 0.0)
        is_top_mover = velocity > 0 and threshold > 0 and velocity >= threshold
        proximity_by_code = proximity_lookup[key]

        weight_kg = float(row.weight_kg)
        volume_cm3 = float(row.volume_cm3)

        candidates = [loc_state[lid] for lid in loc_ids]
        fits = [
            loc
            for loc in candidates
            if (loc["max_weight_kg"] - loc["current_weight_kg"]) >= weight_kg
            and (loc["max_volume_cm3"] - loc["current_volume_cm3"]) >= volume_cm3
        ]
        pool = fits if fits else candidates

        best_loc = None
        best_score = -1.0
        for loc_dict in pool:
            proximity_score = proximity_by_code.get(loc_dict["location_code"])
            score, _ = _score_location(
                loc_dict,
                volume_cm3,
                weight_kg,
                row.fragility,
                is_top_mover=is_top_mover,
                proximity_score=proximity_score,
            )
            if score > best_score:
                best_score = score
                best_loc = loc_dict

        if best_loc is None:
            continue

        # Simulate this product landing there so the next product scored
        # against this same pool sees reduced headroom (see docstring).
        best_loc["current_weight_kg"] = float(best_loc["current_weight_kg"]) + weight_kg
        best_loc["current_volume_cm3"] = float(best_loc["current_volume_cm3"]) + volume_cm3

        rows_to_insert.append(
            {"pid": int(row.product_id), "wid": int(row.warehouse_id), "lid": int(best_loc["location_id"])}
        )

    if not rows_to_insert:
        return 0

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_product_placements (product_id, warehouse_id, location_id, assigned_at, is_backfilled)
                VALUES (:pid, :wid, :lid, NOW(), true)
                ON CONFLICT (product_id, warehouse_id)
                DO UPDATE SET location_id = EXCLUDED.location_id, assigned_at = NOW(), is_backfilled = true
                """
            ),
            rows_to_insert,
        )
    return len(rows_to_insert)


def _resolve_product_attrs(req: StorageSuggestRequest) -> dict:
    if req.product_id is not None:
        row = query_one(
            """
            SELECT d.length_cm, d.width_cm, d.height_cm, d.volume_cm3, d.weight_kg,
                   d.fragility, d.storage_type, p.product_name
            FROM dim_product_dimensions d
            JOIN dim_products p ON p.product_id = d.product_id
            WHERE d.product_id = :product_id
            """,
            {"product_id": req.product_id},
        )
        if not row:
            raise ValueError(f"product_id {req.product_id} not found")
        return row

    if not all([req.length_cm, req.width_cm, req.height_cm, req.weight_kg]):
        raise ValueError("Provide either product_id or length_cm/width_cm/height_cm/weight_kg")

    volume_cm3 = req.length_cm * req.width_cm * req.height_cm
    storage_type = req.storage_type or "AMBIENT"

    return {
        "length_cm": req.length_cm,
        "width_cm": req.width_cm,
        "height_cm": req.height_cm,
        "volume_cm3": volume_cm3,
        "weight_kg": req.weight_kg,
        "fragility": req.fragility or "MEDIUM",
        "storage_type": storage_type,
        "product_name": "New product",
    }


def _score_location(
    loc: dict,
    volume_cm3: float,
    weight_kg: float,
    fragility: str,
    is_top_mover: bool = False,
    proximity_score: Optional[float] = None,
) -> tuple[float, list[str]]:
    reasons = []

    remaining_weight_pct = 1 - (loc["current_weight_kg"] / loc["max_weight_kg"])
    remaining_volume_pct = 1 - (loc["current_volume_cm3"] / loc["max_volume_cm3"])
    headroom_pct = max(0.0, min(remaining_weight_pct, remaining_volume_pct))
    score_headroom = headroom_pct * 100
    reasons.append(f"{round(headroom_pct * 100)}% free capacity")

    space_efficiency = volume_cm3 / loc["max_volume_cm3"]
    if 0.02 <= space_efficiency <= 0.25:
        score_fit = 100.0
        reasons.append("right-sized fit")
    else:
        target = 0.10
        score_fit = max(0.0, 100 - abs(space_efficiency - target) * 250)
        if space_efficiency > 0.25:
            reasons.append("item is large relative to this slot")
        else:
            reasons.append("slot is oversized for this item")

    if fragility == "HIGH":
        tier = loc["shelf_tier"]
        if loc["is_overstock_tier"]:
            score_fragility = 20.0
            reasons.append("fragile item on an overstock tier - not ideal")
        elif 1 <= tier <= 4:
            score_fragility = 100.0
            reasons.append("low/mid shelf tier suits a fragile item")
        else:
            score_fragility = 60.0
    else:
        score_fragility = 100.0

    if loc["is_overstock_tier"]:
        score_overstock = 0.0
    else:
        score_overstock = 100.0
        reasons.append("active (non-overstock) tier")

    # Velocity-aware placement: when the product is a fast mover (trailing
    # sales velocity at/above the catalog's 75th percentile - see
    # _velocity_percentile_threshold) and this candidate location has a
    # dispatch-proximity score, factor it in as a 5th weighted term. This app
    # has no real aisle/distance data, so "proximity" is a synthetic proxy -
    # locations are ranked by location_code within the same warehouse +
    # storage_type pool, with a lower code assumed closer to
    # dispatch/packing (a common warehouse-numbering convention, same kind of
    # documented assumption as is_layout_synthetic elsewhere in this app).
    # Non-fast-movers, and any call that doesn't pass a proximity_score
    # (e.g. every call before this feature existed), get the original
    # 4-factor scoring unchanged.
    if is_top_mover and proximity_score is not None:
        if proximity_score >= 66:
            reasons.append("close to dispatch - good for a fast-moving item")
        elif proximity_score <= 33:
            reasons.append("further from dispatch - a fast mover might do better in a closer slot")
        total = (
            0.28 * score_headroom
            + 0.24 * score_fit
            + 0.16 * score_fragility
            + 0.12 * score_overstock
            + 0.20 * proximity_score
        )
        return round(min(100.0, max(0.0, total)), 1), reasons[:4]

    total = 0.35 * score_headroom + 0.30 * score_fit + 0.20 * score_fragility + 0.15 * score_overstock
    return round(min(100.0, max(0.0, total)), 1), reasons[:3]


def suggest_locations(req: StorageSuggestRequest) -> dict:
    """Smart Placement Advisor. req.warehouse_id=None searches every
    compatible location across all warehouses (currently 3, but not
    hardcoded to that count) and returns up to req.top_n best-fit candidates
    for EACH warehouse (not one overall list of req.top_n regardless of
    warehouse, and not just a single best pick per warehouse either) -
    powers a putaway grid in the frontend: one row per warehouse, one
    column per candidate, so an operator can pick a specific slot in every
    warehouse and confirm them all together as one putaway (see
    mark_placed_bulk below). When req.warehouse_id IS set (a single-
    warehouse request), req.top_n instead caps one flat "best N overall"
    list the ordinary way - unchanged from before this behavior existed.
    The frontend's dashboard-wide warehouse filter is deliberately NOT
    threaded through into this call from the New Products Awaiting
    Placement panel, since a genuinely new product should be shown options
    in every warehouse, not just whichever one the page happens to be
    filtered to when someone clicks "Suggest Location". A WAREHOUSE-role
    user's request is still forced back to their own warehouse_id
    regardless (app/auth.py's effective_warehouse_id, applied in the router
    before this function ever runs) - that's an access-control boundary,
    not this behavior, and is unaffected by any of the above.
    """
    attrs = _resolve_product_attrs(req)
    storage_type = attrs["storage_type"]

    # Velocity-aware scoring only kicks in for an existing, catalogued
    # product (a brand-new product typed into the form has no sales history
    # to be a "fast mover" against yet).
    is_top_mover = False
    if req.product_id is not None:
        velocity = _product_velocity(req.product_id, req.warehouse_id)
        threshold = _velocity_percentile_threshold(req.warehouse_id)
        is_top_mover = velocity > 0 and threshold > 0 and velocity >= threshold
        attrs["avg_daily_units"] = round(velocity, 2)
        attrs["is_top_mover"] = is_top_mover

    compatible_types = [storage_type]

    # v_storage_location_occupancy (app/migrations.py), not
    # dim_storage_locations directly: a live suggestion has to be scored
    # against what's actually recorded as stored at each candidate today,
    # not a disconnected synthetic seed-time number - otherwise the Advisor
    # could recommend a shelf that looks empty on paper but is genuinely
    # full of tracked products, or avoid one that's genuinely wide open.
    clause = warehouse_filter_clause(req.warehouse_id)
    candidates = query_df(
        f"""
        SELECT *
        FROM v_storage_location_occupancy
        WHERE storage_type = ANY(:types) {clause}
        """,
        {"types": compatible_types, "warehouse_id": req.warehouse_id},
    )

    if candidates.empty:
        return {"product": attrs, "suggestions": [], "message": f"No {storage_type} locations found."}

    # Synthetic dispatch-proximity proxy (see _score_location's docstring
    # comment) - ranked within each warehouse's own (warehouse_id,
    # storage_type) pool, never across warehouses: Kimmage and Finglas were
    # seeded with the same location_code range as Lombard (see Session 2's
    # notes), so a single flat ranking across all candidates would silently
    # compare a Lombard code against a same-numbered but physically
    # unrelated Kimmage/Finglas code as if they were one ranking. Mirrors
    # backfill_scored_placements()'s own per-(warehouse_id, storage_type)
    # grouping below, for the same reason. This only matters once a
    # suggestion can span more than one warehouse, i.e. whenever
    # req.warehouse_id is None - a single-warehouse request still produces
    # exactly the same ranking as before.
    proximity_lookup: dict[tuple, dict] = {}
    for (wid, stype), group in candidates.groupby(["warehouse_id", "storage_type"]):
        codes_sorted = sorted(group["location_code"].unique().tolist())
        n_codes = max(len(codes_sorted) - 1, 1)
        proximity_lookup[(wid, stype)] = {
            code: round(100 * (1 - rank / n_codes), 1) for rank, code in enumerate(codes_sorted)
        }

    # Which candidates actually get scored: only ones with enough real
    # headroom for this item, falling back to every compatible location in
    # that warehouse when nothing there qualifies. Done per warehouse
    # (rather than once globally) so a warehouse where nothing currently
    # fits isn't silently dropped just because some *other* warehouse
    # happens to have room - that would break the "always one suggestion
    # per warehouse" guarantee below. A single-warehouse request only ever
    # has one warehouse to begin with, so this is equivalent to the old
    # global check for that case.
    fits_mask = (candidates["max_weight_kg"] - candidates["current_weight_kg"] >= attrs["weight_kg"]) & (
        candidates["max_volume_cm3"] - candidates["current_volume_cm3"] >= attrs["volume_cm3"]
    )
    pool_parts = []
    relaxed = False
    for _, group in candidates.groupby("warehouse_id"):
        group_fits = group[fits_mask.loc[group.index]]
        if group_fits.empty:
            pool_parts.append(group)
            relaxed = True
        else:
            pool_parts.append(group_fits)
    pool = pd.concat(pool_parts)

    scored = []
    for _, loc in pool.iterrows():
        loc_dict = loc.to_dict()
        proximity_by_code = proximity_lookup.get((loc_dict["warehouse_id"], loc_dict["storage_type"]), {})
        proximity_score = proximity_by_code.get(loc_dict["location_code"])
        score, reasons = _score_location(
            loc_dict,
            attrs["volume_cm3"],
            attrs["weight_kg"],
            attrs["fragility"],
            is_top_mover=is_top_mover,
            proximity_score=proximity_score,
        )
        scored.append(
            {
                "location_id": int(loc_dict["location_id"]),
                "location_code": int(loc_dict["location_code"]),
                "warehouse_id": int(loc_dict["warehouse_id"]),
                "storage_type": loc_dict["storage_type"],
                "shelf_tier": int(loc_dict["shelf_tier"]),
                "sub_location": int(loc_dict["sub_location"]),
                "utilization_pct": float(loc_dict["utilization_pct"]),
                "fit_score": score,
                "reasons": reasons,
            }
        )

    scored.sort(key=lambda r: r["fit_score"], reverse=True)

    if req.warehouse_id is None:
        # req.top_n best-fit locations PER warehouse, guaranteed - not "top N
        # overall regardless of warehouse spread" (that would let one
        # warehouse's merely-decent options crowd out another warehouse's
        # options entirely) and not just a single best pick per warehouse
        # either. This powers a putaway grid: one row per warehouse, up to
        # req.top_n candidate columns in that row, so an operator can choose
        # a specific slot in every warehouse and confirm all of them as one
        # "putaway" action (see mark_placed_bulk below) - not just see the
        # single top choice per warehouse with no alternative. Future-proof
        # as more warehouses get added later: however many distinct
        # warehouses appear in the candidate pool, that's how many rows come
        # back. `scored` is already sorted best-first, so slicing each
        # warehouse's own run of rows to req.top_n keeps that warehouse's
        # own best options; the combined list is then reordered
        # warehouse-then-rank so a UI can group it into rows in one pass
        # instead of re-sorting itself.
        by_warehouse: dict[int, list[dict]] = {}
        for row in scored:
            by_warehouse.setdefault(row["warehouse_id"], []).append(row)
        top = []
        for wid in sorted(by_warehouse):
            top.extend(by_warehouse[wid][: req.top_n])
    else:
        top = scored[: req.top_n]

    result = {"product": attrs, "suggestions": top}
    if relaxed:
        result["message"] = (
            "At least one warehouse has no location with enough free capacity for this item right now - "
            "showing its closest option anyway, ranked the same way as everywhere else."
        )
    return result
