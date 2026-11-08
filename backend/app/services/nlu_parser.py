import re
from typing import Dict, Any, List, Optional


def parse_indonesian_amount(text: str) -> Optional[tuple[float, str]]:
    """Extracts amount and currency from text, handling formats like 25k, 50rb, 1.5jt, $15, 50.000, 100000."""
    clean = text.lower().strip()

    # Match USD: $15 or 15 usd
    usd_match = re.search(r'\$\s*([0-9]+(?:\.[0-9]+)?)', clean) or re.search(r'([0-9]+(?:\.[0-9]+)?)\s*usd', clean)
    if usd_match:
        return float(usd_match.group(1)), "USD"

    # Match Juta: 1.5jt, 2 juta, 1.25 jt
    jt_match = re.search(r'([0-9]+(?:[\.,][0-9]+)?)\s*(?:jt|juta)', clean)
    if jt_match:
        val_str = jt_match.group(1).replace(',', '.')
        return float(val_str) * 1_000_000, "IDR"

    # Match Ribu / k / rb: 50k, 25rb, 30 ribu, 45.5k
    rb_match = re.search(r'([0-9]+(?:[\.,][0-9]+)?)\s*(?:k|rb|ribu)', clean)
    if rb_match:
        val_str = rb_match.group(1).replace(',', '.')
        return float(val_str) * 1_000, "IDR"

    # Match formatted IDR: Rp 50.000 or 50.000 or 150000
    rp_match = re.search(r'(?:rp\.?\s*)?([0-9]{1,3}(?:\.[0-9]{3})+(?:,[0-9]+)?)', clean)
    if rp_match:
        num_str = rp_match.group(1).replace('.', '').replace(',', '.')
        return float(num_str), "IDR"

    # Plain integer/float without prefix
    num_match = re.search(r'(?:rp\.?\s*)?([0-9]{4,12})', clean)
    if num_match:
        return float(num_match.group(1)), "IDR"

    return None


CATEGORY_KEYWORDS = {
    "Makanan & Minuman": [
        "makan", "minum", "kopi", "ngopi", "cafe", "starbucks", "fore", "kenangan", "warteg",
        "padang", "resto", "mcd", "kfc", "hokben", "lunch", "dinner", "sarapan", "snack", "gofood", "grabfood", "shopeefood"
    ],
    "Transportasi": [
        "bensin", "pertamax", "pertalite", "spbu", "shell", "gojek", "goride", "gocar", "grab", "maxim",
        "tol", "etoll", "parkir", "kereta", "krl", "mrt", "lrt", "pesawat", "tiket", "ojek"
    ],
    "Belanja": [
        "beli", "belanja", "tokopedia", "shopee", "lazada", "tiktok shop", "indomaret", "alfamart",
        "superindo", "baju", "sepatu", "skincare", "pasar", "mall"
    ],
    "Tagihan & Utilitas": [
        "listrik", "pln", "token", "air", "pdam", "wifi", "indihome", "biznet", "first media",
        "pulsa", "paket data", "telkomsel", "indosat", "xl", "bpjs", "asuransi", "kost", "kontrakan"
    ],
    "Hiburan & Rekreasi": [
        "bioskop", "xxi", "cgv", "netflix", "spotify", "youtube", "game", "steam", "playstation",
        "liburan", "hotel", "staycation", "karaoke"
    ],
    "Kesehatan": [
        "obat", "apotek", "dokter", "rumah sakit", "klinik", "vitamin", "halodoc", "alodokter"
    ],
    "Pendidikan": [
        "buku", "kursus", "udemy", "spp", "sekolah", "kuliah", "seminar", "workshop"
    ],
    "Investasi": [
        "investasi", "saham", "reksadana", "bibit", "bareksa", "ajaib", "stockbit", "crypto", "bitcoin",
        "binance", "tokocrypto", "sbn", "sukuk", "emas", "antam"
    ],
    "Gaji & Pendapatan": [
        "gaji", "payroll", "salary", "bonus", "insentif", "thr"
    ],
}

WALLET_KEYWORDS = {
    "cash": ["cash", "tunai", "dompet"],
    "bca": ["bca", "bank bca"],
    "mandiri": ["mandiri", "livin"],
    "bri": ["bri", "brimo"],
    "bni": ["bni"],
    "jago": ["jago", "bank jago"],
    "seabank": ["seabank"],
    "gopay": ["gopay", "gojek"],
    "ovo": ["ovo"],
    "dana": ["dana"],
    "shopeepay": ["shopeepay", "spay"],
    "danamon": ["danamon"],
    "bibit": ["bibit"],
    "stockbit": ["stockbit"],
}

_BUDGET_STOPWORDS = {
    "budget", "pos", "anggaran", "tabungan", "nabung", "uang", "dana",
    "bayar", "beli", "isi", "untuk", "dan", "bulanan", "cash", "cicilan",
}


def match_budget_item_from_text(raw_text: str, active_budgets: List[Any]) -> Optional[Any]:
    """
    Matches natural language expense text (e.g. 'isi bensin 250rb', 'bayar pdam 240k', 'les renang 500rb')
    against the user's active monthly budget rows. Returns the highest-scoring Budget object or None.
    """
    if not active_budgets or not raw_text:
        return None

    clean_text = re.sub(r"[^a-z0-9\s]", " ", raw_text.lower())
    msg_tokens = {tok for tok in clean_text.split() if len(tok) >= 3 and not tok.isdigit()}

    best_budget = None
    best_score = 0.0

    for b in active_budgets:
        raw_name = (getattr(b, "name", None) or "").strip()
        if not raw_name:
            continue
        norm_name = re.sub(r"[^a-z0-9\s]", " ", raw_name.lower()).strip()
        if not norm_name:
            continue

        score = 0.0
        if len(norm_name) >= 3 and re.search(rf"\b{re.escape(norm_name)}\b", clean_text):
            score += 10.0 + len(norm_name) * 0.2

        b_tokens = [
            tok for tok in norm_name.split()
            if len(tok) >= 3 and tok not in _BUDGET_STOPWORDS
        ]
        if b_tokens:
            matched_tokens = [tok for tok in b_tokens if tok in msg_tokens]
            if matched_tokens:
                score += len(matched_tokens) * 4.0 + (len(matched_tokens) / len(b_tokens)) * 2.0

        if score > best_score:
            best_score = score
            best_budget = b

    return best_budget if best_score >= 4.0 else None


def parse_transaction_text(
    raw_text: str,
    user_wallets: Optional[List[str]] = None,
    custom_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Parses natural text input into structured transaction parameters."""
    text_lower = raw_text.lower().strip()

    # Determine Type
    is_transfer = "transfer" in text_lower or "tf " in text_lower or "pindah" in text_lower or "topup" in text_lower or "top up" in text_lower
    is_income = any(w in text_lower for w in ["gaji", "income", "dapat uang", "bonus", "terima", "cair", "pendapatan", "transferan dari"]) and not is_transfer

    tx_type = "TRANSFER" if is_transfer else ("INCOME" if is_income else "EXPENSE")

    # Extract Amount
    parsed_amt = parse_indonesian_amount(text_lower)
    amount, currency = parsed_amt if parsed_amt else (0.0, "IDR")

    # Detect Category (check custom user categories first, then system keyword map)
    category_name = "Lain-lain"
    if tx_type == "INCOME":
        category_name = "Gaji & Pendapatan"
    else:
        matched_custom = None
        if custom_categories:
            for c_name in sorted(custom_categories, key=len, reverse=True):
                if c_name and c_name.lower() in text_lower:
                    matched_custom = c_name
                    break
        if matched_custom:
            category_name = matched_custom
        else:
            for cat, keywords in CATEGORY_KEYWORDS.items():
                if any(k in text_lower for k in keywords):
                    category_name = cat
                    break

    # Detect Target Wallet (match longest user wallet name first)
    detected_wallet = None
    if user_wallets:
        for w in sorted(user_wallets, key=len, reverse=True):
            if w and re.search(rf"\b{re.escape(w.lower())}\b", text_lower):
                detected_wallet = w
                break
        if not detected_wallet:
            for w in sorted(user_wallets, key=len, reverse=True):
                if w and w.lower() in text_lower:
                    detected_wallet = w
                    break

    if not detected_wallet:
        for w_key, aliases in WALLET_KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(a)}\b", text_lower) for a in aliases):
                detected_wallet = aliases[0].upper()
                break

    # Extract clean description
    clean_desc = raw_text
    # Remove amount expressions to clean up description if possible
    clean_desc = re.sub(r'(?:pake|dari|ke|via)\s+[a-z0-9]+', '', clean_desc, flags=re.IGNORECASE).strip()
    if not clean_desc or len(clean_desc) < 3:
        clean_desc = f"{category_name} via {detected_wallet or 'Default Wallet'}"

    return {
        "type": tx_type,
        "amount": amount,
        "currency": currency,
        "category_name": category_name,
        "wallet_hint": detected_wallet,
        "description": clean_desc,
        "confidence": 0.95 if amount > 0 else 0.5,
    }

