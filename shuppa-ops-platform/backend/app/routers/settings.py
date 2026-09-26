from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, require_admin
from app.models.schemas import UpdateSettingsRequest
from app.services import alerts_service, audit_service, settings_service

router = APIRouter(prefix="/admin/settings", tags=["Settings"])


@router.get("")
def get_settings(current_user: CurrentUser = Depends(require_admin)):
    try:
        return settings_service.get_all_settings_detailed()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
def preview_settings(
    req: UpdateSettingsRequest,
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    current_user: CurrentUser = Depends(require_admin),
):
    """Shows how many alerts would fire under these proposed threshold
    values, without saving anything - lets Admin see the impact of a change
    before committing it."""
    try:
        return alerts_service.preview_settings_impact(
            req.settings, effective_warehouse_id(warehouse_id, current_user)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("")
def put_settings(req: UpdateSettingsRequest, current_user: CurrentUser = Depends(require_admin)):
    try:
        updated = settings_service.update_settings(req.settings)
        audit_service.log_action(
            current_user, "update_settings", "settings", None, ", ".join(req.settings.keys())
        )
        return updated
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
