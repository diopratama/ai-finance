import re
from typing import Dict, Any, List, Optional


def parse_indonesian_amount(text: str) -> Optional[tuple[float, str]]:
    """Extracts amount and currency from text, handling formats like 25k, 50rb, 1.5jt, $15, 2 gram, 50.000, 100000."""
    clean = text.lower().strip()

    # Match GRAM Emas: 2 gram, 10 gr, 0.5 gram
    gram_match = re.search(r'([0-9]+(?:[\.,][0-9]+)?)\s*(?:gram|gr)\b', clean)
    if gram_match:
        val_str = gram_match.group(1).replace(',', '.')
        return float(val_str), "GRAM"

    # Match USD: $15 or 15 usd or 50 dollar / dolar
    usd_match = (
        re.search(r'\$\s*([0-9]+(?:\.[0-9]+)?)', clean)
        or re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:usd|dollar|dolar)\b', clean)
    )
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
    "cash": ["cash", "tunai", "dompet tunai"],
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
    "bareksa": ["bareksa"],
    "ajaib": ["ajaib"],
    "pluang": ["pluang"],
    "rdn": ["rdn", "rekening dana nasabah"],
    "emas": ["tabungan emas", "emas", "antam", "pegadaian"],
    "sbn": ["sbn", "sukuk", "obligasi"],
    "crypto": ["crypto", "tokocrypto", "indodax", "binance", "pintu"],
}

_BUDGET_STOPWORDS = {
    "budget", "pos", "anggaran", "tabungan", "nabung", "uang", "dana",
    "bayar", "beli", "isi", "untuk", "dan", "bulanan", "cash", "cicilan",
}

_WALLET_FILLER_WORDS = {
    "saldo", "dana", "uang", "rekening", "dompet", "akun", "kantong",
    "sebesar", "senilai", "sejumlah", "nominal",
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


def match_wallet_from_str(
    candidate: str,
    user_wallets: Optional[List[str]] = None,
) -> Optional[str]:
    """Matches a string fragment to a known user wallet or alias, stripping common filler words."""
    if not candidate:
        return None
    cand_raw = candidate.strip().lower()
    # Remove trailing/leading numbers or currency notations from candidate fragment
    cand_clean = re.sub(r'\b(?:rp\.?\s*)?[0-9]+(?:[\.,][0-9]+)?\s*(?:jt|juta|rb|ribu|k|usd)?\b', '', cand_raw).strip()
    if not cand_clean:
        cand_clean = cand_raw

    # Also build a stripped version without generic filler words (like "saldo", "dompet", "rekening")
    tokens = [t for t in cand_clean.split() if t not in _WALLET_FILLER_WORDS]
    cand_core = " ".join(tokens).strip()

    if user_wallets:
        # 1. Exact match against full candidate or core candidate
        for w in user_wallets:
            wl = w.lower().strip()
            if wl == cand_clean or (cand_core and wl == cand_core):
                return w
        # 2. Full wallet name appears inside candidate or candidate core appears as whole word in wallet name
        for w in sorted(user_wallets, key=len, reverse=True):
            wl = w.lower().strip()
            if re.search(rf"\b{re.escape(wl)}\b", cand_clean):
                return w
            if cand_core and len(cand_core) >= 2 and re.search(rf"\b{re.escape(cand_core)}\b", wl):
                return w
        # 3. Token overlap with user wallet non-filler tokens
        if cand_core:
            cand_toks = set(cand_core.split())
            for w in sorted(user_wallets, key=len, reverse=True):
                w_toks = {t for t in w.lower().split() if t not in _WALLET_FILLER_WORDS and len(t) >= 2}
                if w_toks and (cand_toks & w_toks):
                    return w

    for w_key, aliases in WALLET_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(a)}\b", cand_clean) for a in aliases):
            # If user_wallets is provided, check if any user wallet matches this keyword key
            if user_wallets:
                for uw in user_wallets:
                    if w_key in uw.lower() or any(a in uw.lower() for a in aliases):
                        return uw
            return aliases[0].upper()
    return None


def parse_transaction_text(
    raw_text: str,
    user_wallets: Optional[List[str]] = None,
    custom_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Parses natural text input into structured transaction parameters across all wallet types."""
    text_lower = raw_text.lower().strip()

    # Extract Amount
    parsed_amt = parse_indonesian_amount(text_lower)
    amount, currency = parsed_amt if parsed_amt else (0.0, "IDR")

    # Check for transfer / addition / subtraction keywords
    is_topup = any(
        w in text_lower
        for w in [
            "topup", "top up", "isi saldo", "isi dompet", "isi gopay", "isi ovo",
            "tambah saldo", "tambah dana", "tambah uang", "masuk dana", "uang masuk",
            "setor", "nabung", "investasi masuk", "dividen",
        ]
    ) or bool(re.match(r'^\+\s*(?:rp\.?\s*)?\d', text_lower))

    is_explicit_subtract = any(
        w in text_lower
        for w in [
            "kurangi saldo", "kurang saldo", "kurangi dana", "potong saldo", "potong dana",
            "tarik dana", "tarik saldo", "tarik tunai", "keluar dana", "uang keluar", "withdraw",
        ]
    ) or bool(re.match(r'^-\s*(?:rp\.?\s*)?\d', text_lower))

    is_explicit_transfer = any(
        w in text_lower
        for w in [
            "transfer", "tf ", "pindah dana", "pindah saldo", "kirim saldo", "kirim dana", "mutasi",
        ]
    )

    # Extract source and destination wallet hints
    source_wallet_hint = None
    target_wallet_hint = None

    # 1. Detect source wallet preceded by dari / pake / pakai / via / lewat
    src_match = re.search(
        r'\b(?:dari|pake|pakai|via|lewat)\s+([a-zA-Z0-9_\s]+?)(?:\s+(?:ke|menuju|sebesar|nominal|sejumlah|senilai|\d|rp\b)|$)',
        text_lower,
    )
    if src_match:
        source_wallet_hint = match_wallet_from_str(src_match.group(1).strip(), user_wallets)

    # 2. Detect target wallet preceded by ke / menuju
    dest_match = re.search(
        r'\b(?:ke|menuju)\s+([a-zA-Z0-9_\s]+?)(?:\s+(?:dari|pake|pakai|via|lewat|sebesar|nominal|sejumlah|senilai|\d|rp\b)|$)',
        text_lower,
    )
    if dest_match:
        target_wallet_hint = match_wallet_from_str(dest_match.group(1).strip(), user_wallets)

    # 3. Pattern: "transfer/tf/pindah [Wallet A] ke [Wallet B]" (without "dari")
    if is_explicit_transfer and not source_wallet_hint and target_wallet_hint:
        direct_tf_match = re.search(
            r'(?:transfer|tf|pindah(?:\s+dana|\s+saldo)?|kirim(?:\s+dana|\s+saldo)?)\s+([a-zA-Z0-9_\s]+?)\s+(?:ke|menuju)\s+',
            text_lower,
        )
        if direct_tf_match:
            cand_src = match_wallet_from_str(direct_tf_match.group(1).strip(), user_wallets)
            if cand_src and cand_src.lower() != target_wallet_hint.lower():
                source_wallet_hint = cand_src

    # 4. If topup/add e.g. "topup saldo gopay 100rb", "tambah saldo bibit 2jt", "nabung emas 500rb dari bca"
    if not target_wallet_hint and is_topup:
        topup_match = re.search(
            r'(?:topup|top\s*up|isi|tambah|masuk|setor|nabung)\s+(?:saldo\s+|dana\s+|uang\s+|ke\s+)?([a-zA-Z0-9_\s]+?)(?:\s+(?:dari|pake|pakai|via|sebesar|senilai|sejumlah|\d|rp\b)|$)',
            text_lower,
        )
        if topup_match:
            target_wallet_hint = match_wallet_from_str(topup_match.group(1).strip(), user_wallets)

    # 5. If explicit subtract e.g. "kurangi saldo bca 200rb", "tarik dana bibit 1jt"
    if not target_wallet_hint and is_explicit_subtract:
        sub_match = re.search(
            r'(?:kurangi|kurang|potong|tarik|keluar|withdraw)\s+(?:saldo\s+|dana\s+|uang\s+|tunai\s+|dari\s+)?([a-zA-Z0-9_\s]+?)(?:\s+(?:sebesar|senilai|sejumlah|\d|rp\b)|$)',
            text_lower,
        )
        if sub_match:
            target_wallet_hint = match_wallet_from_str(sub_match.group(1).strip(), user_wallets)

    # Determine transaction type
    if source_wallet_hint and target_wallet_hint and source_wallet_hint.lower() != target_wallet_hint.lower():
        tx_type = "TRANSFER"
    elif is_explicit_transfer:
        tx_type = "TRANSFER"
    elif is_explicit_subtract:
        tx_type = "EXPENSE"
    elif is_topup:
        tx_type = "INCOME"
    elif any(w in text_lower for w in ["gaji", "income", "dapat uang", "bonus", "terima", "cair", "pendapatan", "transferan dari", "dividen", "imbal hasil", "kupon sbn"]):
        tx_type = "INCOME"
    else:
        tx_type = "EXPENSE"

    # Detect general wallet hint fallback if not yet detected
    detected_wallet = target_wallet_hint or source_wallet_hint
    if not detected_wallet:
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
                    if user_wallets:
                        matched_uw = next((uw for uw in user_wallets if w_key in uw.lower() or any(a in uw.lower() for a in aliases)), None)
                        if matched_uw:
                            detected_wallet = matched_uw
                            break
                    detected_wallet = aliases[0].upper()
                    break

    # Detect Category
    category_name = "Lain-lain"
    if tx_type == "TRANSFER":
        category_name = "Lain-lain"
    elif is_topup or tx_type == "INCOME":
        if any(k in text_lower for k in ("dividen", "kupon", "imbal hasil", "bunga", "bagi hasil")):
            category_name = "Investasi"
        else:
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

    # Clean description
    clean_desc = raw_text.strip()
    if tx_type == "TRANSFER" and source_wallet_hint and target_wallet_hint:
        clean_desc = f"Transfer dari {source_wallet_hint} ke {target_wallet_hint}"
    elif is_topup and (target_wallet_hint or detected_wallet):
        clean_desc = f"Penambahan Saldo {target_wallet_hint or detected_wallet}"
    elif is_explicit_subtract and (target_wallet_hint or detected_wallet):
        clean_desc = f"Pengurangan Saldo {target_wallet_hint or detected_wallet}"
    else:
        clean_desc = re.sub(r'(?:pake|dari|ke|via)\s+[a-z0-9]+', '', clean_desc, flags=re.IGNORECASE).strip()
        if not clean_desc or len(clean_desc) < 3:
            clean_desc = f"{category_name} via {detected_wallet or 'Default Wallet'}"

    return {
        "type": tx_type,
        "amount": amount,
        "currency": currency,
        "category_name": category_name,
        "wallet_hint": target_wallet_hint or detected_wallet,
        "source_wallet_hint": source_wallet_hint,
        "target_wallet_hint": target_wallet_hint or detected_wallet,
        "description": clean_desc,
        "confidence": 0.95 if amount > 0 else 0.5,
    }

