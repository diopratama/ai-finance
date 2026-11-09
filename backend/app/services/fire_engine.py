import math
from typing import Dict, Any, List, Optional


def calculate_fire_metrics(
    current_age: int,
    target_fire_age: int,
    monthly_expenses: float,
    current_net_worth: float,
    monthly_savings: float = 0.0,
    annual_return_rate: float = 0.07,  # 7% real return after inflation
    withdrawal_rate: float = 0.04,  # 4% Rule
) -> Dict[str, Any]:
    """Calculates FIRE (Financial Independence, Retire Early) targets, Coast FIRE, projections, and timelines."""
    annual_expenses = monthly_expenses * 12
    # Rule of 25: FIRE target = 25 * Annual Expenses
    fire_number = annual_expenses / withdrawal_rate if withdrawal_rate > 0 else annual_expenses * 25
    years_to_target = max(0, target_fire_age - current_age)

    # Coast FIRE: lump sum needed today so compound growth alone hits fire_number by target_fire_age
    if years_to_target > 0 and annual_return_rate > 0:
        coast_fire_number = fire_number / math.pow(1 + annual_return_rate, years_to_target)
    else:
        coast_fire_number = fire_number

    # Future value calculation of current net worth + regular monthly savings
    monthly_r = annual_return_rate / 12
    n_months = years_to_target * 12

    if monthly_r > 0:
        pv_growth = current_net_worth * math.pow(1 + monthly_r, n_months)
        pmt_growth = monthly_savings * ((math.pow(1 + monthly_r, n_months) - 1) / monthly_r) if monthly_savings > 0 else 0
        projected_net_worth = pv_growth + pmt_growth
    else:
        projected_net_worth = current_net_worth + (monthly_savings * n_months)

    actual_years_needed = None
    if projected_net_worth < fire_number and monthly_savings > 0 and monthly_r > 0:
        balance = current_net_worth
        month_count = 0
        max_months = 12 * 70  # cap at 70 years
        while balance < fire_number and month_count < max_months:
            balance = balance * (1 + monthly_r) + monthly_savings
            month_count += 1
        actual_years_needed = round(month_count / 12, 1)
    elif current_net_worth >= fire_number:
        actual_years_needed = 0.0
    elif monthly_savings <= 0:
        actual_years_needed = 999.0

    progress_percentage = min(100.0, round((current_net_worth / fire_number) * 100, 1)) if fire_number > 0 else 0.0

    return {
        "fire_number": round(fire_number, 2),
        "coast_fire_number": round(coast_fire_number, 2),
        "is_coast_fire_achieved": current_net_worth >= coast_fire_number,
        "annual_expenses": round(annual_expenses, 2),
        "withdrawal_rate": withdrawal_rate,
        "current_net_worth": round(current_net_worth, 2),
        "progress_percentage": progress_percentage,
        "years_to_target_age": years_to_target,
        "projected_net_worth_at_fire_age": round(projected_net_worth, 2),
        "is_on_track": projected_net_worth >= fire_number,
        "actual_years_needed": actual_years_needed,
    }


def get_asset_allocation_recommendation(risk_tolerance: str, sharia_preference: bool = False) -> Dict[str, Any]:
    """Provides holistic asset allocation models based on risk tolerance and Conventional/Sharia preference."""
    risk = (risk_tolerance or "MODERATE").upper()

    if sharia_preference:
        if risk == "CONSERVATIVE":
            return {
                "profile": "Konservatif Syariah (Proteksi Modal Halal)",
                "description": "Fokus menjaga nilai pokok bebas riba dengan instrumen negara & pasar uang syariah.",
                "allocations": [
                    {"asset": "Sukuk Negara Ritel (SR / ST / PBS)", "asset_class": "BOND", "percentage": 45, "color": "#3b82f6"},
                    {"asset": "Reksa Dana Pasar Uang Syariah & Deposito Mudharabah", "asset_class": "MONEY_MARKET", "percentage": 35, "color": "#10b981"},
                    {"asset": "Emas Fisik / Logam Mulia", "asset_class": "GOLD", "percentage": 15, "color": "#eab308"},
                    {"asset": "Saham Syariah Bluechip (JII / ISSI)", "asset_class": "EQUITY", "percentage": 5, "color": "#8b5cf6"},
                ],
                "expected_cagr": "5.8% - 7.2%",
            }
        elif risk == "AGGRESSIVE":
            return {
                "profile": "Agresif Syariah (Pertumbuhan Ekuitas Halal)",
                "description": "Akselerasi kekayaan jangka panjang berbasis efek syariah terverifikasi DES/ISSI & emas.",
                "allocations": [
                    {"asset": "Saham Syariah Pilihan (ISSI / JII70)", "asset_class": "EQUITY", "percentage": 55, "color": "#8b5cf6"},
                    {"asset": "Sukuk Negara / Project Based Sukuk (PBS)", "asset_class": "BOND", "percentage": 20, "color": "#3b82f6"},
                    {"asset": "Emas Fisik / Logam Mulia", "asset_class": "GOLD", "percentage": 15, "color": "#eab308"},
                    {"asset": "Reksa Dana Pasar Uang Syariah (Kas Taktis)", "asset_class": "MONEY_MARKET", "percentage": 10, "color": "#10b981"},
                ],
                "expected_cagr": "10.0% - 13.5%",
            }
        return {
            "profile": "Moderat Syariah (Pertumbuhan Berimbang Halal)",
            "description": "Kombinasi seimbang antara bagi hasil Sukuk Negara, ekuitas syariah, dan lindung nilai emas.",
            "allocations": [
                {"asset": "Saham & Reksa Dana Saham Syariah (JII / ISSI)", "asset_class": "EQUITY", "percentage": 40, "color": "#8b5cf6"},
                {"asset": "Sukuk Negara (SR / ST / PBS)", "asset_class": "BOND", "percentage": 35, "color": "#3b82f6"},
                {"asset": "Reksa Dana Pasar Uang Syariah", "asset_class": "MONEY_MARKET", "percentage": 15, "color": "#10b981"},
                {"asset": "Emas Fisik / Antam", "asset_class": "GOLD", "percentage": 10, "color": "#eab308"},
            ],
            "expected_cagr": "8.0% - 10.0%",
        }

    if risk == "CONSERVATIVE":
        return {
            "profile": "Konservatif (Capital Preservation)",
            "description": "Fokus pada keamanan modal dan proteksi nilai aset dengan volatilitas sangat minim.",
            "allocations": [
                {"asset": "Obligasi Negara / SBN / Sukuk", "asset_class": "BOND", "percentage": 45, "color": "#3b82f6"},
                {"asset": "Reksa Dana Pasar Uang & Deposito", "asset_class": "MONEY_MARKET", "percentage": 30, "color": "#10b981"},
                {"asset": "Emas Logam Mulia", "asset_class": "GOLD", "percentage": 15, "color": "#eab308"},
                {"asset": "Saham Bluechip / Index Fund", "asset_class": "EQUITY", "percentage": 10, "color": "#8b5cf6"},
            ],
            "expected_cagr": "6.0% - 7.5%",
        }
    elif risk == "AGGRESSIVE":
        return {
            "profile": "Agresif (Maximum Capital Growth)",
            "description": "Fokus pada pertumbuhan kekayaan jangka panjang dan siap menghadapi fluktuasi pasar.",
            "allocations": [
                {"asset": "Saham (IDX LQ45 & US Tech / S&P 500)", "asset_class": "EQUITY", "percentage": 55, "color": "#8b5cf6"},
                {"asset": "Crypto (Bitcoin / Bluechip Crypto)", "asset_class": "CRYPTO", "percentage": 15, "color": "#f97316"},
                {"asset": "Obligasi Korporasi / SBN", "asset_class": "BOND", "percentage": 15, "color": "#3b82f6"},
                {"asset": "Emas Logam Mulia", "asset_class": "GOLD", "percentage": 10, "color": "#eab308"},
                {"asset": "Pasar Uang / Kas Cadangan", "asset_class": "MONEY_MARKET", "percentage": 5, "color": "#10b981"},
            ],
            "expected_cagr": "11.0% - 15.0%",
        }
    else:  # MODERATE
        return {
            "profile": "Moderat (Balanced Growth)",
            "description": "Keseimbangan ideal antara apresiasi modal jangka panjang dan stabilitas arus kas.",
            "allocations": [
                {"asset": "Saham & Reksa Dana Saham", "asset_class": "EQUITY", "percentage": 40, "color": "#8b5cf6"},
                {"asset": "Obligasi Negara / SBN", "asset_class": "BOND", "percentage": 30, "color": "#3b82f6"},
                {"asset": "Reksa Dana Pendapatan Tetap & Pasar Uang", "asset_class": "MONEY_MARKET", "percentage": 15, "color": "#10b981"},
                {"asset": "Emas Fisik / Antam", "asset_class": "GOLD", "percentage": 10, "color": "#eab308"},
                {"asset": "Aset Alternatif / Crypto Pilihan", "asset_class": "CRYPTO", "percentage": 5, "color": "#f97316"},
            ],
            "expected_cagr": "8.5% - 10.5%",
        }


def determine_emergency_target_months(is_married: bool = False, dependents_count: int = 0) -> int:
    """Determines ideal emergency fund months based on household dependents."""
    deps = max(0, int(dependents_count or 0))
    if is_married:
        if deps >= 2:
            return 12
        if deps == 1:
            return 9
        return 6
    else:
        if deps >= 2:
            return 9
        if deps == 1:
            return 6
        return 3


def calculate_financial_health_score(
    total_assets: float,
    total_debts: float,
    monthly_income: float,
    monthly_expenses: float,
    emergency_fund: float,
    is_married: bool = False,
    dependents_count: int = 0,
    monthly_debt_payment: float = 0.0,
) -> Dict[str, Any]:
    """Calculates holistic personal financial health indicators."""
    target_months = determine_emergency_target_months(is_married=is_married, dependents_count=dependents_count)
    ideal_emergency_fund = monthly_expenses * target_months
    emergency_ratio = emergency_fund / monthly_expenses if monthly_expenses > 0 else 0

    effective_debt_payment = monthly_debt_payment if monthly_debt_payment > 0 else total_debts
    total_outflow = monthly_expenses + monthly_debt_payment
    # Savings margin
    savings_margin = (monthly_income - total_outflow) / monthly_income if monthly_income > 0 else 0
    # Debt Service Ratio (DSR)
    debt_service_ratio = effective_debt_payment / monthly_income if monthly_income > 0 else 0
    # Net Worth
    net_worth = total_assets - total_debts

    # Scoring breakdown (0 to 100)
    score = 0

    # Emergency fund score (max 35)
    if emergency_ratio >= target_months:
        score += 35
    elif target_months > 0:
        score += max(0, int((emergency_ratio / target_months) * 35))

    # Savings margin score (max 35)
    if savings_margin >= 0.20:  # >= 20%
        score += 35
    elif savings_margin > 0:
        score += int((savings_margin / 0.20) * 35)

    # Debt ratio score (max 30)
    if debt_service_ratio <= 0.30:  # <= 30%
        score += 30
    elif debt_service_ratio <= 0.50:
        score += 15

    status = (
        "EXCELLENT"
        if score >= 80
        else ("HEALTHY" if score >= 60 else ("NEEDS_ATTENTION" if score >= 40 else "CRITICAL"))
    )

    return {
        "score": score,
        "status": status,
        "net_worth": round(net_worth, 2),
        "emergency_fund": {
            "current": round(emergency_fund, 2),
            "target": round(ideal_emergency_fund, 2),
            "months_covered": round(emergency_ratio, 1),
            "target_months": target_months,
            "is_sufficient": emergency_ratio >= target_months,
        },
        "savings_margin_percentage": round(savings_margin * 100, 1),
        "debt_service_ratio_percentage": round(debt_service_ratio * 100, 1),
    }


ASSET_CLASS_LABELS = {
    "EQUITY": "Saham & Ekuitas",
    "BOND": "Obligasi / SBN / Sukuk",
    "MONEY_MARKET": "Pasar Uang & Deposito",
    "GOLD": "Emas & Logam Mulia",
    "CRYPTO": "Crypto & Aset Alternatif",
}

ASSET_CLASS_COLORS = {
    "EQUITY": "#8b5cf6",
    "BOND": "#3b82f6",
    "MONEY_MARKET": "#10b981",
    "GOLD": "#eab308",
    "CRYPTO": "#f97316",
}


def is_investment_wallet(name: str, wallet_type: str, explicit_class: Optional[str] = None) -> bool:
    """Determines whether a wallet represents an investment account/instrument."""
    if explicit_class and explicit_class.strip().upper() in ASSET_CLASS_LABELS:
        return True
    wt = (wallet_type or "").upper()
    if any(k in wt for k in ("INVEST", "RDN", "SAHAM", "REKSADANA", "CRYPTO", "EMAS", "SBN", "SUKUK", "OBLIGASI", "DEPOSITO")):
        return True
    nm = (name or "").lower()
    if any(k in nm for k in ("bibit", "bareksa", "stockbit", "ajaib", "pluang", "ipot", "reksadana", "reksa dana", "saham", "sbn", "sukuk", "ori", "sbr", "emas", "antam", "pegadaian", "crypto", "bitcoin", "tokocrypto", "indodax", "binance", "rdn", "deposito", "investasi")):
        return True
    return False


def infer_wallet_asset_class(name: str, wallet_type: str, explicit_class: Optional[str] = None) -> Optional[str]:
    """Maps an investment wallet into one of: EQUITY, BOND, MONEY_MARKET, GOLD, CRYPTO."""
    if explicit_class and explicit_class.strip().upper() in ASSET_CLASS_LABELS:
        return explicit_class.strip().upper()

    if not is_investment_wallet(name, wallet_type, explicit_class):
        return None

    combined = f"{name or ''} {wallet_type or ''}".lower()
    if any(k in combined for k in ("emas", "gold", "antam", "logam mulia", "pegadaian")):
        return "GOLD"
    if any(k in combined for k in ("crypto", "bitcoin", "btc", "eth", "binance", "tokocrypto", "indodax", "pintu", "pluang crypto", "web3")):
        return "CRYPTO"
    if any(k in combined for k in ("sbn", "sukuk", "obligasi", "bond", "ori", "sbr", "st0", "sr0", "pbs", "fr0", "pendapatan tetap", "rdpt")):
        return "BOND"
    if any(k in combined for k in ("pasar uang", "rdpu", "deposito", "money market")):
        return "MONEY_MARKET"
    return "EQUITY"


def evaluate_investment_portfolio(
    wallets: List[Any],
    risk_tolerance: str = "MODERATE",
    sharia_preference: bool = False,
    liquid_cash_balance: float = 0.0,
    monthly_expenses: float = 8_000_000.0,
    is_married: bool = False,
    dependents_count: int = 0,
) -> Dict[str, Any]:
    """
    Compares the user's investment wallets against the reference asset allocation model
    and evaluates financial best practices (Emergency Fund readiness, Cash Drag, Concentration Risk, Rebalancing).
    """
    ref_model = get_asset_allocation_recommendation(risk_tolerance=risk_tolerance, sharia_preference=sharia_preference)
    target_map: Dict[str, Dict[str, Any]] = {}
    for item in ref_model["allocations"]:
        ac = item.get("asset_class", "EQUITY")
        target_map[ac] = {
            "asset_class": ac,
            "label": item["asset"],
            "target_pct": float(item["percentage"]),
            "color": item.get("color", ASSET_CLASS_COLORS.get(ac, "#8b5cf6")),
        }

    # Ensure all 5 standard asset classes exist in comparison map
    for ac, default_label in ASSET_CLASS_LABELS.items():
        if ac not in target_map:
            target_map[ac] = {
                "asset_class": ac,
                "label": default_label,
                "target_pct": 0.0,
                "color": ASSET_CLASS_COLORS.get(ac, "#64748b"),
            }

    actual_by_class: Dict[str, float] = {ac: 0.0 for ac in ASSET_CLASS_LABELS}
    investment_wallets_list: List[Dict[str, Any]] = []

    for w in wallets:
        w_name = getattr(w, "name", "") if not isinstance(w, dict) else w.get("name", "")
        w_type = getattr(w, "type", "") if not isinstance(w, dict) else w.get("type", "")
        w_bal = float(getattr(w, "balance", 0.0) if not isinstance(w, dict) else w.get("balance", 0.0))
        w_id = getattr(w, "id", "") if not isinstance(w, dict) else w.get("id", "")
        w_explicit = getattr(w, "asset_class", None) if not isinstance(w, dict) else w.get("asset_class")

        ac = infer_wallet_asset_class(w_name, w_type, w_explicit)
        if ac:
            safe_bal = max(0.0, w_bal)
            actual_by_class[ac] = actual_by_class.get(ac, 0.0) + safe_bal
            investment_wallets_list.append({
                "id": w_id,
                "name": w_name,
                "type": w_type,
                "balance": round(safe_bal, 2),
                "asset_class": ac,
                "asset_class_label": ASSET_CLASS_LABELS.get(ac, ac),
            })

    total_investment = sum(actual_by_class.values())
    total_net_worth = max(0.0, total_investment + max(0.0, liquid_cash_balance))
    invested_ratio_pct = round((total_investment / total_net_worth) * 100, 1) if total_net_worth > 0 else 0.0

    # Emergency fund check
    target_ef_months = determine_emergency_target_months(is_married=is_married, dependents_count=dependents_count)
    target_ef_amount = max(0.0, monthly_expenses * target_ef_months)
    ef_months_covered = round(liquid_cash_balance / monthly_expenses, 1) if monthly_expenses > 0 else 0.0
    is_ef_sufficient = liquid_cash_balance >= target_ef_amount

    allocations_comparison: List[Dict[str, Any]] = []
    total_abs_drift = 0.0

    # Sort classes: those with target_pct > 0 or actual > 0 first
    ordered_classes = [item["asset_class"] for item in ref_model["allocations"]]
    for ac in ASSET_CLASS_LABELS:
        if ac not in ordered_classes:
            ordered_classes.append(ac)

    for ac in ordered_classes:
        meta = target_map[ac]
        actual_amt = actual_by_class.get(ac, 0.0)
        target_pct = meta["target_pct"]
        if total_investment > 0:
            actual_pct = round((actual_amt / total_investment) * 100, 1)
        else:
            actual_pct = 0.0

        if target_pct == 0.0 and actual_amt == 0.0:
            continue

        drift_pct = round(actual_pct - target_pct, 1)
        total_abs_drift += abs(drift_pct)
        ideal_amt = round(total_investment * (target_pct / 100.0), 2)
        delta_amt = round(ideal_amt - actual_amt, 2)  # positive means need to buy/add more

        if abs(drift_pct) <= 5.0:
            action = "IDEAL"
            status_text = "Sesuai Target"
        elif delta_amt > 0:
            action = "UNDERWEIGHT"
            status_text = "Kurang Alokasi (Tambah)"
        else:
            action = "OVERWEIGHT"
            status_text = "Kelebihan Alokasi (Kurangi/Tahan)"

        allocations_comparison.append({
            "asset_class": ac,
            "asset_class_label": ASSET_CLASS_LABELS.get(ac, ac),
            "reference_name": meta["label"],
            "color": meta["color"],
            "actual_amount": round(actual_amt, 2),
            "ideal_amount": ideal_amt,
            "delta_amount": delta_amt,
            "actual_pct": actual_pct,
            "target_pct": target_pct,
            "drift_pct": drift_pct,
            "action": action,
            "status_text": status_text,
        })

    # Compute alignment score (0-100)
    if total_investment <= 0:
        alignment_score = 0
        review_status = "BELUM_ADA_INVESTASI"
        review_status_label = "Belum Ada Saldo Investasi"
    else:
        # Total possible drift is 200 (100% in wrong class vs 100% target)
        raw_alignment = max(0.0, 100.0 - (total_abs_drift / 2.0))
        alignment_score = int(round(raw_alignment))
        # Penalty if sharia preference is true but user holds CRYPTO (>0)
        if sharia_preference and actual_by_class.get("CRYPTO", 0.0) > 0:
            alignment_score = max(0, alignment_score - 15)

        if alignment_score >= 80:
            review_status = "OPTIMAL"
            review_status_label = "Sudah Sesuai Best Practice"
        elif alignment_score >= 55:
            review_status = "PERLU_REBALANCING"
            review_status_label = "Perlu Rebalancing Portofolio"
        else:
            review_status = "PERINGATAN_RISIKO"
            review_status_label = "Deviasi Tinggi dari Profil Risiko"

    # Best Practice Financial Checklist & Actionable Insights
    best_practices: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    # 1. Check Emergency Fund Foundation
    if is_ef_sufficient:
        best_practices.append({
            "key": "EMERGENCY_FUND",
            "title": "Fondasi Dana Darurat Aman",
            "passed": True,
            "detail": f"Kas likuid mencakup {ef_months_covered} bulan pengeluaran (target minimal {target_ef_months} bulan).",
        })
    else:
        best_practices.append({
            "key": "EMERGENCY_FUND",
            "title": "Dana Darurat Belum Mencapai Target Ideal",
            "passed": False,
            "detail": f"Kas likuid baru mencakup {ef_months_covered} dari {target_ef_months} bulan pengeluaran. Prioritaskan instrumen likuid (Pasar Uang) sebelum menambah aset agresif.",
        })
        if total_investment > 0 and (actual_by_class.get("EQUITY", 0) + actual_by_class.get("CRYPTO", 0)) > 0:
            recommendations.append(
                f"Bangun dana darurat hingga {target_ef_months} bulan pengeluaran sebelum menambah porsi Saham/Crypto."
            )

    # 2. Check Invested Ratio vs Cash Drag
    if 20.0 <= invested_ratio_pct <= 85.0:
        best_practices.append({
            "key": "INVESTED_RATIO",
            "title": "Rasio Aset Produktif Ideal",
            "passed": True,
            "detail": f"{invested_ratio_pct}% dari total kekayaan bersih telah bekerja di instrumen investasi.",
        })
    elif invested_ratio_pct < 20.0:
        best_practices.append({
            "key": "INVESTED_RATIO",
            "title": "Terlalu Banyak Kas Mengendap (Cash Drag)",
            "passed": False,
            "detail": f"Baru {invested_ratio_pct}% kekayaan yang diinvestasikan. Setelah dana darurat aman, alokasikan surplus kas ke portofolio investasi agar tidak tergerus inflasi.",
        })
        recommendations.append(
            "Pindahkan sebagian dana mengendap dari rekening tabungan biasa ke instrumen investasi sesuai profil risiko."
        )
    else:
        best_practices.append({
            "key": "INVESTED_RATIO",
            "title": "Porsi Kas Likuid Sangat Tipis",
            "passed": is_ef_sufficient,
            "detail": f"{invested_ratio_pct}% kekayaan berada di aset investasi. Pastikan tetap memegang kas likuid yang cukup untuk kebutuhan mendadak.",
        })

    # 3. Check Diversification & Concentration Risk
    high_risk_pct = 0.0
    if total_investment > 0:
        high_risk_pct = round(((actual_by_class.get("EQUITY", 0.0) + actual_by_class.get("CRYPTO", 0.0)) / total_investment) * 100, 1)
    target_high_risk_pct = sum(
        item["percentage"] for item in ref_model["allocations"] if item.get("asset_class") in ("EQUITY", "CRYPTO")
    )

    if total_investment > 0 and abs(high_risk_pct - target_high_risk_pct) <= 15.0:
        best_practices.append({
            "key": "RISK_ALIGNMENT",
            "title": f"Eksposur Risiko Sesuai Profil ({(risk_tolerance or 'MODERATE').upper()})",
            "passed": True,
            "detail": f"Porsi aset agresif (Saham/Crypto) sebesar {high_risk_pct}% selaras dengan target referensi {target_high_risk_pct}%.",
        })
    elif total_investment > 0:
        is_too_aggressive = high_risk_pct > target_high_risk_pct + 15.0
        best_practices.append({
            "key": "RISK_ALIGNMENT",
            "title": "Eksposur Risiko Melebihi Batas Profil" if is_too_aggressive else "Portofolio Terlalu Konservatif dari Target",
            "passed": False,
            "detail": (
                f"Porsi aset agresif saat ini {high_risk_pct}% vs target {target_high_risk_pct}%. "
                + ("Volatilitas portofolio berisiko terlalu tinggi." if is_too_aggressive else "Potensi pertumbuhan jangka panjang menuju FIRE belum optimal.")
            ),
        })

    # Generate specific rebalancing step recommendations
    if total_investment > 0:
        for comp in allocations_comparison:
            if comp["action"] == "UNDERWEIGHT" and comp["delta_amount"] >= 50_000:
                fmt_delta = f"Rp {int(round(comp['delta_amount'])):,}".replace(",", ".")
                recommendations.append(
                    f"Tambah alokasi {comp['asset_class_label']} sekitar {fmt_delta} (aktual {comp['actual_pct']}% -> target {comp['target_pct']}%)."
                )
            elif comp["action"] == "OVERWEIGHT" and abs(comp["delta_amount"]) >= 50_000:
                fmt_delta = f"Rp {int(round(abs(comp['delta_amount']))):,}".replace(",", ".")
                recommendations.append(
                    f"Kurangi / tahan penambahan {comp['asset_class_label']} sebesar {fmt_delta} (aktual {comp['actual_pct']}% melebihi target {comp['target_pct']}%)."
                )
    else:
        recommendations.append(
            f"Buat atau isi saldo dompet bertipe INVESTMENT / RDN mengikuti referensi {ref_model['profile']} (CAGR {ref_model['expected_cagr']})."
        )

    return {
        "has_investment_wallets": len(investment_wallets_list) > 0,
        "investment_wallets_count": len(investment_wallets_list),
        "investment_wallets": investment_wallets_list,
        "total_investment_balance": round(total_investment, 2),
        "liquid_cash_balance": round(liquid_cash_balance, 2),
        "total_net_worth": round(total_net_worth, 2),
        "invested_ratio_pct": invested_ratio_pct,
        "risk_profile": (risk_tolerance or "MODERATE").upper(),
        "sharia_preference": bool(sharia_preference),
        "reference_profile_name": ref_model["profile"],
        "reference_description": ref_model["description"],
        "expected_cagr": ref_model["expected_cagr"],
        "alignment_score": alignment_score,
        "status": review_status,
        "status_label": review_status_label,
        "allocations_comparison": allocations_comparison,
        "best_practices": best_practices,
        "recommendations": recommendations,
    }
