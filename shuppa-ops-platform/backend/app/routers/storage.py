from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user
from app.models.schemas import MarkPlacedBulkRequest, MarkPlacedRequest, StorageSuggestRequest
from app.services import audit_service, storage_optimizer

router = APIRouter(prefix="/optimizer", tags=["Stock Optimizer"])


@router.get("/tree")
def tree(warehouse_id: Optional[int] = Query(None, ge=1, le=3), current_user: CurrentUser = Depends(get_current_user)):
    try:
        return storage_optimizer.get_tree(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products")
def products(
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return storage_optimizer.get_products(search, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending-placement")
def pending_placement(limit: int = Query(100, ge=1, le=500), current_user: CurrentUser = Depends(get_current_user)):
    """New products (added via Admin) that haven't been assigned a warehouse
    slot yet - shown on every Stock Optimizer page so operators know what
    still needs inbounding."""
    try:
        return storage_optimizer.get_pending_placement(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-placed")
def mark_placed(req: MarkPlacedRequest, current_user: CurrentUser = Depends(get_current_user)):
    try:
        result = storage_optimizer.mark_placed(req.product_id, req.location_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    audit_service.log_action(
        current_user, "confirm_placement", "product", req.product_id, f"location_id={req.location_id}"
    )
    return result


@router.post("/mark-placed-bulk")
def mark_placed_bulk(req: MarkPlacedBulkRequest, current_user: CurrentUser = Depends(get_current_user)):
    """"Confirm Putaway for All Locations" - the New Products Awaiting
    Placement panel's putaway grid (one candidate location per warehouse,
    operator picks one per row) confirms all of them together through this
    single endpoint rather than one /mark-placed call per warehouse - see
    storage_optimizer.mark_placed_bulk for why that matters (atomicity)."""
    try:
        result = storage_optimizer.mark_placed_bulk(req.product_id, req.location_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    audit_service.log_action(
        current_user,
        "confirm_placement_bulk",
        "product",
        req.product_id,
        f"location_ids={req.location_ids}",
    )
    return result


@router.get("/locations/{location_id}")
def location_detail(location_id: int, current_user: CurrentUser = Depends(get_current_user)):
    """Powers the Store Layout Heatmap's click-to-inspect popup - see
    storage_optimizer.get_location_detail for what's real vs. backfilled in
    the returned product list."""
    try:
        result = storage_optimizer.get_location_detail(location_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Location not found")
    if current_user.role == "WAREHOUSE" and result["location"]["warehouse_id"] != current_user.warehouse_id:
        raise HTTPException(status_code=403, detail="Not your warehouse")
    return result


@router.get("/heatmap")
def heatmap(warehouse_id: Optional[int] = Query(None, ge=1, le=3), current_user: CurrentUser = Depends(get_current_user)):
    try:
        return storage_optimizer.get_heatmap(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overstocked")
def overstocked(
    threshold: float = 90,
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return storage_optimizer.get_overstocked(threshold, effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/underutilized")
def underutilized(
    threshold: float = 30,
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return storage_optimizer.get_underutilized(threshold, effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-movers")
def top_movers(
    limit: int = Query(20, ge=1, le=100),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Highest sales-velocity products, trailing 30 days - see
    storage_optimizer.get_top_movers. Powers the Stock Optimizer's "Top
    Movers" panel; each row can be checked against the Smart Placement
    Advisor (POST /optimizer/suggest with that product_id) to see
    velocity-aware placement scoring."""
    try:
        return storage_optimizer.get_top_movers(effective_warehouse_id(warehouse_id, current_user), limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggest")
def suggest(req: StorageSuggestRequest, current_user: CurrentUser = Depends(get_current_user)):
    try:
        req.warehouse_id = effective_warehouse_id(req.warehouse_id, current_user)
        return storage_optimizer.suggest_locations(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
