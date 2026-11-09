import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Resolve skills/planner directory for both Docker (/app/skills/planner) and local dev
_CANDIDATE_DIRS = [
    Path("/app/skills/planner"),
    Path(__file__).resolve().parents[2] / "skills" / "planner",
]
SKILLS_ROOT: Path = next((p for p in _CANDIDATE_DIRS if p.exists()), _CANDIDATE_DIRS[-1])

SKILL_LABELS: Dict[str, str] = {
    "cashflow_budgeting": "Cashflow & Budgeting",
    "emergency_and_protection": "Dana Darurat & Proteksi",
    "debt_and_credit": "Manajemen Utang & KPR",
    "investment_allocation": "Alokasi Portofolio",
    "life_goals_planning": "Tujuan Besar Hidup",
    "retirement_and_fire": "Pensiun & Strategi FIRE",
    "behavioral_coaching": "Psikologi Keuangan",
    "comprehensive_checkup": "Bedah Finansial 360°",
}

SKILL_KEYWORDS: Dict[str, List[str]] = {
    "comprehensive_checkup": [
        "bedah total",
        "checkup",
        "check up",
        "check-up",
        "evaluasi menyeluruh",
        "review semua",
        "audit total",
        "kondisi keuanganku",
        "kondisi keuangan saya",
        "sehat nggak",
        "sehat gak",
        "mulai dari mana",
        "cek kesehatan keuangan",
    ],
    "debt_and_credit": [
        "utang",
        "hutang",
        "cicilan",
        "angsuran",
        "kpr",
        "kkb",
        "paylater",
        "pay later",
        "pinjol",
        "kartu kredit",
        "cc ",
        "dsr",
        "lunas",
        "avalanche",
        "snowball",
        "floating rate",
        "fixed rate",
        "kredit",
    ],
    "emergency_and_protection": [
        "dana darurat",
        "emergency fund",
        "phk",
        "resign",
        "menganggur",
        "asuransi",
        "bpjs",
        "proteksi",
        "asuransi jiwa",
        "term life",
        "unit link",
        "unitlink",
        "premi",
        "rawat inap",
        "rumah sakit",
    ],
    "investment_allocation": [
        "investasi",
        "portofolio",
        "reksa dana",
        "reksadana",
        "rdpu",
        "rdpt",
        "rds",
        "saham",
        "lq45",
        "idx30",
        "issi",
        "jii",
        "s&p",
        "etf",
        "sbn",
        "ori",
        "sbr",
        "sukuk",
        "pbs",
        "obligasi",
        "emas",
        "antam",
        "logam mulia",
        "crypto",
        "kripto",
        "bitcoin",
        "syariah",
        "halal",
        "riba",
        "dca",
        "alokasi aset",
        "deposito",
        "bibit",
    ],
    "life_goals_planning": [
        "nikah",
        "menikah",
        "resepsi",
        "kawin",
        "pendidikan",
        "sekolah",
        "kuliah",
        "uang pangkal",
        "spp",
        "anak",
        "beli rumah",
        "dp rumah",
        "ngontrak",
        "sewa rumah",
        "kost",
        "umrah",
        "umroh",
        "haji",
        "beli mobil",
        "beli motor",
    ],
    "retirement_and_fire": [
        "pensiun",
        "fire",
        "financial freedom",
        "bebas finansial",
        "merdeka finansial",
        "4% rule",
        "rule of 25",
        "coast fire",
        "barista fire",
        "lean fire",
        "fat fire",
        "hari tua",
        "dana pensiun",
        "dplk",
        "swr",
        "withdrawal",
    ],
    "behavioral_coaching": [
        "boros",
        "boncos",
        "kalap",
        "lapar mata",
        "impulsif",
        "impulse",
        "checkout",
        "check out",
        "keranjang kuning",
        "fomo",
        "gengsi",
        "stres",
        "pusing uang",
        "capek hemat",
        "frugal",
        "pasangan",
        "suami",
        "istri",
        "sandwich",
        "bantu orang tua",
        "jajan terus",
        "ngopi terus",
        "khilaf",
    ],
    "cashflow_budgeting": [
        "gaji",
        "budget",
        "anggaran",
        "arus kas",
        "cashflow",
        "cash flow",
        "nabung",
        "menabung",
        "tabungan",
        "50/30/20",
        "zero based",
        "freelance",
        "pengeluaran",
        "hemat",
        "numpang lewat",
        "sisa gaji",
        "pos pengeluaran",
    ],
}

_WORD_NUMBERS = {
    "satu": 1,
    "dua": 2,
    "tiga": 3,
    "empat": 4,
    "lima": 5,
}


def _strip_frontmatter(md_text: str) -> str:
    text = md_text.strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text


def _read_skill_doc(rel_path: str) -> str:
    full_path = SKILLS_ROOT / rel_path
    try:
        return _strip_frontmatter(full_path.read_text(encoding="utf-8"))
    except Exception as err:
        logger.warning("Could not read planner skill file %s: %s", full_path, err)
        return ""


def detect_pronoun_style(message: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Detects user's preferred conversational register for natural mirroring."""
    combined = message.lower()
    if history:
        user_turns = [h.get("content", "").lower() for h in history if h.get("role") == "user"]
        combined = " ".join(user_turns[-3:] + [combined])

    if re.search(r"\b(gue|gw|gua|lo|lu)\b", combined):
        return "SANTAI_AKRAB (`gue` / `lo` — tetap sopan, suportif, dan tajam)"
    if re.search(r"\b(aku|kamu|ku)\b", combined):
        return "HANGAT_AKRAB (`aku` / `kamu` — mengalir santai seperti teman diskusi)"
    if re.search(r"\b(saya|anda|bapak|ibu)\b", combined):
        return "SOPAN_HANGAT (`saya` / `Anda` — ramah, tidak kaku, tidak birokratis)"
    return "HANGAT_NATURAL (`aku` / `kamu` atau sapaan akrab netral — santai & tidak kaku)"


def detect_pacing_mode(message: str) -> str:
    """Determines whether the user is chatting casually/venting vs asking for structured math/plans."""
    msg = message.strip().lower()
    word_count = len(msg.split())

    detailed_triggers = [
        "hitung",
        "simulasi",
        "rincian",
        "strategi",
        "alokasi",
        "bedah",
        "step",
        "langkah",
        "berapa",
        "rencana",
        "portofolio",
        "checkup",
        "check up",
        "bandingkan",
    ]
    if any(t in msg for t in detailed_triggers):
        return (
            "MODE_TERSTRUKTUR_JELAS: User meminta hitungan/strategi konkret. "
            "Berikan poin-poin ringkas, angka yang membumi dari snapshot, dan urutan prioritas yang mudah dieksekusi."
        )
    if word_count <= 14:
        return (
            "MODE_NGOBROL_RINGKAS: Pesan user singkat/santai/curhat. "
            "Jawab hangat dalam 2-4 kalimat tajam (boleh kutip 1 data relevan dari snapshot), "
            "lalu akhiri dengan 1 pertanyaan balik ringan untuk menggali konteks. JANGAN beri ceramah panjang!"
        )
    return (
        "MODE_DISKUSI_SEIMBANG: Jawab mengalir, empatik, fokus pada 2-3 poin terpenting saja, "
        "dan ajukan maksimal 1 pertanyaan lanjutan jika ada konteks yang perlu diperjelas."
    )


def route_planner_skills(message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Selects 1-2 most relevant financial planning skills based on user message and recent turn."""
    msg_lower = message.lower()
    recent_user_context = ""
    if history:
        prev_users = [h.get("content", "").lower() for h in history if h.get("role") == "user"]
        if len(prev_users) >= 2:
            recent_user_context = prev_users[-2]

    scores: Dict[str, int] = {k: 0 for k in SKILL_KEYWORDS}
    for skill_key, keywords in SKILL_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                scores[skill_key] += 3
            elif recent_user_context and len(msg_lower.split()) <= 8 and kw in recent_user_context:
                scores[skill_key] += 1

    # Check if comprehensive checkup is explicitly triggered
    if scores["comprehensive_checkup"] >= 3:
        ranked_others = sorted(
            [(k, v) for k, v in scores.items() if k != "comprehensive_checkup" and v > 0],
            key=lambda x: x[1],
            reverse=True,
        )
        selected = ["comprehensive_checkup"]
        if ranked_others:
            selected.append(ranked_others[0][0])
    else:
        ranked = sorted([(k, v) for k, v in scores.items() if v > 0], key=lambda x: x[1], reverse=True)
        if ranked:
            selected = [ranked[0][0]]
            if len(ranked) > 1 and ranked[1][1] >= 3:
                selected.append(ranked[1][0])
        else:
            # Default conversational fallback: cashflow + behavioral for general chats
            selected = ["cashflow_budgeting", "behavioral_coaching"]

    active_labels = [SKILL_LABELS[s] for s in selected if s in SKILL_LABELS]
    return {
        "skill_ids": selected,
        "skill_labels": active_labels,
        "pronoun_style": detect_pronoun_style(message, history),
        "pacing_mode": detect_pacing_mode(message),
    }


def build_planner_system_prompt(
    financial_context: Dict[str, Any],
    routing: Dict[str, Any],
    web_search_context: Optional[str] = None,
) -> str:
    """Assembles the modular system prompt from PERSONA_AND_TONE + RUNTIME_CONTRACT + routed SKILL.md files + verified snapshot."""
    persona_doc = _read_skill_doc("PERSONA_AND_TONE.md")
    contract_doc = _read_skill_doc("RUNTIME_CONTRACT.md")

    skill_sections: List[str] = []
    for skill_id in routing.get("skill_ids", []):
        doc = _read_skill_doc(f"{skill_id}/SKILL.md")
        if doc:
            skill_sections.append(doc)

    joined_skills = "\n\n---\n\n".join(skill_sections)

    wallets_lines = financial_context.get("wallets_breakdown_text", "- Belum ada dompet tercatat")
    categories_lines = financial_context.get("category_spending_text", "- Belum ada transaksi pengeluaran tercatat")
    budgets_lines = financial_context.get("budget_alerts_text", "- Belum ada anggaran aktif")
    memory_lines = financial_context.get("memory_notes_text", "- Belum ada catatan khusus dari obrolan")
    missing_hints = financial_context.get("missing_profile_hints", [])
    missing_text = ", ".join(missing_hints) if missing_hints else "Seluruh profil inti sudah terkonfirmasi (100%)"

    snapshot_block = f"""[VERIFIED USER FINANCIAL SNAPSHOT]
- Mata Uang Acuan: {financial_context.get('base_currency', 'IDR')}
- Total Kekayaan Bersih (Net Worth): {financial_context.get('net_worth_formatted', 'Rp 0')}
- Saldo Likuid (Kas/Bank/E-Wallet): {financial_context.get('liquid_balance_formatted', 'Rp 0')}
- Rincian Dompet Aktif:
{wallets_lines}
- Penghasilan Bulanan: {financial_context.get('monthly_income_formatted', 'Rp 0')} [{financial_context.get('income_confirmation_label', 'BELUM DIKONFIRMASI')}]
- Pengeluaran Bulanan Acuan: {financial_context.get('monthly_expenses_formatted', 'Rp 0')} [{financial_context.get('expense_confirmation_label', 'BELUM DIKONFIRMASI')}]
- Cicilan Utang Bulanan: {financial_context.get('monthly_debt_formatted', 'Rp 0')} (DSR: {financial_context.get('dsr_percentage', 0)}%) [{financial_context.get('debt_confirmation_label', 'BELUM DIKONFIRMASI')}]
- Savings Margin Aktual: {financial_context.get('savings_margin_percentage', 0)}%
- Status Pernikahan & Tanggungan: {financial_context.get('household_summary', 'Lajang, 0 tanggungan')} [{financial_context.get('household_confirmation_label', 'BELUM DIKONFIRMASI')}]
- Dana Darurat Saat Ini: {financial_context.get('emergency_fund_months', 0)} bulan tercover dari target {financial_context.get('emergency_target_months', 3)} bulan ({financial_context.get('emergency_fund_status', 'Perlu Ditingkatkan')})
- Usia & Target Kemandirian Finansial (FIRE): Usia {financial_context.get('current_age', 28)} th -> Target {financial_context.get('target_fire_age', 50)} th [{financial_context.get('age_confirmation_label', 'BELUM DIKONFIRMASI')}]
- Target Angka FIRE (Rule of 25): {financial_context.get('fire_target_formatted', 'Rp 2.400.000.000')} | Target Coast FIRE Saat Ini: {financial_context.get('coast_fire_formatted', 'Rp 0')}
- Profil Toleransi Risiko: {financial_context.get('risk_profile', 'MODERATE')} [{financial_context.get('risk_confirmation_label', 'BELUM DIKONFIRMASI')}]
- Preferensi Syariah: {"AKTIF (Syariah Only — wajib instrumen halal/syariah)" if financial_context.get('sharia_preference') else "TIDAK AKTIF (Umum/Konvensional & Syariah boleh)"}
- Skor Kesehatan Finansial: {financial_context.get('health_score', 0)}/100 ({financial_context.get('health_status', 'NEEDS_ATTENTION')})
- Pengeluaran Kategori Terdata:
{categories_lines}
- Status Anggaran (Budget) Bulan Ini:
{budgets_lines}
- Catatan Memori Konteks Hidup User:
{memory_lines}
- Kelengkapan Profil Personalisasi: {financial_context.get('profile_completeness_pct', 0)}% (Belum dikonfirmasi: {missing_text})
[/VERIFIED USER FINANCIAL SNAPSHOT]"""

    web_section = ""
    if web_search_context and web_search_context.strip():
        web_section = f"\n\n---\n\n{web_search_context.strip()}\n\n"

    return f"""{persona_doc}

---

{contract_doc}

---

## Panduan Giliran Bicara Saat Ini
- **Gaya Sapaan User:** {routing.get('pronoun_style')}
- **Pacing Respons:** {routing.get('pacing_mode')}
- **Modul Keahlian Aktif:** {', '.join(routing.get('skill_labels', []))}

---

{joined_skills}

---

{snapshot_block}{web_section}
"""


def _parse_idr_amount(num_str: str, unit_str: str) -> Optional[float]:
    """Parses Indonesian currency shorthand like '18,5', 'jt' -> 18500000.0."""
    raw = num_str.strip()
    unit = (unit_str or "").strip().lower()

    if unit in ("jt", "juta", "mio"):
        cleaned = raw.replace(".", "").replace(",", ".") if "," in raw else raw.replace(",", ".")
        try:
            return float(cleaned) * 1_000_000.0
        except ValueError:
            return None
    if unit in ("rb", "ribu", "k"):
        cleaned = raw.replace(".", "").replace(",", ".") if "," in raw else raw.replace(",", ".")
        try:
            return float(cleaned) * 1_000.0
        except ValueError:
            return None
    if unit in ("m", "miliar", "milyar"):
        cleaned = raw.replace(".", "").replace(",", ".") if "," in raw else raw.replace(",", ".")
        try:
            return float(cleaned) * 1_000_000_000.0
        except ValueError:
            return None

    # Raw full number like 15.000.000 or 15000000
    digits_only = re.sub(r"[.,]", "", raw)
    if digits_only.isdigit() and len(digits_only) >= 6:
        return float(digits_only)
    return None


def get_confirmed_fields_set(profile: Any) -> Set[str]:
    if not profile or not getattr(profile, "confirmed_profile_fields", None):
        return set()
    try:
        parsed = json.loads(profile.confirmed_profile_fields)
        if isinstance(parsed, list):
            return {str(x) for x in parsed}
    except Exception:
        pass
    return set()


def save_confirmed_fields_set(profile: Any, fields: Set[str]) -> None:
    profile.confirmed_profile_fields = json.dumps(sorted(fields))


def extract_and_update_profile_memory(message: str, profile: Any) -> Dict[str, Any]:
    """
    Auto-captures personal financial facts mentioned naturally in chat and updates FinancialProfile.
    Returns {'updated': bool, 'updated_fields': [...]}.
    """
    if not profile or not message:
        return {"updated": False, "updated_fields": []}

    text = message.lower()
    confirmed = get_confirmed_fields_set(profile)
    updated_fields: List[str] = []

    amount_pattern = r"(?:rp\.?\s*)?(\d+(?:[.,]\d+)*)\s*(jt|juta|mio|rb|ribu|k|miliar|milyar)?"

    # 1. Monthly Income extraction (avoid hypothetical "kalau gaji..." only if clearly about someone else; user scenarios still useful unless hypothetical)
    income_match = re.search(
        rf"(?:gaji(?:ku| saya| aku)?|penghasilan(?:ku| saya| aku)?|income(?:ku| saya| aku)?|take\s*home\s*pay|thp)\s*(?:sekitar|kurang lebih|kira-kira|sebulan|bulanan|bersih|:)?\s*{amount_pattern}",
        text,
    )
    if income_match:
        amt = _parse_idr_amount(income_match.group(1), income_match.group(2) or "")
        if amt and 500_000 <= amt <= 5_000_000_000:
            profile.monthly_income = amt
            confirmed.add("monthly_income")
            updated_fields.append("monthly_income")

    # 2. Monthly Living Expense extraction
    expense_match = re.search(
        rf"(?:pengeluaran\s*(?:bulanan|rutin|sebulan)|biaya\s*hidup(?:\s*sebulan|\s*bulanan)?)\s*(?:sekitar|kurang lebih|kira-kira|:)?\s*{amount_pattern}",
        text,
    )
    if expense_match:
        amt = _parse_idr_amount(expense_match.group(1), expense_match.group(2) or "")
        if amt and 300_000 <= amt <= 2_000_000_000:
            profile.monthly_living_expense = amt
            profile.fire_target_amount = amt * 12 * 25
            confirmed.add("monthly_living_expense")
            updated_fields.append("monthly_living_expense")

    # 3. Debt / Installments extraction (including debt-free confirmation)
    no_debt_patterns = [
        r"(?:gak|nggak|enggak|tidak|belum)\s+(?:ada|punya)\s+(?:utang|hutang|cicilan|angsuran)",
        r"bebas\s+(?:utang|hutang|cicilan)",
        r"(?:cicilan|utang|hutang)\s*(?:nya\s*)?(?:0|nol)\b",
    ]
    if any(re.search(p, text) for p in no_debt_patterns):
        profile.monthly_debt_payment = 0.0
        confirmed.add("debt_obligation")
        updated_fields.append("debt_obligation")
    else:
        # Avoid capturing hypothetical "mau ambil cicilan..." as existing debt if prefaced by mau/rencana/kalau ambil
        debt_match = re.search(
            rf"(?<!mau\s)(?<!rencana\s)(?:ada\s+cicilan|punya\s+cicilan|cicilan(?:ku| saya| aku| sekarang| rutin| bulanan)?|bayar\s+cicilan|angsuran(?:ku| rutin| bulanan)?)\s*(?:kpr|motor|mobil|paylater|sebulan|per\s*bulan|sekitar|:)?\s*{amount_pattern}",
            text,
        )
        if debt_match:
            amt = _parse_idr_amount(debt_match.group(1), debt_match.group(2) or "")
            if amt is not None and 0 <= amt <= 1_000_000_000:
                profile.monthly_debt_payment = amt
                confirmed.add("debt_obligation")
                updated_fields.append("debt_obligation")

    # 4. Marital Status & Dependents extraction
    if re.search(r"\b(udah nikah|sudah menikah|udah menikah|berkeluarga|istriku|suamiku|istri saya|suami saya)\b", text):
        profile.marital_status = "MARRIED"
        confirmed.add("marital_and_dependents")
        updated_fields.append("marital_status")
    elif re.search(r"\b(masih single|masih lajang|belum nikah|belum menikah|status single|status lajang|jomblo)\b", text):
        profile.marital_status = "SINGLE"
        confirmed.add("marital_and_dependents")
        updated_fields.append("marital_status")

    if re.search(r"\b(belum punya anak|tanpa tanggungan|gak ada tanggungan|nggak ada tanggungan|tidak ada tanggungan|0 anak)\b", text):
        profile.dependents_count = 0
        confirmed.add("marital_and_dependents")
        updated_fields.append("dependents_count")
    else:
        dep_digit = re.search(r"(?:anak(?:nya|ku| saya)?\s*(\d+)|punya\s*(\d+)\s*anak|(\d+)\s*(?:anak|tanggungan)|tanggungan\s*(\d+))", text)
        if dep_digit:
            val = next((int(g) for g in dep_digit.groups() if g is not None), None)
            if val is not None and 0 <= val <= 15:
                profile.dependents_count = val
                confirmed.add("marital_and_dependents")
                updated_fields.append("dependents_count")
        else:
            dep_word = re.search(r"\banak\s+(satu|dua|tiga|empat|lima)\b|\bpunya\s+(satu|dua|tiga|empat|lima)\s+anak\b", text)
            if dep_word:
                word = dep_word.group(1) or dep_word.group(2)
                if word in _WORD_NUMBERS:
                    profile.dependents_count = _WORD_NUMBERS[word]
                    confirmed.add("marital_and_dependents")
                    updated_fields.append("dependents_count")

    # 5. Sharia Preference extraction
    if re.search(r"\b(fokus syariah|mau(?:nya)? syariah|prefer syariah|khusus syariah|investasi syariah|instrumen halal|bebas riba|mode syariah)\b", text):
        if not profile.sharia_preference:
            profile.sharia_preference = True
            updated_fields.append("sharia_preference")
    elif re.search(r"\b(konvensional aja|tidak harus syariah|gak harus syariah|matikan mode syariah)\b", text):
        if profile.sharia_preference:
            profile.sharia_preference = False
            updated_fields.append("sharia_preference")

    # 6. Age & Target Retirement Age extraction
    age_match = re.search(r"(?:umur(?:ku| saya| aku)?|usia(?:ku| saya| aku)?|aku umur|saya usia)\s*(\d{2})\b", text)
    if age_match:
        age_val = int(age_match.group(1))
        if 17 <= age_val <= 80:
            profile.current_age = age_val
            confirmed.add("age_and_retirement")
            updated_fields.append("current_age")

    retire_match = re.search(r"(?:target\s*pensiun|pensiun\s*(?:dini\s*)?(?:di\s*)?(?:umur|usia)|fire\s*(?:di\s*)?(?:umur|usia))\s*(\d{2})\b", text)
    if retire_match:
        ret_val = int(retire_match.group(1))
        if 25 <= ret_val <= 85:
            profile.target_fire_age = ret_val
            confirmed.add("age_and_retirement")
            updated_fields.append("target_fire_age")

    # 7. Risk Tolerance extraction
    if re.search(r"\b(profil(?:ku| saya)?\s*konservatif|tipe\s*konservatif|cari\s*aman\s*aja|gak\s*kuat\s*fluktuasi|takut\s*rugi)\b", text):
        profile.risk_tolerance = "CONSERVATIVE"
        confirmed.add("risk_profile")
        updated_fields.append("risk_profile")
    elif re.search(r"\b(profil(?:ku| saya)?\s*agresif|tipe\s*agresif|siap\s*risiko\s*tinggi|siap\s*fluktuasi)\b", text):
        profile.risk_tolerance = "AGGRESSIVE"
        confirmed.add("risk_profile")
        updated_fields.append("risk_profile")
    elif re.search(r"\b(profil(?:ku| saya)?\s*moderat|tipe\s*moderat)\b", text):
        profile.risk_tolerance = "MODERATE"
        confirmed.add("risk_profile")
        updated_fields.append("risk_profile")

    # 8. Contextual Life Goal Memory Notes capture
    goal_snippets: List[str] = []
    goal_patterns: List[Tuple[str, str]] = [
        (r"\b(freelance|freelancer|penghasilan tidak tetap|komisi)\b", "Penghasilan variabel / freelance"),
        (r"\b(sandwich generation|generasi sandwich|biayain orang tua|bantu orang tua)\b", "Mendukung finansial orang tua (sandwich)"),
        (r"\b(mau nikah|rencana menikah|dana nikah|persiapan nikah)\b", "Sedang menyiapkan dana menikah"),
        (r"\b(dana kuliah|dana pendidikan|uang pangkal anak|sekolah anak)\b", "Fokus menyiapkan dana pendidikan anak"),
        (r"\b(mau ambil kpr|rencana beli rumah|nabung dp rumah)\b", "Merencanakan pembelian rumah pertama / DP KPR"),
        (r"\b(dana haji|tabungan umrah|tabungan umroh)\b", "Menyiapkan dana ibadah Haji/Umrah"),
    ]
    existing_notes = [line.strip() for line in (profile.memory_notes or "").splitlines() if line.strip()]
    for pat, label in goal_patterns:
        if re.search(pat, text) and label not in existing_notes:
            goal_snippets.append(label)

    if goal_snippets:
        merged_notes = (existing_notes + goal_snippets)[-6:]
        profile.memory_notes = "\n".join(merged_notes)
        updated_fields.append("memory_notes")

    if updated_fields:
        save_confirmed_fields_set(profile, confirmed)

    return {
        "updated": bool(updated_fields),
        "updated_fields": updated_fields,
    }


def calculate_profile_completeness(
    profile: Any,
    tx_income: float = 0.0,
    tx_expense: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculates personalization accuracy (0-100%) and subtle missing-field nudges
    without forcing any mandatory upfront form.
    """
    confirmed = get_confirmed_fields_set(profile)

    income_ready = ("monthly_income" in confirmed) or (getattr(profile, "monthly_income", 0.0) or 0.0) > 0 or tx_income > 0
    expense_ready = ("monthly_living_expense" in confirmed) or tx_expense > 0
    household_ready = "marital_and_dependents" in confirmed
    debt_ready = ("debt_obligation" in confirmed) or (getattr(profile, "monthly_debt_payment", 0.0) or 0.0) > 0
    risk_ready = "risk_profile" in confirmed
    age_ready = ("age_and_retirement" in confirmed) or bool(getattr(profile, "memory_notes", None))

    score = 0
    missing_hints: List[str] = []

    if income_ready:
        score += 20
    else:
        missing_hints.append("Penghasilan bersih bulanan")

    if expense_ready:
        score += 20
    else:
        missing_hints.append("Estimasi pengeluaran hidup bulanan")

    if household_ready:
        score += 20
    else:
        missing_hints.append("Status pernikahan & jumlah tanggungan")

    if debt_ready:
        score += 15
    else:
        missing_hints.append("Cicilan rutin bulanan (atau konfirmasi bebas utang)")

    if risk_ready:
        score += 15
    else:
        missing_hints.append("Profil risiko investasi")

    if age_ready:
        score += 10
    else:
        missing_hints.append("Usia & target usia pensiun")

    return {
        "profile_completeness_pct": min(100, score),
        "confirmed_fields": sorted(confirmed),
        "missing_profile_hints": missing_hints,
        "flags": {
            "income_ready": income_ready,
            "expense_ready": expense_ready,
            "household_ready": household_ready,
            "debt_ready": debt_ready,
            "risk_ready": risk_ready,
            "age_ready": age_ready,
        },
    }
