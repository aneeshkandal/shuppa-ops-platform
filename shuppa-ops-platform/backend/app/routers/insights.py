from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user
from app.services import insights_service
from app.services.delivery_risk_service import ModelNotTrainedError

router = APIRouter(prefix="/insights", tags=["Key Business Insights"])

# Each route below mirrors the warehouse/date-filter shape its own page's
# other endpoints already use (see routers/stock.py, sales.py, suppliers.py,
# storage.py, delivery.py) so a page's Key Insights card reads the exact same
# scope its KPI row and charts do - never a different warehouse or period.


@router.get("/stock")
def stock_insights(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return insights_service.get_stock_insights(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sales")
def sales_insights(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return insights_service.get_sales_insights(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/supplier")
def supplier_insights(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return insights_service.get_supplier_insights(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage")
def storage_insights(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return insights_service.get_storage_insights(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/delivery")
def delivery_insights(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return insights_service.get_delivery_insights(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except ModelNotTrainedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
