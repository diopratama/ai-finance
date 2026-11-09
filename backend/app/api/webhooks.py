import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import (
    BotLink,
    Budget,
    Category,
    Transaction,
    User,
    Wallet,
    get_db,
    get_accessible_wallets,
    get_wallet_role,
)
from app.api.budgets import compute_budget_spent_map, get_current_month_key
from app.api.transactions import get_transaction_summary
from app.api.wallets import _build_user_portfolio_review
from app.api.planner import ask_planner_direct
from app.services.fire_engine import ASSET_CLASS_LABELS, infer_wallet_asset_class
from app.services.market_rates_service import (
    fetch_live_market_rates,
    convert_to_idr,
    convert_between_currencies,
    format_currency_with_base,
    format_currency_display_string,
)
from app.services.nlu_parser import match_budget_item_from_text, parse_transaction_text
from app.services.router_service import router_service
from app.auth import get_optional_user, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks & Bot Drivers"])


class SimulateChatRequest(BaseModel):
    message: str
    source: str = "TELEGRAM"  # TELEGRAM | WHATSAPP | VOICE | RECEIPT
    receipt_data: Optional[Dict[str, Any]] = None


def _fmt_rp(val: float) -> str:
    return f"Rp {int(round(val)):,}".replace(",", ".")


def _format_bot_wallets_reply(user: User, db: Session) -> str:
    wallets = get_accessible_wallets(db, user.id, min_role="VIEWER")
    if not wallets:
        return (
            "⚠️ Anda belum memiliki dompet aktif.\n"
            "Silakan tambahkan dompet di web dashboard: https://aifinance.fellow.my.id/wallets"
        )
    rates = fetch_live_market_rates()
    total_balance = sum(convert_to_idr(w.balance, getattr(w, "currency", "IDR"), rates) for w in wallets)
    lines = ["💳 Saldo Dompet & Rekening Anda:\n"]
    for w in wallets:
        curr = (getattr(w, "currency", None) or "IDR").upper()
        ac = infer_wallet_asset_class(w.name, w.type, getattr(w, "asset_class", None))
        icon = "🪙" if (curr in ("GRAM", "XAU") or ac == "GOLD") else ("📈" if ac else ("💵" if w.type == "CASH" else ("🏦" if w.type == "BANK" else ("📱" if w.type == "EWALLET" else "💳"))))
        badges = []
        if w.is_default:
            badges.append("Utama")
        if w.user_id != user.id:
            badges.append("Bersama")
        if ac:
            badges.append(ASSET_CLASS_LABELS.get(ac, "Investasi"))
        badge_str = f" ({', '.join(badges)})" if badges else ""
        if curr in ("GRAM", "XAU"):
            idr_val = convert_to_idr(w.balance, curr, rates)
            lines.append(f"• {icon} {w.name}{badge_str}: {w.balance:g} gram (≈ {_fmt_rp(idr_val)})")
        elif curr == "USD":
            idr_val = convert_to_idr(w.balance, curr, rates)
            lines.append(f"• {icon} {w.name}{badge_str}: ${w.balance:,.2f} (≈ {_fmt_rp(idr_val)})")
        else:
            lines.append(f"• {icon} {w.name}{badge_str}: {_fmt_rp(w.balance)}")

    usd_rate = rates.get("usd_to_idr") or rates.get("usd_idr") or 16850.0
    gold_rate = rates.get("gold_per_gram_idr") or rates.get("gold_idr_per_gram") or 2539000.0
    lines.append(f"\n💰 Total Saldo Tersedia (Setara IDR): {_fmt_rp(total_balance)}")
    lines.append(f"📈 Kurs Live: 1 USD ≈ {_fmt_rp(usd_rate)} | 1 gr Emas ≈ {_fmt_rp(gold_rate)}")
    return "\n".join(lines)


def _format_bot_monthly_report_reply(user: User, db: Session) -> str:
    summary = get_transaction_summary(month=None, current_user=user, db=db)
    m = summary["monthly"]
    mom_inc = f"+{m['income_mom_pct']}%" if m["income_mom_pct"] >= 0 else f"{m['income_mom_pct']}%"
    mom_exp = f"+{m['expense_mom_pct']}%" if m["expense_mom_pct"] >= 0 else f"{m['expense_mom_pct']}%"

    lines = [
        f"📊 Laporan Bulanan ({m['month_label']})\n",
        f"• Pemasukan: {_fmt_rp(m['income'])} ({mom_inc} vs bln lalu)",
        f"• Pengeluaran: {_fmt_rp(m['expense'])} ({mom_exp} vs bln lalu)",
        f"• Arus Kas Bersih: {_fmt_rp(m['net_cashflow'])}",
        f"• Rasio Tabungan (Savings Rate): {m['savings_rate']}%",
        f"• Total Transaksi: {m['tx_count']} transaksi",
    ]

    top_cats = summary.get("expense_categories", [])[:3]
    if top_cats:
        lines.append("\n🏷️ Top Kategori Pengeluaran:")
        for c in top_cats:
            lines.append(f"  - {c['name']}: {_fmt_rp(c['total'])} ({c['percentage']}%)")

    return "\n".join(lines)


def _format_bot_portfolio_review_reply(user: User, db: Session) -> str:
    wallets = get_accessible_wallets(db, user.id, min_role="VIEWER")
    rev = _build_user_portfolio_review(user, wallets, db)

    if not rev["has_investment_wallets"]:
        return (
            "📈 Review Portofolio Investasi\n\n"
            "Anda belum memiliki dompet bertipe Investasi (INVESTMENT / RDN / Saham / Emas / SBN).\n"
            f"Referensi profil {rev['reference_profile_name']} menyarankan alokasi dengan estimasi CAGR {rev['expected_cagr']}."
        )

    lines = [
        f"📈 Review Portofolio Investasi ({rev['reference_profile_name']})\n",
        f"• Total Portofolio Investasi: {_fmt_rp(rev['total_investment_balance'])} ({rev['invested_ratio_pct']}% dari Kekayaan Bersih)",
        f"• Skor Kesesuaian Best Practice: {rev['alignment_score']}/100 ({rev['status_label']})",
        "\n🎯 Perbandingan Alokasi Aktual vs Target:",
    ]
    for comp in rev["allocations_comparison"]:
        lines.append(
            f"  - {comp['asset_class_label']}: Aktual {comp['actual_pct']}% ({_fmt_rp(comp['actual_amount'])}) vs Target {comp['target_pct']}% -> {comp['status_text']}"
        )

    if rev["recommendations"]:
        lines.append("\n💡 Rekomendasi Rebalancing & Best Practice:")
        for r in rev["recommendations"][:3]:
            lines.append(f"  • {r}")

    return "\n".join(lines)


def _run_coro_sync(coro):
    """Executes an async coroutine synchronously, whether or not an event loop is currently running."""
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def _process_user_transaction_message(
    user: User,
    raw_text: str,
    source: str,
    receipt_meta: Optional[Dict[str, Any]],
    db: Session,
    bot_link: Optional[BotLink] = None,
) -> Dict[str, Any]:
    """Helper to parse and save a transaction for a verified user, with smart Budget & Fund Location routing."""
    clean_cmd = (raw_text or "").strip()
    lower_cmd = clean_cmd.lower()

    # Handle exit/selesai from interactive AI Planner mode
    if clean_cmd in ("/selesai", "/exit", "/catat", "/transaksi", "/kembali"):
        if bot_link:
            bot_link.chat_mode = "TRANSACTION"
            db.commit()
        return {
            "success": True,
            "command": "EXIT_PLANNER",
            "message": (
                "✅ Selesai konsultasi AI.\n\n"
                "Anda telah kembali ke mode pencatatan transaksi otomatis.\n"
                "Kirim pesan nominal pengeluaran atau struk kapan saja, atau ketik /finplanner untuk berdiskusi dengan AI lagi."
            ),
        }

    # Handle /finplanner command (one-shot or enter interactive mode)
    if clean_cmd.startswith("/finplanner") or clean_cmd.startswith("/tanya") or clean_cmd.startswith("/ai"):
        parts = clean_cmd.split(maxsplit=1)
        if len(parts) > 1 and parts[1].strip():
            # One-shot query to AI Financial Planner with internet access
            question = parts[1].strip()
            ai_reply = _run_coro_sync(ask_planner_direct(user, question, db))
            return {
                "success": True,
                "command": "FINPLANNER_QUERY",
                "message": f"🤖 AI Financial Planner (Real-Time Web):\n\n{ai_reply}",
            }
        else:
            # Toggle into interactive AI chat mode
            if bot_link:
                bot_link.chat_mode = "PLANNER"
                db.commit()
            return {
                "success": True,
                "command": "ENTER_PLANNER",
                "message": (
                    "🧠 Mode Diskusi AI Financial Planner Aktif!\n\n"
                    "Anda sekarang terhubung langsung dengan AI Financial Planner (didukung pencarian internet terkini untuk data emas, kurs USD, IHSG, SBN/ORI, inflasi & regulasi pajak).\n\n"
                    "Silakan ketik pertanyaan Anda seputar alokasi keuangan, portofolio, atau strategi FIRE.\n\n"
                    "💡 Ketik /selesai untuk keluar dan kembali ke mode catat transaksi otomatis."
                ),
            }

    # If the user is currently in interactive PLANNER mode, route to AI directly
    if bot_link and getattr(bot_link, "chat_mode", "TRANSACTION") == "PLANNER":
        # Don't hijack system commands
        if clean_cmd not in ("/saldo", "/laporan", "/portofolio", "/help"):
            ai_reply = _run_coro_sync(ask_planner_direct(user, raw_text, db))
            return {
                "success": True,
                "command": "PLANNER_CHAT",
                "message": f"{ai_reply}\n\n────────────────\n💬 Ketik /selesai untuk kembali ke mode catat transaksi.",
            }

    # Check if message is a query command (/saldo, /laporan, /portofolio, /help)
    if clean_cmd in ("/saldo", "/dompet", "/wallets") or (
        not any(ch.isdigit() for ch in lower_cmd)
        and any(k in lower_cmd for k in ("cek saldo", "saldo saya", "lihat saldo", "total saldo", "sisa saldo", "cek dompet"))
    ):
        msg = _format_bot_wallets_reply(user, db)
        return {"success": True, "command": "SALDO", "message": msg}

    if clean_cmd in ("/summary", "/laporan", "/report") or (
        not any(ch.isdigit() for ch in lower_cmd)
        and any(k in lower_cmd for k in ("cek laporan", "laporan bulanan", "ringkasan bulan", "rekap bulanan", "summary bulan"))
    ):
        msg = _format_bot_monthly_report_reply(user, db)
        return {"success": True, "command": "LAPORAN", "message": msg}

    if clean_cmd in ("/portofolio", "/portfolio", "/investasi") or (
        not any(ch.isdigit() for ch in lower_cmd)
        and any(k in lower_cmd for k in ("review portofolio", "cek portofolio", "review investasi", "cek investasi", "evaluasi portofolio"))
    ):
        msg = _format_bot_portfolio_review_reply(user, db)
        return {"success": True, "command": "PORTOFOLIO", "message": msg}

    if clean_cmd in ("/help", "/bantuan"):
        help_msg = (
            "💡 Panduan Penggunaan AI-Finance Bot:\n\n"
            "• Tambah Dana ke Dompet Apapun:\n"
            "  - 'tambah saldo bca 500rb'\n"
            "  - 'beli emas 2 gram'\n"
            "  - 'topup 50 usd'\n"
            "  - 'topup gopay 250rb'\n\n"
            "• Kurangi Dana / Catat Pengeluaran:\n"
            "  - 'kopi susu 25rb bayar gopay'\n"
            "  - 'jual emas 1 gram'\n"
            "  - 'belanja $15 dari dompet usd'\n\n"
            "• Transfer Antar Semua Dompet:\n"
            "  - 'transfer 500rb dari mandiri ke jago'\n"
            "  - 'topup gopay 100rb dari bca'\n\n"
            "• Diskusi AI Financial Planner:\n"
            "  - /finplanner <pertanyaan> : Tanya langsung ke AI\n"
            "  - /finplanner : Masuk mode konsultasi AI santai\n"
            "  - /selesai : Keluar dari mode konsultasi AI\n\n"
            "• Perintah Ringkasan:\n"
            "  - /saldo : Cek saldo semua dompet (termasuk USD & Emas live)\n"
            "  - /laporan : Cek ringkasan pemasukan & pengeluaran bulanan\n"
            "  - /portofolio : Review portofolio investasi vs best practice"
        )
        return {"success": True, "command": "HELP", "message": help_msg}

    wallets = get_accessible_wallets(db, user.id, min_role="EDITOR")
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
                "• 'beli emas 2.5 gram'\n"
                "• 'topup gopay 100rb dari bca'\n"
                "• 'transfer 500rb dari mandiri ke jago'\n"
                "• 'isi bensin 100rb'\n"
                "• 'gaji bulanan 12jt'\n"
                "• /finplanner untuk berdiskusi dengan AI"
            ),
            "parsed": parsed,
        }

    tx_type = parsed["type"]
    rates = fetch_live_market_rates()

    # Handle TRANSFER transaction
    if tx_type == "TRANSFER":
        source_wallet = None
        target_wallet = None

        # Resolve source wallet
        src_hint = parsed.get("source_wallet_hint")
        if src_hint:
            for w in wallets:
                if src_hint.lower() in w.name.lower() or w.name.lower() in src_hint.lower():
                    source_wallet = w
                    break

        # Resolve target wallet
        target_hint = parsed.get("target_wallet_hint") or parsed.get("wallet_hint")
        if target_hint:
            for w in wallets:
                if target_hint.lower() in w.name.lower() or w.name.lower() in target_hint.lower():
                    target_wallet = w
                    break

        if not target_wallet:
            return {
                "success": False,
                "message": f"⚠️ Dompet tujuan{f' ({target_hint})' if target_hint else ''} tidak ditemukan di akun Anda. Pastikan nama dompet sesuai.",
            }

        if not source_wallet:
            # Fallback: choose default wallet or first wallet different from target
            default_w = next((w for w in wallets if w.is_default and w.id != target_wallet.id), None)
            source_wallet = default_w or next((w for w in wallets if w.id != target_wallet.id), None)

        if not source_wallet:
            return {
                "success": False,
                "message": f"⚠️ Dompet sumber{f' ({src_hint})' if src_hint else ''} tidak ditemukan di akun Anda.",
            }

        if source_wallet.id == target_wallet.id:
            return {
                "success": False,
                "message": "⚠️ Dompet sumber dan dompet tujuan transfer sama.",
            }

        w_curr = (getattr(source_wallet, "currency", None) or "IDR").upper()
        target_curr = (getattr(target_wallet, "currency", None) or "IDR").upper()
        amount_in_base = convert_to_idr(amount, w_curr, rates)
        received_amount = convert_between_currencies(amount, w_curr, target_curr, rates)

        source_wallet.balance -= amount
        target_wallet.balance += received_amount

        tx = Transaction(
            user_id=user.id,
            wallet_id=source_wallet.id,
            to_wallet_id=target_wallet.id,
            type="TRANSFER",
            amount=amount,
            currency=source_wallet.currency,
            amount_in_base=amount_in_base,
            description=parsed["description"] or f"Transfer dari {source_wallet.name} ke {target_wallet.name}",
            merchant=receipt_meta.get("merchant") if receipt_meta else None,
            raw_source=source,
            raw_input=raw_text,
            receipt_metadata=json.dumps(receipt_meta) if receipt_meta else None,
            transaction_date=datetime.now(timezone.utc),
        )
        db.add(tx)
        db.commit()
        db.refresh(tx)

        formatted_amount = format_currency_display_string(amount, source_wallet.currency)
        src_bal_fmt = format_currency_display_string(source_wallet.balance, source_wallet.currency)
        dest_bal_fmt = format_currency_display_string(target_wallet.balance, target_wallet.currency)

        reply_msg = (
            f"🔄 Transfer Berhasil Dicatat!\n"
            f"• Nominal: {formatted_amount}\n"
            f"• Dari Dompet: {source_wallet.name} (Sisa Saldo: {src_bal_fmt})\n"
            f"• Ke Dompet: {target_wallet.name} (Sisa Saldo: {dest_bal_fmt})\n"
            f"• Deskripsi: {tx.description}"
        )

        return {
            "success": True,
            "message": reply_msg,
            "transaction_id": tx.id,
            "parsed": parsed,
            "source_wallet": {"id": source_wallet.id, "name": source_wallet.name, "balance": source_wallet.balance},
            "target_wallet": {"id": target_wallet.id, "name": target_wallet.name, "balance": target_wallet.balance},
        }

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
    elif tx_type in ("INCOME", "TOPUP"):
        target_wallet.balance += amount

    w_curr = (getattr(target_wallet, "currency", None) or parsed["currency"] or "IDR").upper()
    amount_in_base = convert_to_idr(amount, w_curr, rates)

    tx = Transaction(
        user_id=user.id,
        wallet_id=target_wallet.id,
        category_id=category.id if category else None,
        budget_id=matched_budget.id if matched_budget else None,
        type=tx_type,
        amount=amount,
        currency=w_curr,
        amount_in_base=amount_in_base,
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

    is_topup_text = any(k in raw_text.lower() for k in ("topup", "top up", "isi saldo", "isi dompet", "isi gopay", "isi ovo", "tambah saldo", "beli emas"))
    if is_topup_text:
        action_label = "Top Up / Pemasukan"
        action_symbol = "💰"
    else:
        action_label = "Pengeluaran" if tx_type == "EXPENSE" else "Pemasukan"
        action_symbol = "💸" if tx_type == "EXPENSE" else "💰"

    formatted_amount = format_currency_display_string(amount, w_curr)
    rem_wallet_fmt = format_currency_display_string(target_wallet.balance, target_wallet.currency)

    reply_msg = (
        f"{action_symbol} {action_label} Berhasil Dicatat!\n"
        f"• Nominal: {formatted_amount}\n"
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
async def simulate_chat_message(
    req: SimulateChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allows simulating chat-based transaction logging directly from UI or tests."""
    return _process_user_transaction_message(
        user=current_user,
        raw_text=req.message,
        source=req.source,
        receipt_meta=req.receipt_data,
        db=db,
    )


async def setup_telegram_bot_commands() -> bool:
    """Registers official slash commands in the Telegram chat menu ([/] button)."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return False
    commands = [
        {"command": "saldo", "description": "Cek saldo semua dompet (IDR, USD, Emas)"},
        {"command": "laporan", "description": "Laporan pemasukan & pengeluaran bulanan"},
        {"command": "portofolio", "description": "Review portofolio investasi vs best practice"},
        {"command": "finplanner", "description": "Konsultasi AI Financial Planner (Real-Time Web)"},
        {"command": "selesai", "description": "Keluar dari mode AI ke catat transaksi"},
        {"command": "help", "description": "Panduan perintah & contoh pencatatan"},
    ]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setMyCommands",
                json={"commands": commands},
            )
            return res.status_code == 200
    except Exception as exc:
        logger.warning("Could not set Telegram bot commands: %s", exc)
        return False


async def _send_telegram_reply(chat_id: str, reply_msg: str) -> Dict[str, Any]:
    """Sends reply directly via Telegram Bot API HTTP if token is available, and returns method payload."""
    sent_via_api = False
    if settings.TELEGRAM_BOT_TOKEN and chat_id:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": reply_msg},
                )
                if res.status_code == 200:
                    sent_via_api = True
                else:
                    logger.warning("Telegram direct sendMessage returned %s: %s", res.status_code, res.text)
        except Exception as exc:
            logger.error("Failed to send direct telegram reply: %s", exc)

    if sent_via_api:
        # Avoid duplicate message: already delivered directly via Telegram Bot API HTTP
        return {
            "ok": True,
            "reply": reply_msg,
        }

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
                    # Setup bot menu commands on first pairing
                    try:
                        await setup_telegram_bot_commands()
                    except Exception:
                        pass
                    return await _send_telegram_reply(
                        chat_id,
                        "✅ Akun Telegram Anda berhasil dihubungkan ke AI-Finance!\n\n"
                        "Anda sekarang bisa langsung mencatat transaksi, misal:\n"
                        "• makan siang 35rb di warteg\n"
                        "• beli emas 2.5 gram\n"
                        "• topup 50 usd\n"
                        "• transfer bca ke bibit 1jt\n\n"
                        "💡 Ketik /finplanner untuk berdiskusi dengan AI Financial Planner, atau /saldo untuk cek saldo dompet."
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

        # Process natural language command or transaction
        result = _process_user_transaction_message(
            user=bot_link.user,
            raw_text=text,
            source="TELEGRAM",
            receipt_meta=None,
            db=db,
            bot_link=bot_link,
        )
        return await _send_telegram_reply(chat_id, result["message"])

    except Exception as e:
        logger.error("Telegram webhook error: %s", e)
        err_msg = f"⚠️ Terjadi kesalahan saat memproses pesan: {str(e)}"
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

        # Extract WhatsApp text & sender if standard Cloud API format or direct payload
        sender_id = body.get("from")
        text = body.get("text")
        if isinstance(text, dict):
            text = text.get("body", "")

        if not sender_id and "entry" in body:
            for entry in body.get("entry", []):
                for change in entry.get("changes", []):
                    val = change.get("value", {})
                    msgs = val.get("messages", [])
                    if msgs:
                        sender_id = str(msgs[0].get("from", ""))
                        text = msgs[0].get("text", {}).get("body", "")
                        break

        if sender_id and text:
            bot_link = db.query(BotLink).filter(
                BotLink.platform == "WHATSAPP",
                BotLink.platform_user_id == str(sender_id),
                BotLink.is_active == True,
            ).first()
            if bot_link:
                res = _process_user_transaction_message(
                    user=bot_link.user,
                    raw_text=str(text).strip(),
                    source="WHATSAPP",
                    receipt_meta=None,
                    db=db,
                    bot_link=bot_link,
                )
                return {"status": "processed", "reply": res.get("message"), "result": res}

        return {"status": "received"}
    except Exception as e:
        logger.error("WhatsApp webhook error: %s", e)
        return {"status": "error"}

