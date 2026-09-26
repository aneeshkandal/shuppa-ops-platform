from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user
from app.services import supplier_service

router = APIRouter(prefix="/suppliers", tags=["Supplier Summary"])


@router.get("/kpis")
def kpis(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return supplier_service.get_kpis(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
def performance(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return supplier_service.get_performance(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend")
def trend(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return supplier_service.get_trend(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risk-distribution")
def risk_distribution(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return supplier_service.get_risk_distribution(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-by-value")
def top_by_value(
    limit: int = Query(5, ge=1, le=50),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return supplier_service.get_top_by_value(limit, effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent-late")
def recent_late(
    limit: int = Query(10, ge=1, le=100),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    supplier_id: Optional[int] = Query(None, description="Drill-down: only this supplier's late deliveries"),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return supplier_service.get_recent_late(
            limit, effective_warehouse_id(warehouse_id, current_user), date_from, date_to, supplier_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
