from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.auth import CurrentUser, require_admin
from app.models.schemas import (
    AddLocationRequest,
    AddProductRequest,
    AddSupplierRequest,
    AddUserRequest,
    AddWarehouseRequest,
    BulkAddLocationsRequest,
    BulkAddProductsRequest,
    BulkAddSuppliersRequest,
    UpdateUserRequest,
)
from app.services import admin_service, audit_service

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/warehouses")
def get_warehouses(current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.list_warehouses()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/warehouses")
def create_warehouse(req: AddWarehouseRequest, current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.add_warehouse(req, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suppliers")
def get_suppliers(current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.list_suppliers()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suppliers")
def create_supplier(req: AddSupplierRequest, current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.add_supplier(req, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suppliers/bulk")
def create_suppliers_bulk(req: BulkAddSuppliersRequest, current_user: CurrentUser = Depends(require_admin)):
    """CSV-upload-style bulk supplier onboarding - the frontend parses the
    CSV into a list of AddSupplierRequest rows and posts them all here in one
    call, mirroring POST /admin/products/bulk."""
    try:
        return admin_service.bulk_add_suppliers(req.suppliers, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/products")
def create_product(req: AddProductRequest, current_user: CurrentUser = Depends(require_admin)):
    """Adding a product here immediately marks it pending_placement=true, so
    it shows up in every warehouse's Stock Optimizer "New Products Awaiting
    Placement" panel until someone runs the Smart Placement Advisor for it
    and it's marked placed (POST /optimizer/mark-placed)."""
    try:
        return admin_service.add_product(req, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/products/bulk")
def create_products_bulk(req: BulkAddProductsRequest, current_user: CurrentUser = Depends(require_admin)):
    """CSV-upload-style bulk product onboarding - the frontend parses the CSV
    into a list of AddProductRequest rows and posts them all here in one call."""
    try:
        return admin_service.bulk_add_products(req.products, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/locations")
def create_location(req: AddLocationRequest, current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.add_location(req, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/locations/bulk")
def create_locations_bulk(req: BulkAddLocationsRequest, current_user: CurrentUser = Depends(require_admin)):
    """CSV-upload-style bulk storage-location onboarding - the frontend
    parses the CSV into a list of AddLocationRequest rows and posts them all
    here in one call, mirroring POST /admin/products/bulk."""
    try:
        return admin_service.bulk_add_locations(req.locations, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Manage Users
# ---------------------------------------------------------------------------

@router.get("/users")
def get_users(current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.list_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users")
def create_user(req: AddUserRequest, current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.add_user(req, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/users/{user_id}")
def patch_user(user_id: int, req: UpdateUserRequest, current_user: CurrentUser = Depends(require_admin)):
    try:
        return admin_service.update_user(user_id, req, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit-log")
def get_audit_log(
    limit: int = 100,
    username: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(require_admin),
):
    try:
        return audit_service.get_audit_log(limit, username, action, date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-log/filters")
def get_audit_log_filters(current_user: CurrentUser = Depends(require_admin)):
    """Powers the Audit Log page's username/action filter dropdowns."""
    try:
        return {
            "actions": audit_service.get_distinct_actions(),
            "usernames": audit_service.get_distinct_usernames(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
