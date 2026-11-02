from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.planner import (
    SendChatMessageRequest,
    UpdatePersonalProfileRequest,
    chat_with_planner,
    clear_chat_history,
    get_chat_history,
    get_health_score,
    update_personal_profile,
)
from app.auth import get_current_user
from app.db import User, get_db

# Hidden legacy alias router so any older integrations calling /api/v1/cfp/* continue working seamlessly
router = APIRouter(prefix="/cfp", include_in_schema=False)


@router.get("/health-score")
def legacy_health_score(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_health_score(current_user=current_user, db=db)


@router.put("/personal-profile")
def legacy_update_profile(
    req: UpdatePersonalProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_personal_profile(req=req, current_user=current_user, db=db)


@router.get("/history")
def legacy_get_history(
    limit: int = 40,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_chat_history(limit=limit, current_user=current_user, db=db)


@router.delete("/history")
def legacy_clear_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return clear_chat_history(current_user=current_user, db=db)


@router.post("/chat")
async def legacy_chat(
    req: SendChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await chat_with_planner(req=req, current_user=current_user, db=db)
