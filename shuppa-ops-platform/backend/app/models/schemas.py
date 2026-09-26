from typing import Optional

from pydantic import BaseModel, Field


class StorageSuggestRequest(BaseModel):
    """Input for the Stock Optimizer's Smart Placement Advisor.

    Either pass an existing product_id (its real/synthetic physical
    attributes are looked up) or supply the physical attributes directly for
    a brand-new product that hasn't been catalogued yet.
    """

    product_id: Optional[int] = None
    length_cm: Optional[float] = Field(default=None, gt=0)
    width_cm: Optional[float] = Field(default=None, gt=0)
    height_cm: Optional[float] = Field(default=None, gt=0)
    weight_kg: Optional[float] = Field(default=None, gt=0)
    fragility: Optional[str] = Field(default=None, pattern="^(LOW|MEDIUM|HIGH)$")
    storage_type: Optional[str] = Field(default=None, pattern="^(AMBIENT|CHILLED|FROZEN|VAPE_DRAWER)$")
    warehouse_id: Optional[int] = Field(default=None, ge=1, le=3)
    top_n: int = Field(default=3, ge=1, le=10)


class DeliveryRiskRequest(BaseModel):
    supplier_id: int
    warehouse_id: int = Field(ge=1, le=3)
    order_quantity: float = Field(gt=0)
    lead_time_days: float = Field(gt=0)
    product_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Admin CRUD payloads
# ---------------------------------------------------------------------------

class AddWarehouseRequest(BaseModel):
    warehouse_name: str = Field(min_length=1, max_length=120)
    city: str = Field(default="Dublin", max_length=120)


class AddSupplierRequest(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    # None = common to all warehouses; a specific id = exclusive to that one.
    warehouse_id: Optional[int] = Field(default=None, ge=1, le=3)


class AddProductRequest(BaseModel):
    """Admin form for onboarding a brand-new product, including the physical
    dimensions the Stock Optimizer needs (this is the one place in the app
    where real, not synthetic, dimensions are captured)."""

    product_name: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    selling_price: float = Field(gt=0)
    unit_cost: float = Field(gt=0)
    category: Optional[str] = None
    length_cm: float = Field(gt=0)
    width_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)
    fragility: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH)$")
    storage_type: str = Field(default="AMBIENT", pattern="^(AMBIENT|CHILLED|FROZEN|VAPE_DRAWER)$")
    stackable: bool = True


class AddLocationRequest(BaseModel):
    """A location + one or more sub-locations (slots) under it."""

    warehouse_id: int = Field(ge=1, le=3)
    location_code: int = Field(gt=0)
    storage_type: str = Field(pattern="^(AMBIENT|CHILLED|FROZEN|VAPE_DRAWER)$")
    shelf_tier: int = Field(default=1, ge=0)
    sub_location_start: int = Field(default=1, ge=1)
    sub_location_count: int = Field(default=1, ge=1, le=200)
    is_overstock_tier: bool = False
    max_weight_kg: float = Field(gt=0)
    max_volume_cm3: float = Field(gt=0)
    note: Optional[str] = None


class MarkPlacedRequest(BaseModel):
    """Confirms a product was placed at a specific, real location - see
    storage_optimizer.mark_placed. location_id must be one of the
    Placement Advisor's own suggested locations (or any other valid
    dim_storage_locations row); the warehouse is derived from it server-side
    rather than trusted separately from the client."""

    product_id: int
    location_id: int


class MarkPlacedBulkRequest(BaseModel):
    """"Confirm Putaway for All Locations" - see
    storage_optimizer.mark_placed_bulk. One location_id per warehouse (the
    New Products Awaiting Placement panel's putaway grid enforces this on
    the frontend by only allowing one selection per warehouse row); the
    warehouses themselves are derived from the locations server-side, same
    as the single-location MarkPlacedRequest above."""

    product_id: int
    location_ids: list[int] = Field(min_length=1)


class DraftPurchaseOrderRequest(BaseModel):
    """A one-click "draft PO" created straight from a Reorder Suggestion -
    just records intent (who, what, how much, for which warehouse) so it can
    be reviewed and actually placed with the supplier outside this app.
    Doesn't touch fact_purchase_orders (that table is historical actuals
    loaded from CSV, not a live order queue)."""

    product_id: int
    supplier_id: Optional[int] = None
    warehouse_id: int = Field(ge=1, le=3)
    quantity: int = Field(gt=0)
    note: Optional[str] = None


# A simple, dependency-free email format check (no email-validator package -
# this project has been bitten before by an unpinned auth-adjacent
# dependency silently breaking, see the bcrypt/passlib note in README's
# Session 3 writeup, so this stays as a plain regex rather than adding one).
# Deliberately permissive: it's here to catch typos, not to be a strict RFC
# 5322 validator - the real proof an address works is the email arriving.
_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Shared minimum for every account password in the app (login accounts,
# self-registration, forgot-password resets, and forced changes) - raised
# from 6 to 10 as part of the login-security hardening pass. Deliberately
# just a length floor and not a complexity rule (no forced
# uppercase/digit/symbol mix): modern guidance (e.g. NIST SP 800-63B) rates
# length as a better predictor of real-world password strength than
# complexity rules, which mostly just push people toward "Password1!"-style
# patterns.
_PASSWORD_MIN_LENGTH = 10


class AddUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=72)
    role: str = Field(pattern="^(ADMIN|WAREHOUSE)$")
    warehouse_id: Optional[int] = Field(default=None, ge=1, le=3)
    email: Optional[str] = Field(default=None, max_length=255, pattern=_EMAIL_PATTERN)


class UpdateUserRequest(BaseModel):
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=_PASSWORD_MIN_LENGTH, max_length=72)
    email: Optional[str] = Field(default=None, max_length=255, pattern=_EMAIL_PATTERN)


class RegisterRequest(BaseModel):
    """Self-service signup (POST /auth/register). Always creates a
    WAREHOUSE-role account pending Admin approval - self-registration can
    never grant ADMIN access, and the account can't log in
    (is_active=false) until an Admin approves it from Manage Users. See
    admin_service.register_user."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=72)
    email: str = Field(max_length=255, pattern=_EMAIL_PATTERN)
    warehouse_id: int = Field(ge=1, le=3)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(max_length=255, pattern=_EMAIL_PATTERN)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=72)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=72)


class BulkAddProductsRequest(BaseModel):
    products: list[AddProductRequest] = Field(min_length=1, max_length=500)


class BulkAddSuppliersRequest(BaseModel):
    suppliers: list[AddSupplierRequest] = Field(min_length=1, max_length=500)


class BulkAddLocationsRequest(BaseModel):
    locations: list[AddLocationRequest] = Field(min_length=1, max_length=500)


class UpdateSettingsRequest(BaseModel):
    # Free-form key -> value map so new settings can be added without a
    # schema change; app/migrations.py documents the known keys and defaults.
    settings: dict[str, str]


class SupplierReturnItemRequest(BaseModel):
    """One product line within a filed supplier return. `product_id` is set
    when the item is a recognized catalog product (e.g. an over-delivery of
    something already sold here); left unset when it's a genuinely wrong
    item that isn't in the catalog at all - `product_name_reported` is what
    staff typed in either case, since the reported name is worth keeping
    even once a product_id/resolution exists."""

    product_id: Optional[int] = None
    product_name_reported: str = Field(min_length=1, max_length=300)
    quantity: int = Field(gt=0)
    reason: str = Field(pattern="^(WRONG_PRODUCT|EXTRA_PRODUCT)$")


class CreateSupplierReturnRequest(BaseModel):
    """Filed when a delivery from a supplier included wrong or extra items
    that need resolving - shipped back, onboarded as a new catalog product,
    or kept and formalized with a draft PO. Just records intent, same as
    DraftPurchaseOrderRequest - nothing here is sent to the supplier
    automatically."""

    supplier_id: int
    warehouse_id: int = Field(ge=1, le=3)
    scheduled_return_date: Optional[str] = None
    note: Optional[str] = None
    items: list[SupplierReturnItemRequest] = Field(min_length=1, max_length=50)


class ResolveReturnItemRequest(BaseModel):
    """Admin's decision on one pending return line item. `quantity`/`note`
    are only used when resolution is PO_GENERATED (quantity defaults to the
    item's own reported quantity if omitted); `created_product_id` is only
    used when resolution is LISTED_AS_NEW_PRODUCT, set by the frontend after
    the Add Product form has actually created the product."""

    resolution: str = Field(pattern="^(RETURNED|LISTED_AS_NEW_PRODUCT|PO_GENERATED)$")
    quantity: Optional[int] = Field(default=None, gt=0)
    note: Optional[str] = None
    created_product_id: Optional[int] = None


class ResolveAlertRequest(BaseModel):
    """Marks one currently-showing Alerts Center alert as resolved, for one
    warehouse scope (warehouse_id omitted/None means the "All Warehouses"
    aggregate view). Unlike Supplier Returns, an alert isn't a stored row -
    it's a live threshold check recomputed on every request (see
    alerts_service.get_all_alerts) - so `count` is required: it's the
    alert's own count at the moment it's resolved, snapshotted so the alert
    can automatically reappear later if it recomputes with a different
    count. See alerts_service.resolve_alert() for the full behavior."""

    title: str = Field(min_length=1, max_length=200)
    warehouse_id: Optional[int] = Field(default=None, ge=1, le=3)
    count: int


class RollbackAlertRequest(BaseModel):
    """Undoes an earlier resolution recorded via ResolveAlertRequest - e.g. an
    admin resolved the wrong alert by mistake. No `count` needed since this
    just deletes the resolution row rather than snapshotting anything. See
    alerts_service.rollback_alert() for the full behavior."""

    title: str = Field(min_length=1, max_length=200)
    warehouse_id: Optional[int] = Field(default=None, ge=1, le=3)
