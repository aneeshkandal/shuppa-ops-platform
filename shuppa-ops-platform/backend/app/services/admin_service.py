"""Admin-only write operations: add warehouses, suppliers, products (with
physical dimensions) and storage locations/sub-locations.

These write directly against the live tables seed_database.py populates.
Re-running the seed script wipes anything added here (it's a full "reset to
demo state" tool) - see the seed script's own docstring.
"""

from typing import Optional

from sqlalchemy import text

from app.auth import CurrentUser, hash_password
from app.database import engine
from app.models.schemas import (
    AddLocationRequest,
    AddProductRequest,
    AddSupplierRequest,
    AddUserRequest,
    AddWarehouseRequest,
    RegisterRequest,
    UpdateUserRequest,
)

# NOTE: BulkAddSuppliersRequest / BulkAddLocationsRequest aren't imported here
# - bulk_add_suppliers()/bulk_add_locations() below take plain lists of
# AddSupplierRequest/AddLocationRequest (the router unwraps the request
# model), matching the existing bulk_add_products() pattern.
from app.services import audit_service
from app.services.db_utils import query_one, query_records


def add_warehouse(req: AddWarehouseRequest, actor: CurrentUser) -> dict:
    existing = query_one("SELECT MAX(warehouse_id) AS m FROM dim_warehouses")
    new_id = (existing["m"] or 0) + 1
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dim_warehouses (warehouse_id, warehouse_name, city, is_synthetic) "
                "VALUES (:id, :name, :city, false)"
            ),
            {"id": new_id, "name": req.warehouse_name, "city": req.city},
        )
    audit_service.log_action(actor, "add_warehouse", "warehouse", new_id, req.warehouse_name)
    return {"warehouse_id": new_id, "warehouse_name": req.warehouse_name, "city": req.city}


def add_supplier(req: AddSupplierRequest, actor: CurrentUser) -> dict:
    existing = query_one("SELECT MAX(supplier_id) AS m FROM dim_suppliers")
    new_id = (existing["m"] or 0) + 1
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO dim_suppliers (supplier_id, supplier_name, warehouse_id, is_synthetic, has_order_history) "
                "VALUES (:id, :name, :wh, false, false)"
            ),
            {"id": new_id, "name": req.supplier_name, "wh": req.warehouse_id},
        )
    audit_service.log_action(actor, "add_supplier", "supplier", new_id, req.supplier_name)
    return {"supplier_id": new_id, "supplier_name": req.supplier_name, "warehouse_id": req.warehouse_id}


def bulk_add_suppliers(suppliers: list[AddSupplierRequest], actor: CurrentUser) -> dict:
    """CSV-upload-style bulk supplier onboarding, mirroring bulk_add_products
    - the frontend parses the CSV into AddSupplierRequest rows and posts them
    all here in one call."""
    created = [add_supplier(s, actor) for s in suppliers]
    audit_service.log_action(actor, "bulk_add_suppliers", "supplier", None, f"{len(created)} suppliers")
    return {"created": created, "count": len(created)}


def add_product(req: AddProductRequest, actor: Optional[CurrentUser] = None) -> dict:
    existing = query_one("SELECT MAX(product_id) AS m FROM dim_products")
    new_id = (existing["m"] or 0) + 1
    category = req.category or "General Merchandise"
    gross_profit = round(req.selling_price - req.unit_cost, 2)
    margin_percent = round(gross_profit / req.selling_price * 100, 4) if req.selling_price else 0

    volume_cm3 = round(req.length_cm * req.width_cm * req.height_cm, 1)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_products
                    (product_id, product_name, barcode, selling_price, unit_cost,
                     description, gross_profit, margin_percent, category, pending_placement)
                VALUES
                    (:id, :name, NULL, :price, :cost, :desc, :gp, :margin, :cat, true)
                """
            ),
            {
                "id": new_id, "name": req.product_name, "price": req.selling_price, "cost": req.unit_cost,
                "desc": req.description, "gp": gross_profit, "margin": margin_percent, "cat": category,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO dim_product_dimensions
                    (product_id, length_cm, width_cm, height_cm, volume_cm3, weight_kg,
                     fragility, stackable, storage_type, is_synthetic, pending_placement)
                VALUES
                    (:id, :l, :w, :h, :vol, :wt, :frag, :stack, :st, false, true)
                """
            ),
            {
                "id": new_id, "l": req.length_cm, "w": req.width_cm, "h": req.height_cm, "vol": volume_cm3,
                "wt": req.weight_kg, "frag": req.fragility, "stack": req.stackable, "st": req.storage_type,
            },
        )

    if actor is not None:
        audit_service.log_action(actor, "add_product", "product", new_id, req.product_name)

    return {
        "product_id": new_id,
        "product_name": req.product_name,
        "category": category,
        "storage_type": req.storage_type,
        "pending_placement": True,
    }


def bulk_add_products(products: list[AddProductRequest], actor: CurrentUser) -> dict:
    created = [add_product(p, actor) for p in products]
    audit_service.log_action(actor, "bulk_add_products", "product", None, f"{len(created)} products")
    return {"created": created, "count": len(created)}


def add_location(req: AddLocationRequest, actor: CurrentUser) -> dict:
    existing = query_one("SELECT MAX(location_id) AS m FROM dim_storage_locations")
    next_id = (existing["m"] or 0) + 1

    rows_created = []
    with engine.begin() as conn:
        for offset in range(req.sub_location_count):
            sub_location = req.sub_location_start + offset
            loc_id = next_id + offset
            conn.execute(
                text(
                    """
                    INSERT INTO dim_storage_locations
                        (location_id, location_code, warehouse_id, raw_type, storage_type,
                         shelf_tier, sub_location, is_overstock_tier, note,
                         max_weight_kg, max_volume_cm3, current_weight_kg, current_volume_cm3,
                         utilization_pct, is_synthetic_capacity, is_layout_synthetic)
                    VALUES
                        (:id, :code, :wh, :storage_type, :storage_type,
                         :tier, :sub, :overstock, :note,
                         :maxw, :maxv, 0, 0, 0, false, false)
                    """
                ),
                {
                    "id": loc_id, "code": req.location_code, "wh": req.warehouse_id, "storage_type": req.storage_type,
                    "tier": req.shelf_tier, "sub": sub_location, "overstock": req.is_overstock_tier,
                    "note": req.note, "maxw": req.max_weight_kg, "maxv": req.max_volume_cm3,
                },
            )
            rows_created.append(loc_id)

    audit_service.log_action(
        actor, "add_location", "location", req.location_code, f"{req.sub_location_count} sub-location(s) in warehouse {req.warehouse_id}"
    )
    return {
        "location_ids": rows_created,
        "location_code": req.location_code,
        "warehouse_id": req.warehouse_id,
        "storage_type": req.storage_type,
        "sub_locations_added": req.sub_location_count,
    }


def bulk_add_locations(locations: list[AddLocationRequest], actor: CurrentUser) -> dict:
    """CSV-upload-style bulk storage-location onboarding, mirroring
    bulk_add_products - the frontend parses the CSV into AddLocationRequest
    rows and posts them all here in one call."""
    created = [add_location(loc, actor) for loc in locations]
    total_sub_locations = sum(c["sub_locations_added"] for c in created)
    audit_service.log_action(
        actor, "bulk_add_locations", "location", None,
        f"{len(created)} location(s), {total_sub_locations} sub-location(s) total",
    )
    return {"created": created, "count": len(created)}


def list_warehouses() -> list[dict]:
    return query_records("SELECT * FROM dim_warehouses ORDER BY warehouse_id")


def list_warehouses_public() -> list[dict]:
    """Same table as list_warehouses(), but explicitly narrowed to just id
    and name (not SELECT *) since this powers the registration page's
    warehouse dropdown at GET /auth/warehouses, which is unauthenticated -
    keeps that endpoint safe even if a more sensitive column is ever added
    to dim_warehouses later."""
    return query_records("SELECT warehouse_id, warehouse_name FROM dim_warehouses ORDER BY warehouse_id")


def list_suppliers(warehouse_id: Optional[int] = None) -> list[dict]:
    if warehouse_id is None:
        return query_records("SELECT * FROM dim_suppliers ORDER BY supplier_name")
    return query_records(
        "SELECT * FROM dim_suppliers WHERE warehouse_id IS NULL OR warehouse_id = :w ORDER BY supplier_name",
        {"w": warehouse_id},
    )


# ---------------------------------------------------------------------------
# Users (Manage Users admin page)
# ---------------------------------------------------------------------------

def list_users() -> list[dict]:
    return query_records(
        """
        SELECT user_id, username, email, role, warehouse_id, is_active,
               pending_approval, must_change_password, last_login_at,
               failed_login_count,
               locked_until,
               (locked_until IS NOT NULL AND locked_until > NOW()) AS is_locked
        FROM dim_users
        ORDER BY pending_approval DESC, user_id
        """
    )


def add_user(req: AddUserRequest, actor: CurrentUser) -> dict:
    existing = query_one("SELECT user_id FROM dim_users WHERE username = :u", {"u": req.username})
    if existing:
        raise ValueError(f"Username '{req.username}' is already taken")
    if req.role == "WAREHOUSE" and req.warehouse_id is None:
        raise ValueError("A WAREHOUSE-role user needs a warehouse_id")

    max_id = query_one("SELECT MAX(user_id) AS m FROM dim_users")
    new_id = (max_id["m"] or 0) + 1
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_users
                    (user_id, username, password_hash, role, warehouse_id, email,
                     is_active, must_change_password)
                VALUES (:id, :username, :hash, :role, :wh, :email, true, true)
                """
            ),
            {
                "id": new_id,
                "username": req.username,
                "hash": hash_password(req.password),
                "role": req.role,
                "wh": req.warehouse_id if req.role == "WAREHOUSE" else None,
                "email": req.email,
            },
        )
    # must_change_password=true above because the Admin chose this password,
    # not the user themselves - same reasoning as a reset in update_user().
    audit_service.log_action(actor, "add_user", "user", new_id, f"{req.username} ({req.role})")
    return {"user_id": new_id, "username": req.username, "role": req.role, "warehouse_id": req.warehouse_id}


def update_user(user_id: int, req: UpdateUserRequest, actor: CurrentUser) -> dict:
    target = query_one("SELECT user_id, username FROM dim_users WHERE user_id = :id", {"id": user_id})
    if not target:
        raise ValueError(f"user_id {user_id} not found")

    with engine.begin() as conn:
        if req.is_active is not None:
            # Approving a pending self-registration (see register_user
            # below) is just "set is_active=true" from Admin's point of
            # view - clear pending_approval at the same time so it stops
            # showing up as awaiting approval in Manage Users.
            conn.execute(
                text(
                    "UPDATE dim_users SET is_active = :active, "
                    "pending_approval = CASE WHEN :active THEN false ELSE pending_approval END "
                    "WHERE user_id = :id"
                ),
                {"active": req.is_active, "id": user_id},
            )
        if req.password:
            # Resetting a password also clears any lockout - this is the
            # only "unlock account" path Admin has (see auth.py's lockout
            # policy), so it doubles as that. must_change_password=true
            # because Admin chose this password on the user's behalf.
            conn.execute(
                text(
                    "UPDATE dim_users SET password_hash = :hash, failed_login_count = 0, "
                    "locked_until = NULL, must_change_password = true WHERE user_id = :id"
                ),
                {"hash": hash_password(req.password), "id": user_id},
            )
        if req.email is not None:
            conn.execute(
                text("UPDATE dim_users SET email = :email WHERE user_id = :id"),
                {"email": req.email, "id": user_id},
            )

    action = "deactivate_user" if req.is_active is False else "update_user"
    audit_service.log_action(actor, action, "user", user_id, target["username"])
    return {"user_id": user_id, "updated": True}


def register_user(req: RegisterRequest) -> dict:
    """Self-service signup (POST /auth/register, no auth required). Creates
    an inactive, pending-approval WAREHOUSE account - it can't log in until
    an Admin approves it from Manage Users (see update_user above). Unlike
    add_user, there's no `actor` (nobody is logged in yet), so this logs to
    the audit trail as a system event instead - see
    audit_service.log_system_event.
    """
    existing = query_one("SELECT user_id FROM dim_users WHERE username = :u", {"u": req.username})
    if existing:
        raise ValueError(f"Username '{req.username}' is already taken")
    existing_email = query_one("SELECT user_id FROM dim_users WHERE email = :e", {"e": req.email})
    if existing_email:
        raise ValueError(f"An account already uses the email '{req.email}'")

    max_id = query_one("SELECT MAX(user_id) AS m FROM dim_users")
    new_id = (max_id["m"] or 0) + 1
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO dim_users
                    (user_id, username, password_hash, role, warehouse_id, email,
                     is_active, pending_approval, must_change_password)
                VALUES (:id, :username, :hash, 'WAREHOUSE', :wh, :email, false, true, false)
                """
            ),
            {
                "id": new_id,
                "username": req.username,
                "hash": hash_password(req.password),
                "wh": req.warehouse_id,
                "email": req.email,
            },
        )
    audit_service.log_system_event(
        "register_pending_approval", "user", new_id, f"{req.username} ({req.email}) awaiting Admin approval"
    )
    return {"user_id": new_id, "username": req.username, "pending_approval": True}
