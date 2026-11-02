import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import BotLink, Category, Transaction, User, Wallet, get_db
from app.services.nlu_parser import parse_transaction_text
from app.services.router_service import router_service
from app.auth import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks & Bot Drivers"])


class SimulateChatRequest(BaseModel):
    message: str
    source: str = "TELEGRAM"  # TELEGRAM | WHATSAPP | VOICE | RECEIPT
    receipt_data: Optional[Dict[str, Any]] = None


def _process_user_transaction_message(
    user: User,
    raw_text: str,
    source: str,
    receipt_meta: Optional[Dict[str, Any]],
    db: Session,
) -> Dict[str, Any]:
    """Helper to parse and save a transaction for a verified user."""
    # Fetch user wallet names for entity hints
    wallets = db.query(Wallet).filter(Wallet.user_id == user.id, Wallet.is_archived == False).all()
    wallet_names = [w.name for w in wallets]

    parsed = parse_transaction_text(raw_text, user_wallets=wallet_names)

    # Determine amount (if receipt provided, use receipt total)
    amount = parsed["amount"]
    if receipt_meta and "total_amount" in receipt_meta:
        amount = receipt_meta["total_amount"]

    if amount <= 0:
        return {
            "success": False,
            "message": "Nominal tidak terdeteksi. Silakan sebutkan nominal (contoh: 'kopi 25rb pake gopay' atau 'gaji 10jt')",
            "parsed": parsed,
        }

    # Match target wallet
    target_wallet = None
    if parsed["wallet_hint"]:
        for w in wallets:
            if parsed["wallet_hint"].lower() in w.name.lower():
                target_wallet = w
                break

    if not target_wallet:
        # Fallback to default or first wallet
        default_w = next((w for w in wallets if w.is_default), None)
        target_wallet = default_w or (wallets[0] if wallets else None)

    if not target_wallet:
        return {
            "success": False,
            "message": "Anda belum memiliki wallet aktif. Silakan buat wallet terlebih dahulu di dashboard web.",
        }

    # Match Category
    category = db.query(Category).filter(Category.name == parsed["category_name"]).first()
    if not category:
        category = db.query(Category).filter(Category.name == "Lain-lain").first()

    # Apply balance update
    tx_type = parsed["type"]
    if tx_type == "EXPENSE":
        target_wallet.balance -= amount
    elif tx_type == "INCOME":
        target_wallet.balance += amount

    tx = Transaction(
        user_id=user.id,
        wallet_id=target_wallet.id,
        category_id=category.id if category else None,
        type=tx_type,
        amount=amount,
        currency=parsed["currency"],
        amount_in_base=amount,
        description=parsed["description"],
        merchant=receipt_meta.get("merchant") if receipt_meta else None,
        raw_source=source,
        raw_input=raw_text,
        receipt_metadata=json.dumps(receipt_meta) if receipt_meta else None,
        transaction_date=datetime.now(timezone.utc),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)

    action_symbol = "💸" if tx_type == "EXPENSE" else "💰"
    formatted_amount = f"Rp {int(amount):,}".replace(",", ".")
    reply_msg = (
        f"{action_symbol} **{tx_type.title()} Berhasil Dicatat!**\n"
        f"• **Nominal:** {formatted_amount} ({parsed['currency']})\n"
        f"• **Kategori:** {category.name if category else 'Lain-lain'}\n"
        f"• **Dompet:** {target_wallet.name} (Sisa Saldo: Rp {int(target_wallet.balance):,}".replace(",", ".") + ")\n"
        f"• **Deskripsi:** {parsed['description']}"
    )

    return {
        "success": True,
        "message": reply_msg,
        "transaction_id": tx.id,
        "parsed": parsed,
        "wallet": {"id": target_wallet.id, "name": target_wallet.name, "balance": target_wallet.balance},
    }


@router.post("/simulate-chat")
def simulate_chat_message(
    req: SimulateChatRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Allows simulating chat-based transaction logging directly from UI or tests."""
    user = current_user
    if not user:
        # Fallback to initial admin user if not logged in
        user = db.query(User).first()
        if not user:
            raise HTTPException(status_code=400, detail="No user found to process transaction")

    return _process_user_transaction_message(
        user=user,
        raw_text=req.message,
        source=req.source,
        receipt_meta=req.receipt_data,
        db=db,
    )


@router.post("/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives Telegram Bot webhook updates."""
    try:
        body = await request.json()
        message = body.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id"))
        text = message.get("text", "").strip()

        if not chat_id:
            return {"ok": True}

        # Check for pairing command: /pair 123456
        if text.startswith("/pair"):
            parts = text.split()
            if len(parts) >= 2:
                code = parts[1].strip()
                bot_link = db.query(BotLink).filter(
                    BotLink.platform == "TELEGRAM",
                    BotLink.pairing_code == code,
                    BotLink.pairing_expires_at > datetime.now(timezone.utc),
                ).first()
                if bot_link:
                    bot_link.is_active = True
                    bot_link.platform_user_id = chat_id
                    bot_link.platform_username = message.get("from", {}).get("username")
                    bot_link.pairing_code = None
                    db.commit()
                    return {"ok": True, "reply": "✅ Akun Telegram Anda berhasil dihubungkan ke AI-Finance!"}
            return {"ok": True, "reply": "❌ Kode pairing tidak valid atau telah kedaluwarsa."}

        # Find linked user
        bot_link = db.query(BotLink).filter(
            BotLink.platform == "TELEGRAM",
            BotLink.platform_user_id == chat_id,
            BotLink.is_active == True,
        ).first()

        if not bot_link:
            return {
                "ok": True,
                "reply": "Halo! Silakan hubungkan akun Telegram Anda terlebih dahulu melalui menu Integrasi Chatbot di web dashboard.",
            }

        # Check for /summary command
        if text == "/summary" or text == "/laporan":
            user = bot_link.user
            transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
            total_exp = sum(t.amount_in_base for t in transactions if t.type == "EXPENSE")
            total_inc = sum(t.amount_in_base for t in transactions if t.type == "INCOME")
            summary_msg = (
                f"📊 **Ringkasan Finansial Anda**\n"
                f"• Total Pemasukan: Rp {int(total_inc):,}\n"
                f"• Total Pengeluaran: Rp {int(total_exp):,}\n"
                f"• Saldo Bersih: Rp {int(total_inc - total_exp):,}\n"
            ).replace(",", ".")
            return {"ok": True, "reply": summary_msg}

        # Process natural language expense
        result = _process_user_transaction_message(
            user=bot_link.user,
            raw_text=text,
            source="TELEGRAM",
            receipt_meta=None,
            db=db,
        )
        return {"ok": True, "reply": result["message"]}

    except Exception as e:
        logger.error("Telegram webhook error: %s", e)
        return {"ok": True, "error": str(e)}


@router.get("/whatsapp")
def whatsapp_verify_webhook(request: Request):
    """Handles Meta WhatsApp Webhook Challenge verification."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    """Handles incoming WhatsApp Cloud API messages."""
    try:
        body = await request.json()
        logger.info("WhatsApp payload received: %s", body)
        return {"status": "received"}
    except Exception as e:
        logger.error("WhatsApp webhook error: %s", e)
        return {"status": "error"}

