"""Idempotent startup migrations.

Runs once when the FastAPI app starts (see app/main.py's startup hook).
Every statement here is safe to run against a database that already has
these objects (CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS /
ON CONFLICT DO NOTHING), so schema additions made after this dashboard was
first seeded don't require the destructive full reseed that
scripts/seed_database.py does. seed_database.py also creates these same
objects fresh (with the same defaults) on a full reseed, so a brand-new
database and an incrementally-migrated one end up with identical schemas.
"""

import time

from sqlalchemy import text

from app.database import engine
from app.services import sales_service, storage_optimizer


def _log(msg: str) -> None:
    """Plain stdout progress logging, flushed immediately. Startup migrations
    used to run silently end-to-end - fine when every step was sub-second,
    but the newer backfills (real scoring, order distribution) can take
    a while against the real database, and a long silent gap is
    indistinguishable from a genuine hang. This makes progress visible in
    the same terminal `python run.py` already prints to, no new logging
    setup required."""
    print(f"[migrations] {msg}", flush=True)

DEFAULT_SETTINGS = {
    # Stock Summary alert thresholds
    "stockout_pct_threshold": "5",
    "overstock_value_threshold": "200000",
    # Supplier Summary risk-label thresholds (late % cutoffs)
    "supplier_late_pct_medium_threshold": "15",
    "supplier_late_pct_high_threshold": "25",
    # Delivery risk: how many "high risk" recent orders trigger an alert
    "delivery_high_risk_alert_count": "3",
    # Optimizer: utilization % above which a location counts as overstocked
    "optimizer_overstocked_threshold": "90",
    # Reorder suggestions: target days of stock-on-hand to replenish up to,
    # based on trailing average daily sales velocity (see
    # stock_service.get_reorder_suggestions).
    "reorder_target_days_of_stock": "30",
    # Dead stock report: a product with stock on hand but 0 units sold in
    # this many trailing days is flagged as "dead stock" (see
    # stock_service.get_dead_stock).
    "dead_stock_days_threshold": "60",
}


def run_migrations() -> None:
    _log("starting - schema DDL (tables/columns/indexes/views)...")
    _t0 = time.monotonic()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_settings (
                    setting_key VARCHAR(100) PRIMARY KEY,
                    setting_value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_audit_log (
                    audit_id SERIAL PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    user_id INTEGER,
                    username VARCHAR(100),
                    action VARCHAR(150) NOT NULL,
                    entity_type VARCHAR(100),
                    entity_id VARCHAR(100),
                    details TEXT
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true"))
        # Login hardening: last_login_at for the Manage Users page, plus a
        # simple failed-attempt counter/lockout (see app/auth.py) - not a
        # replacement for real account-security tooling, just a basic
        # brute-force speed bump for an internal ops tool.
        conn.execute(text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0"))
        conn.execute(text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP"))

        # Login security follow-up (self-service registration, forgot
        # password, and a forced-password-change flag) - see app/auth.py
        # and app/routers/auth.py.
        conn.execute(text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS email VARCHAR(255)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON dim_users (email) "
                "WHERE email IS NOT NULL"
            )
        )
        # true when a self-service /auth/register signup is waiting on an
        # Admin to approve it (see admin_service.register_user /
        # admin_service.update_user, and the Manage Users page). A brand new
        # column, so is_active accounts that already existed keep the
        # column's own false default - only a fresh registration sets it.
        conn.execute(
            text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS pending_approval BOOLEAN NOT NULL DEFAULT false")
        )

        # true right after an Admin sets/resets a user's password on their
        # behalf (they didn't choose it themselves), or for the well-known
        # seeded demo accounts below - app/auth.py's get_current_user blocks
        # every other endpoint until POST /auth/change-password clears it.
        # Guarded so the demo-account backfill only ever runs the one time
        # this column is first created, not on every startup - otherwise a
        # user who already changed their demo password would get incorrectly
        # re-flagged the next time the app restarts.
        column_already_existed = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'dim_users' AND column_name = 'must_change_password')"
            )
        ).scalar()
        conn.execute(
            text("ALTER TABLE dim_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false")
        )
        if not column_already_existed:
            conn.execute(
                text(
                    "UPDATE dim_users SET must_change_password = true "
                    "WHERE username IN ('admin', 'lombard', 'kimmage', 'finglas')"
                )
            )

        # Password-reset tokens for the forgot-password flow. Only a hash of
        # the token is stored (sha256, done in app/routers/auth.py) so a
        # database leak alone can't be used to reset anyone's password - the
        # raw token only ever exists in the emailed link and in the user's
        # browser. Short-lived (see ACCESS defaults in app/config.py's
        # neighbourhood - the expiry is actually set in code, not here) and
        # single-use via used_at.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_password_reset_tokens (
                    token_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    token_hash VARCHAR(128) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_hash ON dim_password_reset_tokens (token_hash)")
        )

        # Draft purchase orders created from the Reorder Suggestions panel's
        # one-click "Draft PO" action. This is intentionally separate from
        # fact_purchase_orders (historical actuals loaded from CSV, not a
        # live order queue) - a draft here records intent only; nothing
        # automatically places a real order with a supplier.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_draft_purchase_orders (
                    draft_po_id SERIAL PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT NOW(),
                    created_by VARCHAR(100),
                    product_id INTEGER NOT NULL,
                    supplier_id INTEGER,
                    warehouse_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    status VARCHAR(20) DEFAULT 'DRAFT',
                    note TEXT
                )
                """
            )
        )

        # Supplier returns: a delivery came in with wrong or extra items that
        # need resolving - shipped back, onboarded as a new catalog product
        # (if genuinely not in the catalog), or kept and formalized with a
        # draft PO (if it's actually a known product, via
        # dim_draft_purchase_orders above - hence this block coming after
        # it). Genuinely new operational data, not a synthetic backfill like
        # most other gaps in this app: both tables start empty (see
        # scripts/seed_database.py) and are only ever populated by real
        # usage through returns_service.create_return(), same convention as
        # dim_draft_purchase_orders. One header row per return (a single
        # delivery incident), one line-item row per affected product within
        # it, since a mis-delivery can easily involve more than one product
        # at once (see returns_service.py for the full resolve workflow).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_supplier_returns (
                    return_id SERIAL PRIMARY KEY,
                    supplier_id INTEGER NOT NULL REFERENCES dim_suppliers (supplier_id),
                    warehouse_id INTEGER NOT NULL REFERENCES dim_warehouses (warehouse_id),
                    filed_at TIMESTAMP DEFAULT NOW(),
                    filed_by VARCHAR(100),
                    scheduled_return_date DATE,
                    note TEXT
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_supplier_returns_supplier ON dim_supplier_returns (supplier_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_supplier_returns_warehouse ON dim_supplier_returns (warehouse_id)")
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_supplier_return_items (
                    return_item_id SERIAL PRIMARY KEY,
                    return_id INTEGER NOT NULL REFERENCES dim_supplier_returns (return_id) ON DELETE CASCADE,
                    product_id INTEGER REFERENCES dim_products (product_id),
                    product_name_reported VARCHAR(300) NOT NULL,
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    reason VARCHAR(20) NOT NULL CHECK (reason IN ('WRONG_PRODUCT', 'EXTRA_PRODUCT')),
                    resolution VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                        CHECK (resolution IN ('PENDING', 'RETURNED', 'LISTED_AS_NEW_PRODUCT', 'PO_GENERATED')),
                    resolved_at TIMESTAMP,
                    resolved_by VARCHAR(100),
                    linked_draft_po_id INTEGER REFERENCES dim_draft_purchase_orders (draft_po_id),
                    created_product_id INTEGER REFERENCES dim_products (product_id)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_supplier_return_items_return ON dim_supplier_return_items (return_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_supplier_return_items_resolution "
                "ON dim_supplier_return_items (resolution)"
            )
        )

        # Alerts Center "Resolve" button. Alerts aren't stored events - every
        # one is a live threshold check recomputed on each request (see
        # alerts_service.get_all_alerts) - so there's no row to update the way
        # Supplier Returns has. Resolving one instead snapshots its `count`
        # here; get_all_alerts hides that (title, warehouse) pair for as long
        # as it keeps recomputing to the same count, and it reappears on its
        # own the moment the count changes either way. warehouse_id uses 0 as
        # a sentinel for the "All Warehouses" scope (real warehouse ids are
        # 1-3) rather than NULL, since Postgres treats every NULL as distinct
        # for UNIQUE purposes and that would defeat the upsert below.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_alert_resolutions (
                    alert_resolution_id SERIAL PRIMARY KEY,
                    alert_title VARCHAR(200) NOT NULL,
                    warehouse_id INTEGER NOT NULL DEFAULT 0,
                    resolved_count INTEGER NOT NULL,
                    resolved_at TIMESTAMP DEFAULT NOW(),
                    resolved_by VARCHAR(100),
                    UNIQUE (alert_title, warehouse_id)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_alert_resolutions_scope "
                "ON dim_alert_resolutions (alert_title, warehouse_id)"
            )
        )

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                text(
                    "INSERT INTO dim_settings (setting_key, setting_value) VALUES (:k, :v) "
                    "ON CONFLICT (setting_key) DO NOTHING"
                ),
                {"k": key, "v": value},
            )

        # Real product-to-slot placement tracking (previously nonexistent -
        # POST /optimizer/mark-placed only ever flipped a pending_placement
        # flag, it never recorded WHICH location a product actually went
        # into, so "what's stored at this location" had no real answer).
        # One row per (product_id, warehouse_id) - a simplification: a
        # product is modeled as living in exactly one slot per warehouse,
        # not spread across several. is_backfilled=true marks a row this
        # migration created retroactively (see below) rather than one a
        # person actually chose via the Placement Advisor's "Place here"
        # action (app/routers/storage.py's mark_placed sets false for those).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_product_placements (
                    product_id INTEGER NOT NULL,
                    warehouse_id INTEGER NOT NULL,
                    location_id INTEGER NOT NULL REFERENCES dim_storage_locations (location_id),
                    assigned_at TIMESTAMP DEFAULT NOW(),
                    is_backfilled BOOLEAN NOT NULL DEFAULT false,
                    PRIMARY KEY (product_id, warehouse_id)
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_product_placements_location ON dim_product_placements (location_id)")
        )

        # A location's "current_weight_kg"/"current_volume_cm3"/"utilization_pct"
        # columns on dim_storage_locations itself are a launch-day synthetic
        # value (a randomized percentage of a randomized capacity range, baked
        # in at seed time - see seed_database.py's build_dim_storage_locations)
        # with NO link to which products are actually recorded as being there.
        # That mismatch used to be invisible, because the original round-robin
        # backfill (see below) assigned a product to every location regardless
        # of how "full" its synthetic number claimed to be. Real scoring
        # exposed it: a location seeded as 92% full gets correctly skipped by
        # every scoring pass (nothing should recommend an already-full-looking
        # shelf), so it now honestly shows zero *tracked* products - which,
        # sitting next to a stale "92% full" figure, reads as a contradiction.
        #
        # Fix: stop treating the base table's current_weight_kg/current_volume_cm3/
        # utilization_pct as ground truth anywhere read-facing or scoring-facing.
        # This view recomputes them LIVE from dim_product_placements (every
        # placed product's own single-unit weight_kg/volume_cm3, summed per
        # location - the same single-unit figures suggest_locations() and
        # _score_location() already reason about, not stock_on_hand-multiplied
        # totals, so "does this fit" stays consistent everywhere) - so a
        # location's shown occupancy is always exactly "the products actually
        # on record here," never a disconnected random seed value. Only the
        # CEILING (max_weight_kg/max_volume_cm3) stays synthetic - there's
        # still no real per-slot maximum-capacity data to replace it with.
        # The three raw columns on dim_storage_locations are left in place
        # (an admin-added location already inserts 0/0/0 there - see
        # admin_service.add_location) but are no longer read by anything;
        # every query that used to read them now reads this view instead.
        # A plain view, not materialized, so it's always live with no refresh
        # step to remember after mark_placed()/backfill_scored_placements().
        conn.execute(
            text(
                """
                CREATE OR REPLACE VIEW v_storage_location_occupancy AS
                SELECT
                    sl.location_id,
                    sl.location_code,
                    sl.warehouse_id,
                    sl.raw_type,
                    sl.storage_type,
                    sl.shelf_tier,
                    sl.sub_location,
                    sl.is_overstock_tier,
                    sl.note,
                    sl.max_weight_kg,
                    sl.max_volume_cm3,
                    COALESCE(occ.occ_weight_kg, 0)::numeric AS current_weight_kg,
                    COALESCE(occ.occ_volume_cm3, 0)::numeric AS current_volume_cm3,
                    COALESCE(
                        ROUND(
                            (GREATEST(
                                COALESCE(occ.occ_weight_kg, 0) / NULLIF(sl.max_weight_kg, 0),
                                COALESCE(occ.occ_volume_cm3, 0) / NULLIF(sl.max_volume_cm3, 0)
                            ) * 100)::numeric,
                            1
                        ),
                        0
                    ) AS utilization_pct,
                    sl.is_synthetic_capacity,
                    sl.is_layout_synthetic
                FROM dim_storage_locations sl
                LEFT JOIN (
                    SELECT pp.location_id,
                           SUM(d.weight_kg) AS occ_weight_kg,
                           SUM(d.volume_cm3) AS occ_volume_cm3
                    FROM dim_product_placements pp
                    JOIN dim_product_dimensions d ON d.product_id = pp.product_id
                    GROUP BY pp.location_id
                ) occ ON occ.location_id = sl.location_id
                """
            )
        )

        # Synthetic order + customer layer for "True Order Trends", "Peak
        # Order Time Analysis", "Customer Growth & Retention", last-mile
        # "Delivery & Fulfillment Performance", and "Return & Cancellation
        # Insights" on Sales Analytics. fact_sales_daily has never had an
        # order_id, a time-of-day, or a customer entity anywhere in Shuppa's
        # data.
        #
        # This supersedes an earlier, coarser fact_orders_hourly bucket table
        # (one row per hour per date/warehouse, dropped just below) that was
        # enough for order COUNT/revenue alone, but Customer Growth/Delivery
        # Performance/Returns all need real per-ORDER *and* per-CUSTOMER
        # identity, which a bucket table deliberately doesn't have - so
        # dim_customers/fact_orders (one row per individual synthetic order,
        # linked to a synthetic customer) is now the single source of truth
        # for every order-based figure, so two synthetic layers can never
        # quietly disagree with each other. See
        # sales_service.backfill_synthetic_orders() for exactly what's real
        # (each day's total revenue/units) vs. estimated (order count, hour,
        # customer identity/repeat behaviour, delivery outcome).
        conn.execute(text("DROP TABLE IF EXISTS fact_orders_hourly CASCADE"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS dim_customers (
                    customer_id INTEGER PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES dim_warehouses (warehouse_id),
                    first_order_date DATE NOT NULL
                )
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_dim_customers_warehouse ON dim_customers (warehouse_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_dim_customers_first_order_date ON dim_customers (first_order_date)")
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_orders (
                    order_id BIGSERIAL PRIMARY KEY,
                    customer_id INTEGER NOT NULL REFERENCES dim_customers (customer_id),
                    warehouse_id INTEGER NOT NULL REFERENCES dim_warehouses (warehouse_id),
                    order_date DATE NOT NULL,
                    order_hour SMALLINT NOT NULL CHECK (order_hour BETWEEN 0 AND 23),
                    order_value NUMERIC(10, 2) NOT NULL,
                    item_count INTEGER NOT NULL,
                    delivery_status VARCHAR(20) NOT NULL
                        CHECK (delivery_status IN ('ON_TIME', 'LATE', 'CANCELLED', 'RETURNED')),
                    delivery_minutes INTEGER
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_orders_date ON fact_orders (order_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_orders_warehouse ON fact_orders (warehouse_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fact_orders_customer ON fact_orders (customer_id)"))

    _log(f"schema DDL done ({time.monotonic() - _t0:.1f}s). Checking placement backfill status...")

    # Backfill: any product actually carrying stock in a warehouse
    # (fact_inventory_daily has a row for that product+warehouse) that isn't
    # awaiting placement but has no placement record yet gets one - scored
    # with the exact same fit-score logic (headroom, space efficiency,
    # fragility-appropriate shelf tier, active-vs-overstock tier, and
    # velocity/proximity for fast movers) a live Smart Placement Advisor
    # suggestion uses, via storage_optimizer.backfill_scored_placements().
    # This used to be a much simpler product_id-modulo round robin; it's
    # still a reconstruction, not real history (nobody ever recorded where
    # these products actually went), so it's still flagged is_backfilled=true
    # and the frontend still says so wherever it's shown - it's just a much
    # better-matched reconstruction now.
    #
    # Runs outside the DDL transaction above (and on its own connections,
    # via storage_optimizer's query helpers) rather than inside it, because
    # scoring runs a handful of read queries plus its own write against
    # tables the DDL block may not have committed yet - nesting it inside
    # that same open transaction risked a self-deadlock (a second connection
    # blocking on a lock the first one, still open and waiting on this
    # function to return, would never release).
    #
    # One-time upgrade, guarded by a dim_settings sentinel (there's no new
    # column to gate on this time, unlike the must_change_password backfill
    # above): the very first version of this backfill (see the docstring
    # above) used the naive round robin. The first time this code runs after
    # that, every is_backfilled=true row gets deleted so those pairs look
    # unplaced again, then falls through to the ordinary incremental fill
    # below to redo them with real scoring. Guarded so this delete+redo only
    # ever happens once, not on every restart - after that, only genuinely
    # new pairs (a product newly stocked, or newly un-pended) are missing a
    # row, and the incremental fill below picks up only those, same
    # self-healing property the original round robin had.
    with engine.connect() as conn:
        upgrade_already_done = conn.execute(
            text("SELECT 1 FROM dim_settings WHERE setting_key = 'placement_backfill_scored_v1'")
        ).scalar()
    if not upgrade_already_done:
        _log("one-time placement-scoring upgrade: clearing old backfilled rows for a redo...")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM dim_product_placements WHERE is_backfilled = true"))
            conn.execute(
                text(
                    "INSERT INTO dim_settings (setting_key, setting_value) VALUES "
                    "('placement_backfill_scored_v1', 'done') ON CONFLICT (setting_key) DO NOTHING"
                )
            )

    _log("scoring product-to-slot placements (storage_optimizer.backfill_scored_placements)...")
    _t1 = time.monotonic()
    placed = storage_optimizer.backfill_scored_placements()
    _log(f"placement backfill done ({time.monotonic() - _t1:.1f}s), {placed} placement(s) written.")

    # Unlike the self-healing placement backfill above, this is a genuine
    # ONE-TIME batch run (guarded by a dim_settings sentinel inside
    # backfill_synthetic_orders itself, same pattern as the placement-scoring
    # upgrade above) - sizing a believable customer pool needs the whole
    # year's order volume for a warehouse up front, which doesn't compose
    # with filling in a handful of new days later. On every startup after the
    # first, this call returns immediately (0 rows) once the sentinel is set.
    # Given the row counts involved (~750k orders, ~50k customers across all
    # warehouses), this first run can take a while against the real
    # database - sales_service._insert_chunked() logs progress per chunk so
    # a long first run is visible, not indistinguishable from a hang.
    _log("computing synthetic customers/orders (sales_service.backfill_synthetic_orders, one-time)...")
    _t2 = time.monotonic()
    order_rows = sales_service.backfill_synthetic_orders()
    _log(f"synthetic order backfill done ({time.monotonic() - _t2:.1f}s), {order_rows} order row(s) written.")
    _log(f"all migrations complete ({time.monotonic() - _t0:.1f}s total).")
