import math
from typing import Dict, Any


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
                    {"asset": "Sukuk Negara Ritel (SR / ST / PBS)", "percentage": 45, "color": "#3b82f6"},
                    {"asset": "Reksa Dana Pasar Uang Syariah & Deposito Mudharabah", "percentage": 35, "color": "#10b981"},
                    {"asset": "Emas Fisik / Logam Mulia", "percentage": 15, "color": "#eab308"},
                    {"asset": "Saham Syariah Bluechip (JII / ISSI)", "percentage": 5, "color": "#8b5cf6"},
                ],
                "expected_cagr": "5.8% - 7.2%",
            }
        elif risk == "AGGRESSIVE":
            return {
                "profile": "Agresif Syariah (Pertumbuhan Ekuitas Halal)",
                "description": "Akselerasi kekayaan jangka panjang berbasis efek syariah terverifikasi DES/ISSI & emas.",
                "allocations": [
                    {"asset": "Saham Syariah Pilihan (ISSI / JII70)", "percentage": 55, "color": "#8b5cf6"},
                    {"asset": "Sukuk Negara / Project Based Sukuk (PBS)", "percentage": 20, "color": "#3b82f6"},
                    {"asset": "Emas Fisik / Logam Mulia", "percentage": 15, "color": "#eab308"},
                    {"asset": "Reksa Dana Pasar Uang Syariah (Kas Taktis)", "percentage": 10, "color": "#10b981"},
                ],
                "expected_cagr": "10.0% - 13.5%",
            }
        return {
            "profile": "Moderat Syariah (Pertumbuhan Berimbang Halal)",
            "description": "Kombinasi seimbang antara bagi hasil Sukuk Negara, ekuitas syariah, dan lindung nilai emas.",
            "allocations": [
                {"asset": "Saham & Reksa Dana Saham Syariah (JII / ISSI)", "percentage": 40, "color": "#8b5cf6"},
                {"asset": "Sukuk Negara (SR / ST / PBS)", "percentage": 35, "color": "#3b82f6"},
                {"asset": "Reksa Dana Pasar Uang Syariah", "percentage": 15, "color": "#10b981"},
                {"asset": "Emas Fisik / Antam", "percentage": 10, "color": "#eab308"},
            ],
            "expected_cagr": "8.0% - 10.0%",
        }

    if risk == "CONSERVATIVE":
        return {
            "profile": "Konservatif (Capital Preservation)",
            "description": "Fokus pada keamanan modal dan proteksi nilai aset dengan volatilitas sangat minim.",
            "allocations": [
                {"asset": "Obligasi Negara / SBN / Sukuk", "percentage": 45, "color": "#3b82f6"},
                {"asset": "Reksa Dana Pasar Uang & Deposito", "percentage": 30, "color": "#10b981"},
                {"asset": "Emas Logam Mulia", "percentage": 15, "color": "#eab308"},
                {"asset": "Saham Bluechip / Index Fund", "percentage": 10, "color": "#8b5cf6"},
            ],
            "expected_cagr": "6.0% - 7.5%",
        }
    elif risk == "AGGRESSIVE":
        return {
            "profile": "Agresif (Maximum Capital Growth)",
            "description": "Fokus pada pertumbuhan kekayaan jangka panjang dan siap menghadapi fluktuasi pasar.",
            "allocations": [
                {"asset": "Saham (IDX LQ45 & US Tech / S&P 500)", "percentage": 55, "color": "#8b5cf6"},
                {"asset": "Crypto (Bitcoin / Bluechip Crypto)", "percentage": 15, "color": "#f97316"},
                {"asset": "Obligasi Korporasi / SBN", "percentage": 15, "color": "#3b82f6"},
                {"asset": "Emas Logam Mulia", "percentage": 10, "color": "#eab308"},
                {"asset": "Pasar Uang / Kas Cadangan", "percentage": 5, "color": "#10b981"},
            ],
            "expected_cagr": "11.0% - 15.0%",
        }
    else:  # MODERATE
        return {
            "profile": "Moderat (Balanced Growth)",
            "description": "Keseimbangan ideal antara apresiasi modal jangka panjang dan stabilitas arus kas.",
            "allocations": [
                {"asset": "Saham & Reksa Dana Saham", "percentage": 40, "color": "#8b5cf6"},
                {"asset": "Obligasi Negara / SBN", "percentage": 30, "color": "#3b82f6"},
                {"asset": "Reksa Dana Pendapatan Tetap & Pasar Uang", "percentage": 15, "color": "#10b981"},
                {"asset": "Emas Fisik / Antam", "percentage": 10, "color": "#eab308"},
                {"asset": "Aset Alternatif / Crypto Pilihan", "percentage": 5, "color": "#f97316"},
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
