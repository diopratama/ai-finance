from types import SimpleNamespace

from app.services.fire_engine import (
    calculate_fire_metrics,
    determine_emergency_target_months,
    get_asset_allocation_recommendation,
)
from app.services.planner_skills_loader import (
    build_planner_system_prompt,
    calculate_profile_completeness,
    detect_pronoun_style,
    extract_and_update_profile_memory,
    route_planner_skills,
)


def _dummy_profile():
    return SimpleNamespace(
        current_age=28,
        target_fire_age=50,
        monthly_income=0.0,
        monthly_living_expense=10_000_000.0,
        monthly_debt_payment=0.0,
        marital_status="SINGLE",
        dependents_count=0,
        risk_tolerance="MODERATE",
        sharia_preference=False,
        memory_notes="",
        confirmed_profile_fields="[]",
        fire_target_amount=3_000_000_000.0,
        emergency_fund_target=30_000_000.0,
    )


def test_skill_router_selects_relevant_domains():
    r_debt = route_planner_skills("Gue ada cicilan KPR 4jt sama paylater 1jt, baiknya lunasin mana dulu?")
    assert "debt_and_credit" in r_debt["skill_ids"]
    assert "gue" in r_debt["pronoun_style"]

    r_sharia = route_planner_skills("Aku pengen mulai investasi syariah di Sukuk atau saham JII, gimana bagi porsinya?")
    assert "investment_allocation" in r_sharia["skill_ids"]

    r_goals = route_planner_skills("Gimana cara nyiapin dana kuliah anak 10 tahun lagi?")
    assert "life_goals_planning" in r_goals["skill_ids"]

    r_ef = route_planner_skills("Dana darurat ideal buat keluarga dan asuransi kesehatan murni apa yang penting?")
    assert "emergency_and_protection" in r_ef["skill_ids"]

    r_fire = route_planner_skills("Jelasin bedanya Coast FIRE dan Barista FIRE dong")
    assert "retirement_and_fire" in r_fire["skill_ids"]

    r_behav = route_planner_skills("Duh tiap malam suka lapar mata checkout keranjang kuning terus")
    assert "behavioral_coaching" in r_behav["skill_ids"]

    r_checkup = route_planner_skills("Tolong bedah total kondisi keuanganku sekarang, sehat nggak dan mulai dari mana?")
    assert r_checkup["skill_ids"][0] == "comprehensive_checkup"


def test_system_prompt_has_no_false_cfp_certification_claim():
    routing = route_planner_skills("Aku bingung ngatur gaji bulanan")
    prompt = build_planner_system_prompt(
        financial_context={
            "base_currency": "IDR",
            "net_worth_formatted": "Rp 25.000.000",
            "liquid_balance_formatted": "Rp 25.000.000",
            "monthly_income_formatted": "Rp 15.000.000",
            "monthly_expenses_formatted": "Rp 8.000.000",
            "monthly_debt_formatted": "Rp 0",
            "dsr_percentage": 0.0,
            "savings_margin_percentage": 46.7,
            "household_summary": "Lajang, 0 tanggungan",
            "emergency_fund_months": 3.1,
            "emergency_target_months": 3,
            "emergency_fund_status": "Memadai",
            "current_age": 28,
            "target_fire_age": 50,
            "fire_target_formatted": "Rp 2.400.000.000",
            "coast_fire_formatted": "Rp 540.000.000",
            "risk_profile": "MODERATE",
            "sharia_preference": True,
            "health_score": 85,
            "health_status": "EXCELLENT",
            "profile_completeness_pct": 60,
            "missing_profile_hints": ["Profil risiko investasi"],
        },
        routing=routing,
    )
    assert "[VERIFIED USER FINANCIAL SNAPSHOT]" in prompt
    assert "AI Financial Planner" in prompt
    assert "DILARANG KERAS" in prompt
    assert "Alex, Certified Financial Planner" not in prompt
    assert "AKTIF (Syariah Only" in prompt


def test_progressive_profiling_auto_capture_and_completeness():
    profile = _dummy_profile()
    initial = calculate_profile_completeness(profile, tx_income=0.0, tx_expense=0.0)
    assert initial["profile_completeness_pct"] == 0
    assert len(initial["missing_profile_hints"]) == 6

    msg = (
        "Halo! Aku umur 30, udah nikah dan punya 1 anak. "
        "Gaji aku 18,5 juta sebulan, pengeluaran bulanan 9 juta, ada cicilan 3,5 juta, "
        "profilku moderat dan pengen fokus syariah buat dana kuliah anak."
    )
    res = extract_and_update_profile_memory(msg, profile)
    assert res["updated"] is True
    assert profile.current_age == 30
    assert profile.marital_status == "MARRIED"
    assert profile.dependents_count == 1
    assert profile.monthly_income == 18_500_000.0
    assert profile.monthly_living_expense == 9_000_000.0
    assert profile.monthly_debt_payment == 3_500_000.0
    assert profile.risk_tolerance == "MODERATE"
    assert profile.sharia_preference is True
    assert "dana pendidikan anak" in profile.memory_notes

    after = calculate_profile_completeness(profile, tx_income=0.0, tx_expense=0.0)
    assert after["profile_completeness_pct"] == 100
    assert after["missing_profile_hints"] == []


def test_debt_free_and_single_explicit_confirmation():
    profile = _dummy_profile()
    res = extract_and_update_profile_memory("Gue masih single belum punya anak dan gak punya cicilan sama sekali", profile)
    assert res["updated"] is True
    assert profile.marital_status == "SINGLE"
    assert profile.dependents_count == 0
    assert profile.monthly_debt_payment == 0.0

    comp = calculate_profile_completeness(profile)
    assert comp["flags"]["household_ready"] is True
    assert comp["flags"]["debt_ready"] is True
    assert comp["profile_completeness_pct"] == 35


def test_sharia_allocations_and_dynamic_emergency_months():
    assert determine_emergency_target_months(is_married=False, dependents_count=0) == 3
    assert determine_emergency_target_months(is_married=True, dependents_count=0) == 6
    assert determine_emergency_target_months(is_married=True, dependents_count=1) == 9
    assert determine_emergency_target_months(is_married=True, dependents_count=2) == 12

    for risk in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
        sharia_alloc = get_asset_allocation_recommendation(risk, sharia_preference=True)
        assert sum(a["percentage"] for a in sharia_alloc["allocations"]) == 100
        assert "Syariah" in sharia_alloc["profile"]

    fire = calculate_fire_metrics(
        current_age=30,
        target_fire_age=50,
        monthly_expenses=10_000_000,
        current_net_worth=800_000_000,
        monthly_savings=5_000_000,
    )
    assert fire["coast_fire_number"] > 0
    assert fire["coast_fire_number"] < fire["fire_number"]
    assert fire["is_coast_fire_achieved"] is True

