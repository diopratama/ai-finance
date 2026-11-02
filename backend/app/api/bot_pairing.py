import random
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import BotLink, User, get_db
from app.auth import get_current_user

router = APIRouter(prefix="/bot", tags=["Bot Pairing"])


class GenerateCodeRequest(BaseModel):
    platform: str = "TELEGRAM"  # "TELEGRAM" or "WHATSAPP"


@router.post("/generate-code")
def generate_pairing_code(req: GenerateCodeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    platform = req.platform.upper()
    code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    link = db.query(BotLink).filter(BotLink.user_id == current_user.id, BotLink.platform == platform).first()
    if not link:
        link = BotLink(
            user_id=current_user.id,
            platform=platform,
            pairing_code=code,
            pairing_expires_at=expires_at,
            is_active=False,
        )
        db.add(link)
    else:
        link.pairing_code = code
        link.pairing_expires_at = expires_at

    db.commit()
    return {
        "platform": platform,
        "pairing_code": code,
        "expires_in_minutes": 15,
        "instruction": f"Buka bot Telegram/WhatsApp dan kirim pesan: /pair {code}",
    }


@router.get("/status")
def get_bot_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    links = db.query(BotLink).filter(BotLink.user_id == current_user.id).all()
    status_map = {
        "TELEGRAM": {"connected": False, "username": None},
        "WHATSAPP": {"connected": False, "username": None},
    }
    for l in links:
        if l.is_active:
            status_map[l.platform] = {
                "connected": True,
                "username": l.platform_username or l.platform_user_id,
            }
    return status_map


@router.delete("/unlink/{platform}")
def unlink_bot(platform: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    link = db.query(BotLink).filter(
        BotLink.user_id == current_user.id,
        BotLink.platform == platform.upper(),
    ).first()
    if link:
        link.is_active = False
        link.platform_user_id = None
        db.commit()
    return {"message": f"{platform} unlinked successfully"}

