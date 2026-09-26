from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, get_current_user
from app.services import search_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("")
def search(q: str = Query(min_length=1), current_user: CurrentUser = Depends(get_current_user)):
    try:
        return search_service.search(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
