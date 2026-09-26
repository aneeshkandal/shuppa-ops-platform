from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user
from app.models.schemas import DeliveryRiskRequest
from app.services import delivery_risk_service
from app.services.delivery_risk_service import ModelNotTrainedError

router = APIRouter(prefix="/delivery", tags=["Delivery Risk Predictor"])


@router.get("/kpis")
def kpis(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return delivery_risk_service.get_kpis(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except ModelNotTrainedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options")
def options(current_user: CurrentUser = Depends(get_current_user)):
    try:
        return delivery_risk_service.get_options(effective_warehouse_id(None, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/predict")
def predict(req: DeliveryRiskRequest, current_user: CurrentUser = Depends(get_current_user)):
    try:
        scoped = effective_warehouse_id(req.warehouse_id, current_user)
        if scoped is not None:
            req.warehouse_id = scoped
        return delivery_risk_service.predict(req)
    except ModelNotTrainedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/risky-orders")
def risky_orders(
    limit: int = Query(15, ge=1, le=100),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return delivery_risk_service.get_risky_orders(
            limit, effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
