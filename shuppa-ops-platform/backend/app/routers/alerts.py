from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user, require_admin
from app.models.schemas import ResolveAlertRequest, RollbackAlertRequest
from app.services import alerts_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("")
def all_alerts(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return alerts_service.get_all_alerts(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resolve")
def resolve_alert(req: ResolveAlertRequest, current_user: CurrentUser = Depends(require_admin)):
    """Admin-only, matching this app's one other "resolve" precedent
    (Supplier Returns' resolve_item) even though the Alerts Center page
    itself is open to every authenticated user."""
    try:
        warehouse_id = effective_warehouse_id(req.warehouse_id, current_user)
        return alerts_service.resolve_alert(req.title, warehouse_id, req.count, current_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resolved")
def resolved_alerts(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(require_admin),
):
    """Admin-only, same as resolve/rollback - the Resolved tab (and undoing
    anything in it) is only meaningful for the people who can act on it."""
    try:
        return alerts_service.get_resolved_alerts(effective_warehouse_id(warehouse_id, current_user))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback")
def rollback_alert(req: RollbackAlertRequest, current_user: CurrentUser = Depends(require_admin)):
    """Undo an earlier resolve - e.g. an admin resolved the wrong alert by
    mistake. Admin-only, same as resolve."""
    try:
        warehouse_id = effective_warehouse_id(req.warehouse_id, current_user)
        return alerts_service.rollback_alert(req.title, warehouse_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
