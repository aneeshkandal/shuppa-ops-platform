"""
Shuppa Operations Intelligence Platform - database seed script
================================================================

Run this ONCE (and again any time you want to reset/refresh the data) from a
machine that has network access to your Neon Postgres instance and the
backend/venv packages installed (sqlalchemy, psycopg2-binary, pandas, numpy,
passlib[bcrypt]).

It:
  1. Loads the real transactional CSVs (sales, inventory, purchase orders,
     deliveries, product master, store locations) from D:\\Projects\\SHUPPA.
  2. Builds dimension tables that don't exist yet in the source data:
       - dim_products        (adds a stable product_id + a derived category)
       - dim_suppliers       (the real ~89-name Irish supplier list you gave
         us, plus a handful of synthetic per-warehouse-only suppliers to
         demonstrate that concept. Flagged is_synthetic per row.)
       - dim_warehouses      (the 3 real Dublin warehouses: Lombard, Kimmage,
         Finglas)
       - dim_product_dimensions  (SYNTHETIC height/width/length/weight/
         fragility/storage_type per product - your source data has no
         physical dimensions, so this is generated with reproducible
         category-aware randomness. Every row is flagged is_synthetic=true.
         Also carries pending_placement, used to flag brand-new products
         added via the Admin UI that haven't been assigned a warehouse slot
         yet.)
       - dim_storage_locations   (your store_locations.csv enriched with
         SYNTHETIC capacity + current utilization, replicated once per
         warehouse. Lombard uses the REAL location->storage-type layout you
         gave us; Kimmage and Finglas don't have a real layout yet, so a
         distinct-but-structurally-similar layout is generated for each and
         flagged is_layout_synthetic=true - swap those in once you have the
         real Kimmage/Finglas shelving plans.)
       - dim_users           (login accounts: one ADMIN + one per warehouse.
         See PRINTED credentials at the end of this script's output, and
         change them before this goes anywhere near production.)
  3. Loads the fact tables, remapping their original 1-5 warehouse_id range
     down to the 3 real warehouses (((old_id - 1) % 3) + 1, so no historical
     rows are dropped - see README for why), and converts all GBP monetary
     columns to EUR at an illustrative fixed rate (this is NOT a live FX
     rate - see FX_RATE_GBP_TO_EUR below).
  4. Trains a small logistic-regression delivery-risk model (pure numpy, no
     extra dependency) on fact_purchase_orders + fact_deliveries and writes
     its coefficients to backend/app/ml_model.json for the API to load.

Every table is written with if_exists="replace" so this script is safe to
re-run from scratch as many times as you like. NOTE: re-running this wipes
out anything added later through the Admin UI (new products/suppliers/
warehouses/locations/users) since those live in the same tables - this
script is a full "reset to demo state" tool, not an incremental migration.

Usage (from a normal Windows terminal / PowerShell):
    cd D:\\Projects\\SHUPPA\\shuppa-ops-platform\\shuppa-ops-platform\\backend
    venv\\Scripts\\activate
    python scripts\\seed_database.py
"""

import json
import os
import re
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    # python-dotenv is optional - DATABASE_URL can also be set directly in
    # the environment. See backend/.env.example.
    pass

# ---------------------------------------------------------------------------
# Paths & config
# ---------------------------------------------------------------------------

DATA_DIR = os.getenv("SHUPPA_DATA_DIR", r"D:\Projects\SHUPPA")
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML_MODEL_PATH = os.path.join(BACKEND_DIR, "app", "ml_model.json")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/shuppa_dev",
)

RNG_SEED = 42
rng = np.random.default_rng(RNG_SEED)

# Illustrative fixed GBP->EUR rate used to convert the source data's monetary
# columns (they were captured in GBP from the original UK-market dataset).
# This is NOT pulled from a live FX feed - it's a reasonable point-in-time
# approximation so the numbers on screen are internally consistent EUR
# amounts rather than a bare currency-symbol swap. Change this constant (and
# re-run the seed) if you want a different rate.
FX_RATE_GBP_TO_EUR = 1.16


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def eur(series: pd.Series) -> pd.Series:
    return (series.astype(float) * FX_RATE_GBP_TO_EUR).round(2)


# ---------------------------------------------------------------------------
# 1. Product master + derived category
# ---------------------------------------------------------------------------

CATEGORY_RULES = [
    ("Wine & Champagne", r"champagne|prosecco|cava|wine|moet|bollinger|perignon"),
    ("Spirits", r"whisk(e)?y|vodka|\bgin\b|rum|tequila|liqueur|brandy|cognac"),
    ("Beer & Cider", r"\bbeer\b|lager|\bale\b|cider|stout"),
    ("Vapes & E-liquids", r"vape|e-?liquid|\bpod\b|\bcoil\b|disposable"),
    ("Adult & Wellness", r"lelo|vibrat|lubric|condom|dildo|wellness|intimacy"),
    ("Home & Grocery", r"soap|clean|detergent|snack|choc|coffee|tea\b"),
]


def derive_category(name: str, description: str) -> str:
    text_blob = f"{name} {description or ''}".lower()
    for category, pattern in CATEGORY_RULES:
        if re.search(pattern, text_blob):
            return category
    return "General Merchandise"


def build_dim_products() -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA_DIR, "shuppa_products_cleaned.csv"))
    df = df.reset_index(drop=True)
    df.insert(0, "product_id", df.index + 1)
    df["category"] = [
        derive_category(n, d) for n, d in zip(df["product_name"], df["description"])
    ]
    # Source prices/costs/profit are GBP in the original dataset - convert to
    # EUR (see FX_RATE_GBP_TO_EUR). margin_percent is a ratio, left as-is.
    for col in ("selling_price", "unit_cost", "gross_profit"):
        if col in df.columns:
            df[col] = eur(df[col])
    df["pending_placement"] = False
    return df


# ---------------------------------------------------------------------------
# 2. Synthetic product physical dimensions
# ---------------------------------------------------------------------------

# category -> (L cm range, W cm range, H cm range, weight kg range, fragility,
#              stackable default, primary storage_type, % chilled override)
CATEGORY_PHYSICAL_PROFILE = {
    "Wine & Champagne": ((7, 9), (7, 9), (28, 33), (1.0, 1.8), "HIGH", True, "AMBIENT", 0.15),
    "Spirits": ((7, 10), (7, 10), (24, 32), (0.9, 1.6), "HIGH", True, "AMBIENT", 0.0),
    "Beer & Cider": ((18, 30), (13, 20), (18, 25), (3.0, 9.0), "MEDIUM", True, "AMBIENT", 0.35),
    "Vapes & E-liquids": ((3, 9), (2, 5), (8, 14), (0.03, 0.25), "LOW", True, "VAPE_DRAWER", 0.0),
    "Adult & Wellness": ((8, 18), (5, 12), (3, 10), (0.1, 0.6), "LOW", True, "AMBIENT", 0.0),
    "Home & Grocery": ((6, 25), (6, 20), (6, 30), (0.15, 2.5), "LOW", True, "AMBIENT", 0.1),
    "General Merchandise": ((5, 40), (5, 30), (5, 45), (0.1, 6.0), "MEDIUM", True, "AMBIENT", 0.0),
}


def build_dim_product_dimensions(products: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, p in products.iterrows():
        (l_rng, w_rng, h_rng, wt_rng, fragility, stackable, storage_type, chilled_p) = (
            CATEGORY_PHYSICAL_PROFILE[p["category"]]
        )
        length_cm = round(float(rng.uniform(*l_rng)), 1)
        width_cm = round(float(rng.uniform(*w_rng)), 1)
        height_cm = round(float(rng.uniform(*h_rng)), 1)
        weight_kg = round(float(rng.uniform(*wt_rng)), 2)
        volume_cm3 = round(length_cm * width_cm * height_cm, 1)

        this_storage_type = storage_type
        if storage_type == "AMBIENT" and chilled_p > 0 and rng.random() < chilled_p:
            this_storage_type = "CHILLED"

        # A little fragility jitter so it's not 100% deterministic by category.
        fragility_roll = rng.random()
        if fragility_roll < 0.08:
            fragility_final = "HIGH"
        elif fragility_roll < 0.25:
            fragility_final = "MEDIUM"
        else:
            fragility_final = fragility

        rows.append(
            {
                "product_id": p["product_id"],
                "length_cm": length_cm,
                "width_cm": width_cm,
                "height_cm": height_cm,
                "volume_cm3": volume_cm3,
                "weight_kg": weight_kg,
                "fragility": fragility_final,
                "stackable": bool(stackable and fragility_final != "HIGH"),
                "storage_type": this_storage_type,
                "is_synthetic": True,
                "pending_placement": False,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Suppliers (real Irish supplier list) & warehouses (3 real Dublin sites)
# ---------------------------------------------------------------------------

# The real, common-to-all-warehouses supplier list, exactly as given. The
# first 50 (in list order) are mapped 1:1 onto the original synthetic
# supplier_id 1-50 already referenced by ~20k historical fact_purchase_orders
# rows, so all existing on-time-rate / order-value history stays intact -
# only the display name changes. Names beyond the first 50 have no order
# history yet (they're available for new orders going forward).
REAL_SUPPLIER_NAMES = [
    "Musgraves", "Alibaba", "Amazon", "Bread Nation (Bread41)", "CandyHero",
    "CARDBOUTIQUE", "CLOUDPICKER", "Dunnes Stores", "EuroGeneral",
    "Healthwise Pharmacies", "HP Nutrition", "House of Spice", "KaffeKapslen",
    "National Beauty Ireland", "Atlantico", "NOTINO", "Tesco",
    "Tipperary Crystal", "VELO", "AsiaMarket", "BARRY & FITZWILLIAM",
    "Barry Group", "Barry Group Chill", "Broderick's Handmade",
    "Bunalun Organic", "CHIMAC", "Creative Distribution", "Dublin Pizza",
    "eCIRETTE", "Edward Dillon", "EUROPA FOODS", "Febvre Wines", "Findlaters",
    "Gleneely Foods", "GRAND CRU BEERS", "GREEN ISLE FOODS",
    "Harry's Nut Butter", "HORGANS", "Hosons Brands", "HOTCHIP", "HR Foods",
    "Independent Irish Health Foods", "Lavins", "LELO", "LEYDENS",
    "Lindt & Sprungli Ltd", "M&D", "MACCROMAICS", "Pharmacy Supplies",
    "PRL Ambient", "Richmond Marketing", "S&W Chill", "S&W Wholesale",
    "SHERIDANS", "STAFFORD LYNCH", "TINDAL WINES", "Unify Brands",
    "Uniphar Group", "WHOLEFOODS", "Wicklow Wolf Brewing Company",
    "Brennans Bread", "Omalleys", "PRL", "Lilliput Trading Co", "BWG",
    "BWG Ambient", "BWG Chill", "BWG Frozen", "BWG Fruit & Veg",
    "CLASSIC DRINKS", "Glanbia Consumer Foods", "Italicatessen",
    "SYSCO IRELAND", "Bretzel Bakey", "Dole", "MUSGRAVES CHILL", "Oreillys",
    "Porkys", "Atlantis", "Comans", "All about", "Lithuanica", "Moyee",
    "Tipple",
]

# The last few names in the common list above are held back and re-assigned
# as warehouse-EXCLUSIVE suppliers (3 per warehouse) instead of common ones,
# to demonstrate "there could be more suppliers for different warehouses"
# without inventing brand-new names you didn't give us. They have no
# historical orders (new relationships), and only ever appear in that one
# warehouse's supplier list / delivery-risk supplier dropdown.
WAREHOUSE_EXCLUSIVE_SUPPLIER_COUNT = 3


def build_dim_suppliers(historical_supplier_ids) -> pd.DataFrame:
    n_common_pool = len(REAL_SUPPLIER_NAMES) - WAREHOUSE_EXCLUSIVE_SUPPLIER_COUNT * 3
    common_names = REAL_SUPPLIER_NAMES[:n_common_pool]
    exclusive_names = REAL_SUPPLIER_NAMES[n_common_pool:]

    rows = []
    sid = 1
    historical_ids = sorted(int(x) for x in historical_supplier_ids)
    for i, name in enumerate(common_names):
        has_history = i < len(historical_ids)
        rows.append(
            {
                "supplier_id": sid,
                "supplier_name": name,
                "warehouse_id": None,  # NULL = common to all warehouses
                "is_synthetic": False,
                "has_order_history": bool(has_history),
            }
        )
        sid += 1

    # 3 exclusive names per warehouse (Lombard=1, Kimmage=2, Finglas=3)
    for wh_id in (1, 2, 3):
        for j in range(WAREHOUSE_EXCLUSIVE_SUPPLIER_COUNT):
            idx = (wh_id - 1) * WAREHOUSE_EXCLUSIVE_SUPPLIER_COUNT + j
            name = exclusive_names[idx] if idx < len(exclusive_names) else f"Local Supplier {idx + 1}"
            rows.append(
                {
                    "supplier_id": sid,
                    "supplier_name": name,
                    "warehouse_id": wh_id,
                    "is_synthetic": False,
                    "has_order_history": False,
                }
            )
            sid += 1

    df = pd.DataFrame(rows)
    df["warehouse_id"] = df["warehouse_id"].astype("Int64")  # nullable int - keeps NULL clean instead of NaN/float
    return df


# Real Dublin warehouses. Addresses aren't part of the source data - if you
# have real street addresses for these three sites, add them here.
DUBLIN_WAREHOUSES = [
    (1, "Lombard", "Dublin"),
    (2, "Kimmage", "Dublin"),
    (3, "Finglas", "Dublin"),
]


def build_dim_warehouses() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"warehouse_id": w, "warehouse_name": n, "city": c, "is_synthetic": False}
            for w, n, c in DUBLIN_WAREHOUSES
        ]
    )


def remap_warehouse_id(series: pd.Series) -> pd.Series:
    """The source CSVs were captured against 5 UK warehouses; this project now
    models exactly 3 Dublin sites. Rather than drop ~40% of the historical
    rows, fold the old 1-5 range down onto the 3 real warehouse ids
    (((old - 1) % 3) + 1: 1->1, 2->2, 3->3, 4->1, 5->2) so every historical
    sales/inventory/purchase-order row still has a valid, populated
    warehouse. This is an assumption made to keep the real historical data -
    it is NOT a claim that old warehouse "4" and "1" were the same place.
    """
    return ((series.astype(int) - 1) % 3) + 1


# ---------------------------------------------------------------------------
# 4. Storage locations enriched with synthetic capacity/utilization,
#    replicated once per warehouse (each warehouse gets its own full
#    shelving layout, not a round-robin slice of one shared layout).
# ---------------------------------------------------------------------------

# The real location -> storage-type layout for LOMBARD (warehouse_id=1), as
# given directly by the warehouse owner (overrides whatever the CSV's "Type"
# column says, since that column turned out to be an unreliable/incomplete
# proxy for this). Location 54 doesn't exist in store_locations.csv at all
# (confirmed - only 53 and 55 do) and was a typo/duplicate for 55, so it's
# simply omitted here. Locations 33/37/44/46 are plain "Shelf" rows in the
# source data, consistent with Ambient. Location 50 was named "Ambient" in
# the same breath as the other four, but its raw Type column already says
# "Fridge" (identical structure/note to location 55, which IS in the Chill
# list) - that looks like an oversight rather than intent, so it's
# classified as Chilled here for Lombard.
#
# ASSUMPTION: this real layout is treated as Lombard's, since it was the
# first/flagship site this project was built around before the 3-warehouse
# expansion. Kimmage and Finglas don't have a real layout yet, so distinct
# synthetic ones are generated for them below (same code range, same total
# slot counts per temperature zone, different codes shuffled into each zone)
# - swap in their real layouts as soon as you have them.
LOMBARD_AMBIENT_CODES = {
    3, 5, 7, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 27, 28,
    29, 30, 31, 33, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46,
}
LOMBARD_CHILLED_CODES = {8, 9, 10, 34, 47, 50, 51, 53, 55, 56, 57, 58, 59}
LOMBARD_FROZEN_CODES = {1, 2, 4, 6, 48, 49}
# Vape drawers are a fixed structural fixture (specific drawer units), kept
# the same set of codes across all 3 warehouses.
VAPE_LOCATION_CODES = {23, 60, 61}

CAPACITY_RANGES = {
    # storage_type -> (max_weight_kg range, max_volume_cm3 range)
    "AMBIENT": ((150, 400), (150_000, 400_000)),
    "CHILLED": ((80, 250), (80_000, 220_000)),
    "FROZEN": ((60, 200), (60_000, 180_000)),
    "VAPE_DRAWER": ((5, 20), (3_000, 12_000)),
}


def _build_warehouse_type_maps() -> dict:
    """warehouse_id -> {"AMBIENT": set(codes), "CHILLED": set(codes), "FROZEN": set(codes)}"""
    maps = {1: {"AMBIENT": set(LOMBARD_AMBIENT_CODES), "CHILLED": set(LOMBARD_CHILLED_CODES), "FROZEN": set(LOMBARD_FROZEN_CODES)}}

    non_vape_codes = sorted(LOMBARD_AMBIENT_CODES | LOMBARD_CHILLED_CODES | LOMBARD_FROZEN_CODES)
    n_ambient, n_chilled = len(LOMBARD_AMBIENT_CODES), len(LOMBARD_CHILLED_CODES)

    for wh_id, seed_offset in ((2, 101), (3, 202)):
        local_rng = np.random.default_rng(RNG_SEED + seed_offset)
        shuffled = list(local_rng.permutation(non_vape_codes))
        maps[wh_id] = {
            "AMBIENT": set(shuffled[:n_ambient]),
            "CHILLED": set(shuffled[n_ambient:n_ambient + n_chilled]),
            "FROZEN": set(shuffled[n_ambient + n_chilled:]),
        }
    return maps


def _classify(code: int, wh_id: int, type_maps: dict) -> str:
    if code in VAPE_LOCATION_CODES:
        return "VAPE_DRAWER"
    m = type_maps[wh_id]
    if code in m["FROZEN"]:
        return "FROZEN"
    if code in m["CHILLED"]:
        return "CHILLED"
    return "AMBIENT"


def _load_base_location_grid() -> pd.DataFrame:
    """Read store_locations.csv once and apply the vape-drawer trim/pad that
    reconciles the CSV's placeholder sub-location counts with the real
    layout (60: 3 sections x 1-20 slots, 61: 2 sections x 1-25 slots, 23
    "Small Drawers": 1-40 slots)."""
    loc = pd.read_csv(os.path.join(DATA_DIR, "store_locations.csv"))

    loc = loc[~((loc["Location"] == 60) & (loc["SubLocation"] > 20))]
    loc = loc[~((loc["Location"] == 61) & (loc["SubLocation"] > 25))]

    loc23_extra = pd.DataFrame(
        [
            {"Location": 23, "Type": "Drawer Shelf", "Shelf": 1, "SubLocation": sub, "Note": "Small items storage"}
            for sub in range(31, 41)
        ]
    )
    loc = pd.concat([loc, loc23_extra], ignore_index=True)
    return loc.sort_values(["Location", "Shelf", "SubLocation"]).reset_index(drop=True)


def build_dim_storage_locations(inventory_util_by_wh: dict) -> pd.DataFrame:
    base_grid = _load_base_location_grid()
    type_maps = _build_warehouse_type_maps()

    per_warehouse_frames = []
    for wh_id in (1, 2, 3):
        loc = base_grid.copy()
        loc["warehouse_id"] = wh_id
        loc["storage_type"] = loc["Location"].apply(lambda code: _classify(code, wh_id, type_maps))
        loc["is_layout_synthetic"] = wh_id != 1  # only Lombard's layout is the real one

        is_overstock = []
        for _, row in loc.iterrows():
            note = str(row["Note"])
            tier = row["Shelf"]
            if "0 & 7" in note and tier in (0, 7):
                is_overstock.append(True)
            elif "0 & 6" in note and tier in (0, 6):
                is_overstock.append(True)
            else:
                is_overstock.append(False)
        loc["is_overstock_tier"] = is_overstock

        max_weight, max_volume, cur_weight, cur_volume = [], [], [], []
        base_pct = inventory_util_by_wh.get(wh_id, 0.55)
        for _, row in loc.iterrows():
            (w_rng, v_rng) = CAPACITY_RANGES[row["storage_type"]]
            mw = round(float(rng.uniform(*w_rng)), 1)
            mv = round(float(rng.uniform(*v_rng)), 1)
            max_weight.append(mw)
            max_volume.append(mv)

            jitter = rng.normal(0, 0.12)
            pct = base_pct + jitter
            if row["is_overstock_tier"]:
                pct += 0.25
            pct = float(np.clip(pct, 0.05, 1.15))  # allow slight over-100% to feed "overstocked" alerts
            cur_weight.append(round(mw * pct, 1))
            cur_volume.append(round(mv * pct, 1))

        loc["max_weight_kg"] = max_weight
        loc["max_volume_cm3"] = max_volume
        loc["current_weight_kg"] = cur_weight
        loc["current_volume_cm3"] = cur_volume
        loc["utilization_pct"] = round(
            (loc["current_weight_kg"] / loc["max_weight_kg"] * 100).combine(
                loc["current_volume_cm3"] / loc["max_volume_cm3"] * 100, max
            ),
            1,
        )
        loc["is_synthetic_capacity"] = True

        loc = loc.rename(
            columns={
                "Location": "location_code",
                "Type": "raw_type",
                "Shelf": "shelf_tier",
                "SubLocation": "sub_location",
                "Note": "note",
            }
        )
        per_warehouse_frames.append(loc)

    all_locs = pd.concat(per_warehouse_frames, ignore_index=True)
    all_locs = all_locs.sort_values(["warehouse_id", "location_code", "shelf_tier", "sub_location"]).reset_index(drop=True)
    all_locs.insert(0, "location_id", all_locs.index + 1)

    return all_locs[
        [
            "location_id", "location_code", "warehouse_id", "raw_type", "storage_type",
            "shelf_tier", "sub_location", "is_overstock_tier", "note",
            "max_weight_kg", "max_volume_cm3", "current_weight_kg", "current_volume_cm3",
            "utilization_pct", "is_synthetic_capacity", "is_layout_synthetic",
        ]
    ]


# ---------------------------------------------------------------------------
# 5. Users (Admin + one per warehouse)
# ---------------------------------------------------------------------------

DEFAULT_USERS = [
    # username, password, role, warehouse_id
    # Passwords are 10+ chars to satisfy the same minimum the app now
    # enforces on every other account (see AddUserRequest/UpdateUserRequest
    # in app/models/schemas.py) - these are still demo defaults, though:
    # must_change_password below forces a real password on first login.
    ("admin", "Admin@12345", "ADMIN", None),
    ("lombard", "Lombard@123", "WAREHOUSE", 1),
    ("kimmage", "Kimmage@123", "WAREHOUSE", 2),
    ("finglas", "Finglas@123", "WAREHOUSE", 3),
]


def build_dim_users() -> pd.DataFrame:
    try:
        from passlib.context import CryptContext
    except ImportError as exc:
        raise SystemExit(
            "passlib is required to seed login accounts. Install it with:\n"
            "    pip install \"passlib[bcrypt]\"\n"
            f"(original error: {exc})"
        )

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    rows = []
    for i, (username, password, role, warehouse_id) in enumerate(DEFAULT_USERS, start=1):
        rows.append(
            {
                "user_id": i,
                "username": username,
                "password_hash": pwd_context.hash(password),
                "role": role,
                "warehouse_id": warehouse_id,
            }
        )
    df = pd.DataFrame(rows)
    df["warehouse_id"] = df["warehouse_id"].astype("Int64")  # nullable int - keeps NULL clean instead of NaN/float
    df["is_active"] = True  # matches app/migrations.py's ALTER TABLE ... ADD COLUMN IF NOT EXISTS is_active
    df["last_login_at"] = pd.NaT
    df["failed_login_count"] = 0
    df["locked_until"] = pd.NaT
    df["email"] = None
    df["pending_approval"] = False
    # These are known, published demo credentials - force a real password
    # to be set on first login rather than trusting they get changed
    # eventually. Matches the one-time backfill in app/migrations.py so a
    # fresh reseed and an incrementally-migrated database end up identical.
    df["must_change_password"] = True
    return df


# Default dashboard-configurable settings (alert thresholds etc.) - kept in
# sync by hand with backend/app/migrations.py's DEFAULT_SETTINGS, since this
# script and the FastAPI app don't share imports. A fresh full reseed should
# leave the database in the same state a migrated-up existing one would be.
SETTINGS_DEFAULTS = {
    "stockout_pct_threshold": "5",
    "overstock_value_threshold": "200000",
    "supplier_late_pct_medium_threshold": "15",
    "supplier_late_pct_high_threshold": "25",
    "delivery_high_risk_alert_count": "3",
    "optimizer_overstocked_threshold": "90",
    "reorder_target_days_of_stock": "30",
    "dead_stock_days_threshold": "60",
}


# ---------------------------------------------------------------------------
# 6. Fact tables
# ---------------------------------------------------------------------------

def load_fact_tables():
    # Parse the date columns to real dates (not text) so Postgres stores them
    # as DATE/TIMESTAMP columns - the API relies on date arithmetic
    # (date_id > max(date_id) - interval '30 days', etc.) that only works on
    # a proper date type.
    sales = pd.read_csv(os.path.join(DATA_DIR, "fact_sales_daily.csv"), parse_dates=["date_id"])
    inventory = pd.read_csv(os.path.join(DATA_DIR, "fact_inventory_daily.csv"), parse_dates=["date_id"])
    po = pd.read_csv(
        os.path.join(DATA_DIR, "fact_purchase_orders.csv"),
        parse_dates=["order_date", "expected_delivery_date"],
    ).reset_index(drop=True)
    po.insert(0, "po_id", po.index + 1)
    deliveries = pd.read_csv(
        os.path.join(DATA_DIR, "fact_deliveries.csv"), parse_dates=["actual_delivery_date"]
    )

    # Fold the source data's 5-UK-warehouse ids down onto the 3 real Dublin
    # warehouses (see remap_warehouse_id's docstring).
    for df in (sales, inventory, po):
        df["warehouse_id"] = remap_warehouse_id(df["warehouse_id"])

    # GBP -> EUR (see FX_RATE_GBP_TO_EUR).
    sales["revenue"] = eur(sales["revenue"])
    sales["cost"] = eur(sales["cost"])
    sales["profit"] = eur(sales["profit"])
    inventory["stock_value"] = eur(inventory["stock_value"])
    po["order_cost"] = eur(po["order_cost"])

    return sales, inventory, po, deliveries


# ---------------------------------------------------------------------------
# 7. Delivery risk model (pure-numpy logistic regression)
# ---------------------------------------------------------------------------

FEATURE_NAMES = [
    "supplier_on_time_rate",
    "order_quantity",
    "lead_time_days",
    "warehouse_utilization_pct",
    "order_cost",
]


def train_delivery_risk_model(po: pd.DataFrame, deliveries: pd.DataFrame, inventory: pd.DataFrame) -> dict:
    merged = po.merge(deliveries, on="po_id", how="inner")
    merged["order_date"] = pd.to_datetime(merged["order_date"])
    merged["expected_delivery_date"] = pd.to_datetime(merged["expected_delivery_date"])
    merged["lead_time_days"] = (merged["expected_delivery_date"] - merged["order_date"]).dt.days
    merged["y"] = (merged["delivery_status"] == "LATE").astype(float)

    supplier_on_time = (
        merged.groupby("supplier_id")["y"].apply(lambda s: 1.0 - s.mean()).rename("supplier_on_time_rate")
    )
    merged = merged.merge(supplier_on_time, on="supplier_id", how="left")

    inv = inventory.copy()
    wh_util = (
        (inv["stock_on_hand"] / inv["max_stock_level"].replace(0, np.nan))
        .groupby(inv["warehouse_id"]).mean().rename("warehouse_utilization_pct") * 100
    )
    merged = merged.merge(wh_util, on="warehouse_id", how="left")

    X = merged[FEATURE_NAMES].astype(float).to_numpy()
    y = merged["y"].to_numpy()

    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds == 0] = 1.0
    Xs = (X - means) / stds

    n, d = Xs.shape
    Xb = np.hstack([np.ones((n, 1)), Xs])
    w = np.zeros(d + 1)
    lr = 0.1
    l2 = 0.01
    for _ in range(3000):
        z = Xb @ w
        p = 1.0 / (1.0 + np.exp(-z))
        grad = Xb.T @ (p - y) / n
        grad[1:] += l2 * w[1:] / n
        w -= lr * grad

    z = Xb @ w
    p = 1.0 / (1.0 + np.exp(-z))
    pred = (p >= 0.5).astype(float)
    accuracy = float((pred == y).mean())

    n_pos = y.sum()
    n_neg = len(y) - n_pos
    if n_pos > 0 and n_neg > 0:
        ranks = np.argsort(np.argsort(p)) + 1
        auc = float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))
    else:
        auc = float("nan")

    # The historical PO/delivery data in this dataset has only a weak signal
    # (features barely correlate with LATE outcomes - see README/SETUP notes),
    # so absolute predicted probabilities cluster tightly around the base
    # rate. Rather than use a fixed 50% cutoff (which would call almost
    # nothing "risky"), we bucket LOW/MEDIUM/HIGH by percentile rank of the
    # predicted probability within the training population, so the UI still
    # shows a meaningful relative risk spread.
    p50, p80 = float(np.percentile(p, 50)), float(np.percentile(p, 80))

    return {
        "feature_names": FEATURE_NAMES,
        "means": means.tolist(),
        "stds": stds.tolist(),
        "intercept": float(w[0]),
        "coefficients": w[1:].tolist(),
        "train_accuracy": round(accuracy, 4),
        "train_auc": round(auc, 4) if auc == auc else None,
        "n_training_rows": int(n),
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "supplier_on_time_rate_overall": float(supplier_on_time.mean()),
        "warehouse_utilization_pct_overall": float(wh_util.mean()),
        "order_quantity_mean": float(merged["order_quantity"].mean()),
        "order_quantity_std": float(merged["order_quantity"].std()),
        "lead_time_days_mean": float(merged["lead_time_days"].mean()),
        "risk_thresholds": {"low_max": p50, "medium_max": p80},
        "base_rate_late": float(y.mean()),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    log("Reading source CSVs from " + DATA_DIR)
    products = build_dim_products()
    log(f"  {len(products)} products")

    log("Generating synthetic product dimensions...")
    dimensions = build_dim_product_dimensions(products)

    sales, inventory, po, deliveries = load_fact_tables()
    log(f"  sales={len(sales)} inventory={len(inventory)} po={len(po)} deliveries={len(deliveries)}")
    log("  (warehouse_id remapped from the source 1-5 range onto the 3 real Dublin warehouses)")
    log(f"  (monetary columns converted GBP->EUR at {FX_RATE_GBP_TO_EUR})")

    historical_supplier_ids = po["supplier_id"].unique()
    suppliers = build_dim_suppliers(historical_supplier_ids)
    log(f"  {len(suppliers)} suppliers ({len(REAL_SUPPLIER_NAMES)} real names supplied)")
    warehouses = build_dim_warehouses()
    users = build_dim_users()
    log(f"  seeded {len(users)} login accounts (see printed credentials below)")

    log("Computing per-warehouse utilization baseline from real inventory data...")
    util_by_wh = (
        (inventory["stock_on_hand"] / inventory["max_stock_level"].replace(0, np.nan))
        .groupby(inventory["warehouse_id"]).mean().to_dict()
    )

    log("Generating synthetic storage-location capacity (3 warehouse-specific layouts)...")
    locations = build_dim_storage_locations(util_by_wh)

    log("Training delivery-risk logistic regression on real PO + delivery history...")
    model = train_delivery_risk_model(po, deliveries, inventory)
    log(f"  train_accuracy={model['train_accuracy']} train_auc={model['train_auc']}")

    os.makedirs(os.path.dirname(ML_MODEL_PATH), exist_ok=True)
    with open(ML_MODEL_PATH, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)
    log(f"Saved model coefficients to {ML_MODEL_PATH}")

    log(f"Connecting to database...")
    engine = create_engine(DATABASE_URL)

    tables = {
        "dim_products": products,
        "dim_product_dimensions": dimensions,
        "dim_suppliers": suppliers,
        "dim_warehouses": warehouses,
        "dim_users": users,
        "dim_storage_locations": locations,
        "fact_sales_daily": sales,
        "fact_inventory_daily": inventory,
        "fact_purchase_orders": po,
        "fact_deliveries": deliveries,
    }
    # This DB already has objects from an earlier/different schema setup
    # (views like vw_exec_revenue_overview, vw_dead_stock, etc., and FK
    # constraints on the fact tables) left over from before this rewrite -
    # they reference dim_products and would block a plain DROP TABLE. Since
    # this app no longer uses any of those views, drop each table we manage
    # with CASCADE first so the replace below always succeeds cleanly,
    # however this script has been run before (or never).
    log("Dropping any existing versions of these tables (CASCADE - clears old dependent views/constraints)...")
    with engine.begin() as conn:
        for name in tables.keys():
            conn.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE"))

    for name, df in tables.items():
        log(f"Writing {name} ({len(df)} rows)...")
        df.to_sql(name, engine, if_exists="replace", index=False, chunksize=5000, method="multi")

    log("Creating indexes...")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE dim_products ADD PRIMARY KEY (product_id)"))
        conn.execute(text("ALTER TABLE dim_product_dimensions ADD PRIMARY KEY (product_id)"))
        conn.execute(text("ALTER TABLE dim_suppliers ADD PRIMARY KEY (supplier_id)"))
        conn.execute(text("ALTER TABLE dim_warehouses ADD PRIMARY KEY (warehouse_id)"))
        conn.execute(text("ALTER TABLE dim_users ADD PRIMARY KEY (user_id)"))
        conn.execute(text("CREATE UNIQUE INDEX idx_users_username ON dim_users (username)"))
        conn.execute(text("CREATE UNIQUE INDEX idx_users_email ON dim_users (email) WHERE email IS NOT NULL"))
        conn.execute(text("ALTER TABLE dim_storage_locations ADD PRIMARY KEY (location_id)"))
        conn.execute(text("ALTER TABLE fact_purchase_orders ADD PRIMARY KEY (po_id)"))
        conn.execute(text("CREATE INDEX idx_sales_product ON fact_sales_daily (product_id)"))
        conn.execute(text("CREATE INDEX idx_sales_warehouse ON fact_sales_daily (warehouse_id)"))
        conn.execute(text("CREATE INDEX idx_sales_date ON fact_sales_daily (date_id)"))
        conn.execute(text("CREATE INDEX idx_inv_product ON fact_inventory_daily (product_id)"))
        conn.execute(text("CREATE INDEX idx_inv_warehouse ON fact_inventory_daily (warehouse_id)"))
        conn.execute(text("CREATE INDEX idx_inv_date ON fact_inventory_daily (date_id)"))
        conn.execute(text("CREATE INDEX idx_po_supplier ON fact_purchase_orders (supplier_id)"))
        conn.execute(text("CREATE INDEX idx_po_warehouse ON fact_purchase_orders (warehouse_id)"))
        conn.execute(text("CREATE INDEX idx_po_order_date ON fact_purchase_orders (order_date)"))
        conn.execute(text("CREATE INDEX idx_deliv_po ON fact_deliveries (po_id)"))
        conn.execute(text("CREATE INDEX idx_loc_warehouse ON dim_storage_locations (warehouse_id)"))
        conn.execute(text("CREATE INDEX idx_suppliers_warehouse ON dim_suppliers (warehouse_id)"))

    log("Creating dim_settings / dim_audit_log (dashboard settings + admin audit trail)...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dim_settings CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS dim_audit_log CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_settings (
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
                CREATE TABLE dim_audit_log (
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
        for key, value in SETTINGS_DEFAULTS.items():
            conn.execute(
                text("INSERT INTO dim_settings (setting_key, setting_value) VALUES (:k, :v) ON CONFLICT DO NOTHING"),
                {"k": key, "v": value},
            )

    log("Creating dim_draft_purchase_orders (Reorder Suggestions' one-click Draft PO action)...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dim_draft_purchase_orders CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_draft_purchase_orders (
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

    log("Creating dim_supplier_returns + dim_supplier_return_items (Supplier Returns card)...")
    log("  (left empty on purpose - populated only by real usage through")
    log("   returns_service.create_return(), same convention as dim_draft_purchase_orders above)")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dim_supplier_return_items CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS dim_supplier_returns CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_supplier_returns (
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
        conn.execute(text("CREATE INDEX idx_supplier_returns_supplier ON dim_supplier_returns (supplier_id)"))
        conn.execute(text("CREATE INDEX idx_supplier_returns_warehouse ON dim_supplier_returns (warehouse_id)"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_supplier_return_items (
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
        conn.execute(text("CREATE INDEX idx_supplier_return_items_return ON dim_supplier_return_items (return_id)"))
        conn.execute(
            text("CREATE INDEX idx_supplier_return_items_resolution ON dim_supplier_return_items (resolution)")
        )

    log("Creating dim_alert_resolutions (Alerts Center 'Resolve' button)...")
    log("  (left empty on purpose - alerts are recomputed live, not stored events;")
    log("   see app/services/alerts_service.py's resolve_alert() for the snapshot-and-")
    log("   reappear-on-change behavior)")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dim_alert_resolutions CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_alert_resolutions (
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
            text("CREATE INDEX idx_alert_resolutions_scope ON dim_alert_resolutions (alert_title, warehouse_id)")
        )

    log("Creating dim_password_reset_tokens (forgot-password flow)...")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dim_password_reset_tokens CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_password_reset_tokens (
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
        conn.execute(text("CREATE INDEX idx_password_reset_tokens_hash ON dim_password_reset_tokens (token_hash)"))

    log("Creating dim_product_placements (real product-to-slot tracking)...")
    log("  (left empty on purpose - app/migrations.py fills it on next app startup using the")
    log("   Smart Placement Advisor's real fit-score logic, not a seed-script shortcut, so there's")
    log("   only one place this scoring logic has to be kept correct)")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dim_product_placements CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_product_placements (
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
        conn.execute(text("CREATE INDEX idx_product_placements_location ON dim_product_placements (location_id)"))

    log("Creating dim_customers + fact_orders (synthetic customer/order-level layer for Sales Analytics)...")
    log("  (left empty on purpose - app/migrations.py fills them on next app startup via")
    log("   sales_service.backfill_synthetic_orders(), same one-place-only pattern as")
    log("   dim_product_placements above; supersedes the older fact_orders_hourly table)")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS fact_orders_hourly CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS fact_orders CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS dim_customers CASCADE"))
        conn.execute(
            text(
                """
                CREATE TABLE dim_customers (
                    customer_id INTEGER PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES dim_warehouses (warehouse_id),
                    first_order_date DATE NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX idx_dim_customers_warehouse ON dim_customers (warehouse_id)"))
        conn.execute(text("CREATE INDEX idx_dim_customers_first_order_date ON dim_customers (first_order_date)"))
        conn.execute(
            text(
                """
                CREATE TABLE fact_orders (
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
        conn.execute(text("CREATE INDEX idx_fact_orders_date ON fact_orders (order_date)"))
        conn.execute(text("CREATE INDEX idx_fact_orders_warehouse ON fact_orders (warehouse_id)"))
        conn.execute(text("CREATE INDEX idx_fact_orders_customer ON fact_orders (customer_id)"))

    log("Done. Database is fully (re)seeded.")
    log("")
    log("Login accounts (these will be FORCED to set a new password on first login):")
    for username, password, role, warehouse_id in DEFAULT_USERS:
        scope = "all warehouses" if warehouse_id is None else dict((w, n) for w, n, _ in DUBLIN_WAREHOUSES)[warehouse_id]
        log(f"    {username} / {password}   ({role}, {scope})")


if __name__ == "__main__":
    main()
