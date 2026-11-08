import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import BotLink, Budget, Category, Transaction, User, Wallet, get_db
from app.api.budgets import compute_budget_spent_map, get_current_month_key
from app.services.nlu_parser import match_budget_item_from_text, parse_transaction_text
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
    """Helper to parse and save a transaction for a verified user, with smart Budget & Fund Location routing."""
    wallets = db.query(Wallet).filter(Wallet.user_id == user.id, Wallet.is_archived == False).all()
    wallet_names = [w.name for w in wallets]
    user_custom_cats = [
        c.name
        for c in db.query(Category).filter(Category.user_id == user.id, Category.is_system == False).all()
    ]

    parsed = parse_transaction_text(
        raw_text,
        user_wallets=wallet_names,
        custom_categories=user_custom_cats,
    )

    amount = parsed["amount"]
    if receipt_meta and "total_amount" in receipt_meta:
        amount = receipt_meta["total_amount"]

    if amount <= 0:
        return {
            "success": False,
            "message": (
                "⚠️ Nominal transaksi tidak terdeteksi.\n\n"
                "Contoh format yang bisa Anda kirimkan:\n"
                "• 'kopi susu 25rb bayar gopay'\n"
                "• 'makan siang 35.000 di warteg'\n"
                "• 'isi bensin 100rb'\n"
                "• 'gaji bulanan 12jt'"
            ),
            "parsed": parsed,
        }

    tx_type = parsed["type"]
    current_mk = get_current_month_key()
    matched_budget: Optional[Budget] = None
    if tx_type == "EXPENSE":
        active_budgets = (
            db.query(Budget)
            .filter(Budget.user_id == user.id, Budget.month_key == current_mk)
            .all()
        )
        matched_budget = match_budget_item_from_text(raw_text, active_budgets)

    # Match target wallet:
    # 1. Explicit wallet mentioned in chat text
    # 2. Matched budget's Fund Location wallet (if user didn't specify a wallet in chat)
    # 3. Default or first active wallet
    target_wallet = None
    if parsed["wallet_hint"]:
        for w in wallets:
            if parsed["wallet_hint"].lower() in w.name.lower() or w.name.lower() in parsed["wallet_hint"].lower():
                target_wallet = w
                break

    if not target_wallet and matched_budget and matched_budget.wallet_id:
        target_wallet = next((w for w in wallets if w.id == matched_budget.wallet_id), None)

    if not target_wallet:
        default_w = next((w for w in wallets if w.is_default), None)
        target_wallet = default_w or (wallets[0] if wallets else None)

    if not target_wallet:
        return {
            "success": False,
            "message": "⚠️ Tidak ada dompet/wallet aktif yang ditemukan. Silakan tambahkan dompet di menu Wallets di web dashboard: https://aifinance.fellow.my.id/wallets",
        }

    # Match Category (prefer custom/system match or matched_budget's category)
    category = None
    if matched_budget and matched_budget.category_id:
        category = db.query(Category).filter(Category.id == matched_budget.category_id).first()
    if not category:
        category = (
            db.query(Category)
            .filter(
                ((Category.is_system == True) | (Category.user_id == user.id)),
                Category.name.ilike(parsed["category_name"]),
            )
            .first()
        )
    if not category:
        category = db.query(Category).filter(Category.name == "Lain-lain").first()

    # Apply balance update
    if tx_type == "EXPENSE":
        target_wallet.balance -= amount
    elif tx_type == "INCOME":
        target_wallet.balance += amount

    tx = Transaction(
        user_id=user.id,
        wallet_id=target_wallet.id,
        category_id=category.id if category else None,
        budget_id=matched_budget.id if matched_budget else None,
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

    budget_line = ""
    matched_budget_payload = None
    if matched_budget:
        all_tx = db.query(Transaction).filter(Transaction.user_id == user.id).all()
        spent_map = compute_budget_spent_map([matched_budget], all_tx, current_mk)
        spent_now = spent_map.get(matched_budget.id, 0.0)
        rem_now = max(0.0, matched_budget.limit_amount - spent_now)
        rem_fmt = f"Rp {int(round(rem_now)):,}".replace(",", ".")
        b_label = matched_budget.name or "Pos Anggaran"
        budget_line = f"• Pos Anggaran: {b_label} (Sisa bulan ini: {rem_fmt})\n"
        matched_budget_payload = {
            "id": matched_budget.id,
            "name": b_label,
            "group_type": matched_budget.group_type,
            "remaining_amount": round(rem_now, 2),
        }

    action_label = "Pengeluaran" if tx_type == "EXPENSE" else "Pemasukan"
    action_symbol = "💸" if tx_type == "EXPENSE" else "💰"
    formatted_amount = f"Rp {int(amount):,}".replace(",", ".")
    rem_wallet_fmt = f"Rp {int(round(target_wallet.balance)):,}".replace(",", ".")

    reply_msg = (
        f"{action_symbol} {action_label} Berhasil Dicatat!\n"
        f"• Nominal: {formatted_amount} ({parsed['currency']})\n"
        f"• Kategori: {category.name if category else 'Lain-lain'}\n"
        f"{budget_line}"
        f"• Dompet: {target_wallet.name} (Sisa Saldo: {rem_wallet_fmt})\n"
        f"• Deskripsi: {parsed['description']}"
    )

    return {
        "success": True,
        "message": reply_msg,
        "transaction_id": tx.id,
        "parsed": parsed,
        "matched_budget": matched_budget_payload,
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


async def _send_telegram_reply(chat_id: str, reply_msg: str) -> Dict[str, Any]:
    """Sends reply directly via Telegram Bot API HTTP if token is available, and returns method payload."""
    if settings.TELEGRAM_BOT_TOKEN and chat_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": reply_msg},
                )
                if res.status_code != 200:
                    logger.warning("Telegram direct sendMessage returned %s: %s", res.status_code, res.text)
        except Exception as exc:
            logger.error("Failed to send direct telegram reply: %s", exc)

    return {
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": reply_msg,
        "ok": True,
        "reply": reply_msg,
    }


@router.post("/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Receives Telegram Bot webhook updates."""
    chat_id = ""
    try:
        body = await request.json()
        message = body.get("message") or body.get("edited_message") or {}
        chat = message.get("chat", {})
        chat_id = str(chat.get("id")) if chat.get("id") is not None else ""
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
                    return await _send_telegram_reply(
                        chat_id,
                        "✅ Akun Telegram Anda berhasil dihubungkan ke AI-Finance!\n\n"
                        "Anda sekarang bisa langsung mencatat transaksi, misal:\n"
                        "• makan siang 35rb di warteg\n"
                        "• isi bensin 250rb\n"
                        "• gaji bulanan 10jt\n\n"
                        "Ketik /summary atau /laporan untuk cek ringkasan saldo."
                    )
            return await _send_telegram_reply(
                chat_id,
                "❌ Kode pairing tidak valid atau telah kedaluwarsa. Silakan generate kode baru di web dashboard: https://aifinance.fellow.my.id/bot-pairing"
            )

        # Find linked user
        bot_link = db.query(BotLink).filter(
            BotLink.platform == "TELEGRAM",
            BotLink.platform_user_id == chat_id,
            BotLink.is_active == True,
        ).first()

        if not bot_link:
            return await _send_telegram_reply(
                chat_id,
                "Halo! Selamat datang di AI-Finance Bot 🤖\n\n"
                "Akun Telegram Anda belum terhubung. Silakan lakukan pairing terlebih dahulu:\n"
                "1. Buka dashboard: https://aifinance.fellow.my.id/bot-pairing\n"
                "2. Klik 'Generate Code' pada kartu Telegram\n"
                "3. Kirim pesan ke bot ini: /pair <kode>\n\n"
                "Contoh: /pair 123456"
            )

        # Check for /summary command
        if text in ("/summary", "/laporan"):
            user = bot_link.user
            transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
            total_exp = sum(t.amount_in_base for t in transactions if t.type == "EXPENSE")
            total_inc = sum(t.amount_in_base for t in transactions if t.type == "INCOME")
            summary_msg = (
                f"📊 Ringkasan Finansial Anda\n"
                f"• Total Pemasukan: Rp {int(total_inc):,}\n"
                f"• Total Pengeluaran: Rp {int(total_exp):,}\n"
                f"• Saldo Bersih: Rp {int(total_inc - total_exp):,}"
            ).replace(",", ".")
            return await _send_telegram_reply(chat_id, summary_msg)

        if text in ("/help", "/bantuan"):
            help_msg = (
                "💡 Panduan Penggunaan AI-Finance Bot:\n\n"
                "• Catat Pengeluaran: Cukup ketik seperti chat biasa:\n"
                "  - 'kopi susu 25rb bayar gopay'\n"
                "  - 'beli belanja bulanan 450.000'\n"
                "• Catat Pemasukan:\n"
                "  - 'gaji bulan ini 15jt'\n"
                "  - 'freelance project 2.5jt'\n"
                "• Cek Ringkasan: Ketik /summary atau /laporan"
            )
            return await _send_telegram_reply(chat_id, help_msg)

        # Process natural language expense
        result = _process_user_transaction_message(
            user=bot_link.user,
            raw_text=text,
            source="TELEGRAM",
            receipt_meta=None,
            db=db,
        )
        return await _send_telegram_reply(chat_id, result["message"])

    except Exception as e:
        logger.error("Telegram webhook error: %s", e)
        err_msg = f"⚠️ Terjadi kesalahan saat memproses transaksi: {str(e)}"
        if chat_id:
            await _send_telegram_reply(chat_id, err_msg)
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

