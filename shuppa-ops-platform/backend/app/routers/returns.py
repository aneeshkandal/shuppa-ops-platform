from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user, require_admin
from app.models.schemas import CreateSupplierReturnRequest, ResolveReturnItemRequest
from app.services import returns_service

router = APIRouter(prefix="/supplier-returns", tags=["Supplier Returns"])


@router.get("/suppliers")
def suppliers_for_return_form(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Supplier dropdown for the "File a Return" form - any authenticated
    user, not admin-only (unlike GET /admin/suppliers)."""
    try:
        return returns_service.list_suppliers_for_warehouse(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
def list_returns(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return returns_service.list_returns(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{return_id}")
def return_detail(return_id: int, current_user: CurrentUser = Depends(get_current_user)):
    try:
        result = returns_service.get_return_detail(return_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if current_user.role == "WAREHOUSE" and result["warehouse_id"] != current_user.warehouse_id:
        raise HTTPException(status_code=403, detail="Not your warehouse")
    return result


@router.post("")
def file_return(req: CreateSupplierReturnRequest, current_user: CurrentUser = Depends(get_current_user)):
    """Any authenticated user can file a return - warehouse-scoped the same
    way as other operational actions like Draft PO / mark-placed, not
    admin-gated (resolving one is, per the user's explicit ask)."""
    try:
        req.warehouse_id = effective_warehouse_id(req.warehouse_id, current_user)
        return returns_service.create_return(req, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{return_item_id}/resolve")
def resolve_item(
    return_item_id: int,
    req: ResolveReturnItemRequest,
    current_user: CurrentUser = Depends(require_admin),
):
    try:
        return returns_service.resolve_return_item(return_item_id, req, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
