from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user
from app.models.schemas import DraftPurchaseOrderRequest
from app.services import stock_service

router = APIRouter(prefix="/stock", tags=["Stock Summary"])


@router.get("/summary")
def summary(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return stock_service.get_summary(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
def alerts(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return stock_service.get_alerts(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend")
def trend(
    days: int = Query(31, ge=7, le=365),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return stock_service.get_trend(days, effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/distribution")
def distribution(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return stock_service.get_distribution(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/low-stock")
def low_stock(
    limit: int = Query(20, ge=1, le=200),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return stock_service.get_low_stock(limit, effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reorder-suggestions")
def reorder_suggestions(
    limit: int = Query(50, ge=1, le=200),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Auto-suggested reorder quantity + best historical supplier for every
    LOW/CRITICAL product line. See stock_service.get_reorder_suggestions."""
    try:
        return stock_service.get_reorder_suggestions(
            limit, effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reorder-suggestions/draft-po")
def draft_po(req: DraftPurchaseOrderRequest, current_user: CurrentUser = Depends(get_current_user)):
    """One-click "Draft PO" from a Reorder Suggestions row - see
    stock_service.create_draft_po. Records intent only; doesn't place a
    real order with a supplier."""
    try:
        req.warehouse_id = effective_warehouse_id(req.warehouse_id, current_user)
        return stock_service.create_draft_po(req, current_user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/draft-pos")
def draft_pos(
    limit: int = Query(100, ge=1, le=500),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return stock_service.list_draft_pos(effective_warehouse_id(warehouse_id, current_user), limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rebalancing-suggestions")
def rebalancing_suggestions(
    limit: int = Query(50, ge=1, le=200),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cross-warehouse transfer suggestions - see
    stock_service.get_rebalancing_suggestions. A WAREHOUSE-role login only
    ever sees shortfalls in their own warehouse (effective_warehouse_id
    forces this); only ADMIN can see every warehouse's shortfalls at once."""
    try:
        return stock_service.get_rebalancing_suggestions(limit, effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dead-stock")
def dead_stock(
    limit: int = Query(50, ge=1, le=200),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Products with stock value tied up but ~0 recent sales - see
    stock_service.get_dead_stock."""
    try:
        return stock_service.get_dead_stock(effective_warehouse_id(warehouse_id, current_user), limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/margin-density")
def margin_density(
    limit: int = Query(50, ge=1, le=200),
    category: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Profit-per-cm3 product ranking - see stock_service.get_margin_density.
    Not warehouse-scoped: product economics (price/cost/dimensions) don't
    vary by warehouse in this catalog."""
    try:
        return stock_service.get_margin_density(limit, category)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
