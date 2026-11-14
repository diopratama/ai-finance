"""Real fundamental data providers for the Fundamental / On-Chain agents.

Fetches institutional-grade fundamentals from Financial Modeling Prep (FMP),
with deterministic financial-statement fallback via Yahoo Finance (especially for
IDX/IHSG equities), ETF metrics via Yahoo Finance, and long-term crypto
tokenomics/revenue via CoinGecko and DefiLlama. Short-term futures derivatives
data has been intentionally removed to maintain an investment-only horizon.
"""

import logging
import math
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait as wait_futures
from typing import Any, Callable, Dict, List, Optional

# pyrefly: ignore[missing-import]
import yfinance as yf

from app.config import settings
from app.investment_ai.cache_store import redis_get_json, redis_set_json
from app.investment_ai.market_data import (
    _http_get_json,
    _normalize_market,
    _safe_float,
    resolve_coingecko_id,
    resolve_yahoo_symbol,
)
from app.investment_ai.sharia_reference import ShariaReferenceError, get_issi_issuer, load_sharia_reference

logger = logging.getLogger(__name__)

# DSN-MUI / OJK financial screening thresholds.
SHARIA_MAX_DEBT_TO_ASSETS = 0.45
SHARIA_MAX_NON_HALAL_INCOME = 0.10

# Yahoo industry classifications that clearly conflict with the Sharia business screen.
# Coarse automatic flag, NOT a fatwa and NOT DES membership.
NON_HALAL_INDUSTRY_KEYWORDS = (
    "tobacco",
    "gambling",
    "casino",
    "brewer",
    "wineries",
    "distilleries",
)

# Finance sectors: Yahoo does NOT distinguish conventional from Islamic institutions
# (e.g. BRIS is Bank Syariah Indonesia but is classified "Banks - Regional"), so these
# can never be auto-failed on industry alone and require a manual check.
FINANCE_REVIEW_KEYWORDS = ("bank", "insurance", "credit services", "mortgage")

# Provider glitches (seen e.g. P/B of 15,250 for ADRO.JK) must not reach the LLM as facts.
MAX_PLAUSIBLE_PRICE_TO_BOOK = 500.0

SHARIA_DISCLAIMER = (
    "Status ISSI pada file referensi yang dipelihara pengguna TIDAK dapat diverifikasi live oleh aplikasi; "
    "Rasio di atas hanya indikatif (Total Debt Yahoo termasuk liabilitas sewa, bukan murni "
    "utang berbunga). Verifikasi status final di daftar DES OJK / IDX sebelum berinvestasi."
)

_CACHE_TTL = 900.0
_FAILURE_CACHE_TTL = 60.0
_DEFILLAMA_TTL = 3600.0
RECOMMENDATION_FUNDAMENTALS_STAGE_TIMEOUT = 12.0
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
_cache_key_locks: Dict[str, threading.Lock] = {}


def _cached(key: str, loader: Callable[[], Any], ttl: float = _CACHE_TTL) -> Any:
    with _cache_lock:
        key_lock = _cache_key_locks.setdefault(key, threading.Lock())
    with key_lock:
        now = time.monotonic()
        with _cache_lock:
            hit = _cache.get(key)
            if hit and now - hit["_ts"] < hit.get("_ttl", ttl):
                return hit["_data"]

        found_l2, l2_data = redis_get_json(f"fund:{key}")
        if found_l2:
            with _cache_lock:
                _cache[key] = {"_ts": time.monotonic(), "_ttl": ttl, "_data": l2_data}
            return l2_data

        data = loader()
        effective_ttl = (
            min(ttl, _FAILURE_CACHE_TTL)
            if isinstance(data, dict) and data.get("available") is False
            else ttl
        )
        with _cache_lock:
            _cache[key] = {"_ts": time.monotonic(), "_ttl": effective_ttl, "_data": data}
        redis_set_json(f"fund:{key}", data, effective_ttl)
        return data


def _fmt_num(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "UNAVAILABLE"
    return f"{value:,.{digits}f}{suffix}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "UNAVAILABLE"
    return f"{value * 100:.1f}%"


def _fmt_big(value: Optional[float]) -> str:
    if value is None:
        return "UNAVAILABLE"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(value) >= div:
            return f"{value / div:,.2f}{unit}"
    return f"{value:,.0f}"


def _fmt_usd(value: Optional[float]) -> str:
    """USD amount, or UNAVAILABLE without a dangling currency symbol."""
    if value is None:
        return "UNAVAILABLE"
    return f"${_fmt_big(value)}"


# ---------------------------------------------------------------------------
# Stocks (IHSG / US) via Financial Modeling Prep (FMP) + Yahoo Finance Statements
# ---------------------------------------------------------------------------


def _first_row(df: Any, names: List[str]) -> Optional[float]:
    """Latest value of the first matching statement row (yfinance columns: newest first)."""
    if df is None or getattr(df, "empty", True):
        return None
    for name in names:
        if name in df.index:
            series = df.loc[name].dropna()
            if len(series):
                return _safe_float(series.iloc[0])
    return None


def _statement_series(df: Any, names: List[str], limit: int = 5) -> List[float]:
    """Extracts up to ``limit`` annual values newest-first from a yfinance statement."""
    if df is None or getattr(df, "empty", True):
        return []
    for name in names:
        if name in df.index:
            series = df.loc[name].dropna()
            vals = [_safe_float(v) for v in series.iloc[:limit].tolist()]
            clean = [v for v in vals if v is not None]
            if clean:
                return clean
    return []


def _calc_cagr_from_series(newest_first: List[float]) -> Optional[float]:
    """Computes CAGR (decimal, e.g. 0.12 = 12%) from newest-first annual values."""
    if len(newest_first) < 2:
        return None
    end_val = newest_first[0]
    start_val = newest_first[-1]
    periods = len(newest_first) - 1
    if end_val <= 0 or start_val <= 0 or periods <= 0:
        return None
    try:
        cagr = (end_val / start_val) ** (1.0 / periods) - 1.0
        return cagr if math.isfinite(cagr) else None
    except Exception:
        return None


def _compute_piotroski_f_score(income: Any, balance_sheet: Any, cashflow: Any) -> Optional[int]:
    """Computes deterministic Piotroski F-Score (0-9) from multi-year statements."""
    if income is None or balance_sheet is None or getattr(income, "empty", True) or getattr(balance_sheet, "empty", True):
        return None

    ni_s = _statement_series(income, ["Net Income", "Net Income Common Stockholders"], 2)
    assets_s = _statement_series(balance_sheet, ["Total Assets"], 2)
    ocf_s = _statement_series(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"], 2)
    rev_s = _statement_series(income, ["Total Revenue", "Operating Revenue"], 2)
    gp_s = _statement_series(income, ["Gross Profit"], 2)
    ltd_s = _statement_series(balance_sheet, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 2)
    ca_s = _statement_series(balance_sheet, ["Current Assets"], 2)
    cl_s = _statement_series(balance_sheet, ["Current Liabilities"], 2)
    shares_s = _statement_series(balance_sheet, ["Ordinary Shares Number", "Share Issued"], 2)

    if not ni_s or not assets_s or assets_s[0] <= 0:
        return None

    score = 0
    evaluated = 0

    # 1. Positive ROA
    roa_curr = ni_s[0] / assets_s[0]
    evaluated += 1
    if roa_curr > 0:
        score += 1

    # 2. Positive Operating Cash Flow
    if ocf_s:
        evaluated += 1
        if ocf_s[0] > 0:
            score += 1

    # 3. Improving ROA
    if len(ni_s) >= 2 and len(assets_s) >= 2 and assets_s[1] > 0:
        evaluated += 1
        if roa_curr > (ni_s[1] / assets_s[1]):
            score += 1

    # 4. Accrual quality (OCF > Net Income)
    if ocf_s:
        evaluated += 1
        if ocf_s[0] > ni_s[0]:
            score += 1

    # 5. Lower Long-Term Debt to Assets ratio
    if len(ltd_s) >= 2 and len(assets_s) >= 2 and assets_s[1] > 0:
        evaluated += 1
        if (ltd_s[0] / assets_s[0]) <= (ltd_s[1] / assets_s[1]):
            score += 1

    # 6. Higher Current Ratio
    if len(ca_s) >= 2 and len(cl_s) >= 2 and cl_s[0] > 0 and cl_s[1] > 0:
        evaluated += 1
        if (ca_s[0] / cl_s[0]) > (ca_s[1] / cl_s[1]):
            score += 1

    # 7. No dilution in shares issued
    if len(shares_s) >= 2:
        evaluated += 1
        if shares_s[0] <= shares_s[1] * 1.005:
            score += 1

    # 8. Higher Gross Margin
    if len(gp_s) >= 2 and len(rev_s) >= 2 and rev_s[0] > 0 and rev_s[1] > 0:
        evaluated += 1
        if (gp_s[0] / rev_s[0]) > (gp_s[1] / rev_s[1]):
            score += 1

    # 9. Higher Asset Turnover
    if len(rev_s) >= 2 and len(assets_s) >= 2 and assets_s[1] > 0:
        evaluated += 1
        if (rev_s[0] / assets_s[0]) > (rev_s[1] / assets_s[1]):
            score += 1

    return score if evaluated >= 5 else None


def _compute_altman_z_score(
    income: Any, balance_sheet: Any, market_cap: Optional[float]
) -> Optional[float]:
    """Computes deterministic Altman Z-Score from financial statements."""
    if income is None or balance_sheet is None or market_cap is None or market_cap <= 0:
        return None
    total_assets = _first_row(balance_sheet, ["Total Assets"])
    total_liab = _first_row(balance_sheet, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
    if not total_assets or total_assets <= 0 or not total_liab or total_liab <= 0:
        return None
    ca = _first_row(balance_sheet, ["Current Assets"])
    cl = _first_row(balance_sheet, ["Current Liabilities"])
    retained = _first_row(balance_sheet, ["Retained Earnings"])
    ebit = _first_row(income, ["EBIT", "Operating Income"])
    rev = _first_row(income, ["Total Revenue", "Operating Revenue"])

    if ca is None or cl is None or retained is None or ebit is None or rev is None:
        return None

    a = (ca - cl) / total_assets
    b = retained / total_assets
    c = ebit / total_assets
    d = market_cap / total_liab
    e = rev / total_assets
    z = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e
    return round(z, 2) if math.isfinite(z) else None


def _compute_statement_dcf_and_graham(
    current_price: Optional[float],
    info: Dict[str, Any],
    fcf: Optional[float],
    net_debt: Optional[float],
    shares: Optional[float],
    growth_rate: Optional[float],
) -> Dict[str, Any]:
    """Fallback Intrinsic Value estimator using 5Y FCF DCF + Graham Number + target price."""
    dcf_val = None
    if fcf and fcf > 0 and shares and shares > 0:
        g = max(0.03, min(0.15, growth_rate if growth_rate is not None else 0.07))
        r = 0.105
        tg = 0.04
        pv = sum((fcf * ((1 + g) ** yr)) / ((1 + r) ** yr) for yr in range(1, 6))
        tv = (fcf * ((1 + g) ** 5) * (1 + tg)) / (r - tg)
        pv_tv = tv / ((1 + r) ** 5)
        equity_val = pv + pv_tv - (net_debt or 0.0)
        if equity_val > 0:
            dcf_val = equity_val / shares

    eps = _safe_float(info.get("trailingEps"))
    bvps = _safe_float(info.get("bookValue"))
    graham_val = None
    if eps is not None and bvps is not None and eps > 0 and bvps > 0:
        graham_val = math.sqrt(22.5 * eps * bvps)

    target_mean = _safe_float(info.get("targetMeanPrice"))
    candidates = [v for v in (dcf_val, graham_val, target_mean) if v is not None and v > 0]
    intrinsic = dcf_val if dcf_val is not None else (sum(candidates) / len(candidates) if candidates else None)

    mos_pct = None
    val_status = "UNAVAILABLE"
    if intrinsic and current_price and intrinsic > 0 and current_price > 0:
        mos_pct = round(((intrinsic - current_price) / intrinsic) * 100.0, 2)
        if mos_pct >= 15.0:
            val_status = "UNDERVALUED"
        elif mos_pct >= -15.0:
            val_status = "FAIR"
        else:
            val_status = "OVERVALUED"

    return {
        "dcf_fair_value": round(intrinsic, 2) if intrinsic is not None else None,
        "graham_number": round(graham_val, 2) if graham_val is not None else None,
        "margin_of_safety_pct": mos_pct,
        "valuation_signal": val_status,
        "fair_value_source": "Yahoo Statement DCF / Graham" if intrinsic is not None else None,
    }


def _fmp_get_json(
    stable_path: str,
    legacy_path: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Any]:
    """Fetches JSON from FMP preferring /stable/ and falling back cleanly to legacy paths."""
    api_key = (getattr(settings, "FMP_API_KEY", "") or "").strip()
    if not api_key:
        return None

    q = dict(params or {})
    q["apikey"] = api_key
    qs = urllib.parse.urlencode(q)
    urls = [f"https://financialmodelingprep.com/stable/{stable_path}?{qs}"]
    if legacy_path:
        urls.append(f"https://financialmodelingprep.com/api/{legacy_path}?apikey={api_key}")

    for url in urls:
        try:
            data = _http_get_json(url, timeout=6.0, max_retries=1)
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict) and data and "Error Message" not in data:
                return data
        except Exception as e:
            logger.debug("FMP endpoint unavailable (%s): %s", url.split("?")[0], e)
            continue
    return None


def fetch_fmp_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetches institutional DCF, growth, scores, and TTM metrics from FMP API."""
    clean_sym = symbol.strip().upper()
    if not (getattr(settings, "FMP_API_KEY", "") or "").strip():
        return {"available": False}

    def load() -> Dict[str, Any]:
        dcf_rows = _fmp_get_json(
            "discounted-cash-flow",
            f"v3/discounted-cash-flow/{urllib.parse.quote(clean_sym)}",
            {"symbol": clean_sym},
        )
        growth_rows = _fmp_get_json(
            "financial-growth",
            f"v3/financial-growth/{urllib.parse.quote(clean_sym)}",
            {"symbol": clean_sym, "limit": 5},
        )
        score_rows = _fmp_get_json(
            "financial-scores",
            f"v4/score",
            {"symbol": clean_sym},
        )
        km_rows = _fmp_get_json(
            "key-metrics-ttm",
            f"v3/key-metrics-ttm/{urllib.parse.quote(clean_sym)}",
            {"symbol": clean_sym},
        )
        ratio_rows = _fmp_get_json(
            "ratios-ttm",
            f"v3/ratios-ttm/{urllib.parse.quote(clean_sym)}",
            {"symbol": clean_sym},
        )

        out: Dict[str, Any] = {"symbol": clean_sym, "provider": "FMP"}

        if isinstance(dcf_rows, list) and dcf_rows:
            d0 = dcf_rows[0]
            dcf_val = _safe_float(d0.get("dcf"))
            stk_p = _safe_float(d0.get("Stock Price") or d0.get("stockPrice"))
            out["dcf_fair_value"] = round(dcf_val, 2) if dcf_val is not None else None
            out["fmp_stock_price"] = stk_p
            if dcf_val and stk_p and dcf_val > 0 and stk_p > 0:
                mos = round(((dcf_val - stk_p) / dcf_val) * 100.0, 2)
                out["margin_of_safety_pct"] = mos
                out["valuation_signal"] = (
                    "UNDERVALUED" if mos >= 15.0 else ("FAIR" if mos >= -15.0 else "OVERVALUED")
                )

        if isinstance(growth_rows, list) and growth_rows:
            g0 = growth_rows[0]
            out["revenue_growth_latest"] = _safe_float(g0.get("revenueGrowth"))
            out["net_income_growth_latest"] = _safe_float(g0.get("netIncomeGrowth"))
            out["eps_growth_latest"] = _safe_float(g0.get("epsgrowth") or g0.get("epsdilutedGrowth"))
            out["fcf_growth_latest"] = _safe_float(g0.get("freeCashFlowGrowth"))
            # FMP provides total 3Y/5Y per-share growth; convert to annualized CAGR if >-1
            def _to_cagr(total_g: Optional[float], yrs: int) -> Optional[float]:
                if total_g is None or total_g <= -0.99:
                    return None
                return round(((1.0 + total_g) ** (1.0 / yrs)) - 1.0, 4)

            rev_3y_raw = _safe_float(g0.get("threeYRevenueGrowthPerShare"))
            rev_5y_raw = _safe_float(g0.get("fiveYRevenueGrowthPerShare"))
            ni_3y_raw = _safe_float(g0.get("threeYNetIncomeGrowthPerShare"))
            ocf_3y_raw = _safe_float(g0.get("threeYOperatingCFGrowthPerShare"))
            out["revenue_cagr_3y"] = _to_cagr(rev_3y_raw, 3)
            out["revenue_cagr_5y"] = _to_cagr(rev_5y_raw, 5)
            out["net_income_cagr_3y"] = _to_cagr(ni_3y_raw, 3)
            out["fcf_cagr_3y"] = _to_cagr(ocf_3y_raw, 3) or _safe_float(g0.get("freeCashFlowGrowth"))
            div_5y_g = _safe_float(g0.get("fiveYDividendperShareGrowthPerShare"))
            out["dividend_growth_5y_cagr"] = _to_cagr(div_5y_g, 5)

        if isinstance(score_rows, list) and score_rows:
            s0 = score_rows[0]
            p_raw = s0.get("piotroskiScore")
            out["piotroski_f_score"] = int(p_raw) if p_raw is not None else None
            z_raw = _safe_float(s0.get("altmanZScore"))
            out["altman_z_score"] = round(z_raw, 2) if z_raw is not None else None

        if isinstance(km_rows, list) and km_rows:
            k0 = km_rows[0]
            out["roic"] = _safe_float(k0.get("returnOnInvestedCapitalTTM") or k0.get("roicTTM"))
            out["roe"] = _safe_float(k0.get("returnOnEquityTTM") or k0.get("roeTTM"))
            out["fcf_yield"] = _safe_float(k0.get("freeCashFlowYieldTTM"))
            out["graham_number"] = _safe_float(k0.get("grahamNumberTTM"))

        if isinstance(ratio_rows, list) and ratio_rows:
            r0 = ratio_rows[0]
            out["trailing_pe"] = _safe_float(r0.get("priceToEarningsRatioTTM") or r0.get("peRatioTTM"))
            out["price_to_book"] = _sane_price_to_book(_safe_float(r0.get("priceToBookRatioTTM")))
            out["debt_to_equity"] = _safe_float(r0.get("debtToEquityRatioTTM") or r0.get("debtEquityRatioTTM"))
            out["interest_coverage"] = _safe_float(r0.get("interestCoverageRatioTTM") or r0.get("interestCoverageTTM"))
            dy = _safe_float(r0.get("dividendYieldTTM") or r0.get("dividendYielTTM"))
            out["dividend_yield"] = dy * 100.0 if dy is not None and dy < 0.35 else dy
            out["payout_ratio"] = _safe_float(r0.get("dividendPayoutRatioTTM") or r0.get("payoutRatioTTM"))
            out["net_profit_margin"] = _safe_float(r0.get("netProfitMarginTTM"))

        has_any = any(
            out.get(k) is not None
            for k in ("dcf_fair_value", "piotroski_f_score", "altman_z_score", "roic", "revenue_cagr_3y")
        )
        out["available"] = has_any
        return out

    try:
        return _cached(f"fmp:{clean_sym}", load, ttl=3600.0)
    except Exception as e:
        logger.debug("FMP cached fetch failed for %s: %s", clean_sym, e)
        return {"symbol": clean_sym, "available": False}


def _sane_price_to_book(value: Optional[float]) -> Optional[float]:
    """Drops negative or absurd P/B values caused by provider data glitches."""
    if value is None or value < 0 or value > MAX_PLAUSIBLE_PRICE_TO_BOOK:
        return None
    return value


def get_sharia_reference_status(symbol: str) -> Dict[str, Any]:
    """Looks up ISSI membership only in the user-maintained local reference file."""
    try:
        reference = load_sharia_reference()
        issuer = get_issi_issuer(symbol)
    except ShariaReferenceError as e:
        logger.warning("ISSI reference lookup failed for %s: %s", symbol, e)
        return {
            "status": "UNAVAILABLE",
            "source_as_of": None,
            "valid_until": None,
            "source_name": None,
        }
    return {
        "status": issuer["issi_status"] if issuer else "NOT_IN_REFERENCE",
        "source_as_of": reference["source_as_of"],
        "valid_until": reference["valid_until"],
        "source_name": reference["source_name"],
    }


def _format_sharia_reference_block(symbol: str, reference_status: Dict[str, Any]) -> str:
    return (
        f"ISSI REFERENCE for {symbol} (manual local CSV; primary list used by this application, not an independent certification):\n"
        f"- ISSI status in supplied list: {reference_status['status']}\n"
        "- Source dates are informational only and are not required to use this list.\n"
        f"- Source: {reference_status.get('source_name') or 'UNAVAILABLE'}\n"
        f"- Source as-of: {reference_status.get('source_as_of') or 'UNSPECIFIED'} | "
        f"valid until: {reference_status.get('valid_until') or 'UNSPECIFIED'}\n"
        "- This reference does not establish JII/JII70 membership or a final Sharia ruling."
    )


def fetch_stock_fundamentals(yahoo_symbol: str) -> Dict[str, Any]:
    """Fetches institutional FMP fundamentals + Yahoo Finance financial statements fallback."""

    def load() -> Dict[str, Any]:
        fmp_data = fetch_fmp_fundamentals(yahoo_symbol)
        ticker = yf.Ticker(yahoo_symbol)

        info: Dict[str, Any] = {}
        try:
            info = ticker.info or {}
        except Exception as e:
            logger.warning("yfinance info failed for %s: %s", yahoo_symbol, e)

        balance_sheet = income = cashflow = None
        try:
            balance_sheet = ticker.balance_sheet
        except Exception as e:
            logger.warning("yfinance balance_sheet failed for %s: %s", yahoo_symbol, e)
        try:
            income = ticker.income_stmt
        except Exception as e:
            logger.warning("yfinance income_stmt failed for %s: %s", yahoo_symbol, e)
        try:
            cashflow = ticker.cashflow
        except Exception as e:
            logger.warning("yfinance cashflow failed for %s: %s", yahoo_symbol, e)

        period = None
        try:
            if balance_sheet is not None and not balance_sheet.empty:
                period = str(balance_sheet.columns[0].date())
        except Exception:
            period = None

        current_price = _safe_float(info.get("currentPrice") or info.get("regularMarketPrice") or fmp_data.get("fmp_stock_price"))
        rev_series = _statement_series(income, ["Total Revenue", "Operating Revenue"], 5)
        ni_series = _statement_series(income, ["Net Income", "Net Income Common Stockholders"], 5)
        eps_series = _statement_series(income, ["Diluted EPS", "Basic EPS"], 5)
        fcf_series = _statement_series(cashflow, ["Free Cash Flow"], 5)
        ocf_curr = _first_row(cashflow, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
        fcf_curr = _safe_float(info.get("freeCashflow")) or (fcf_series[0] if fcf_series else None)
        total_assets = _first_row(balance_sheet, ["Total Assets"])
        total_debt = _first_row(balance_sheet, ["Total Debt"])
        cash_eq = _first_row(balance_sheet, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
        equity = _first_row(balance_sheet, ["Stockholders Equity", "Common Stock Equity"])
        ebit = _first_row(income, ["EBIT", "Operating Income"])
        int_exp = _first_row(income, ["Interest Expense", "Interest Expense Non Operating"])
        shares = _safe_float(info.get("sharesOutstanding")) or _first_row(balance_sheet, ["Ordinary Shares Number", "Share Issued"])

        # Deterministic fallbacks for institutional metrics
        rev_cagr_3y = fmp_data.get("revenue_cagr_3y") or _calc_cagr_from_series(rev_series[:4])
        rev_cagr_5y = fmp_data.get("revenue_cagr_5y") or (_calc_cagr_from_series(rev_series) if len(rev_series) >= 4 else None)
        ni_cagr_3y = fmp_data.get("net_income_cagr_3y") or _calc_cagr_from_series(ni_series[:4])
        eps_cagr_3y = fmp_data.get("eps_growth_latest") or _calc_cagr_from_series(eps_series[:4])
        fcf_cagr_3y = fmp_data.get("fcf_cagr_3y") or _calc_cagr_from_series(fcf_series[:4])

        piotroski = fmp_data.get("piotroski_f_score")
        if piotroski is None:
            piotroski = _compute_piotroski_f_score(income, balance_sheet, cashflow)

        market_cap = _safe_float(info.get("marketCap"))
        altman_z = fmp_data.get("altman_z_score")
        if altman_z is None:
            altman_z = _compute_altman_z_score(income, balance_sheet, market_cap)

        roic = fmp_data.get("roic")
        if roic is None and ebit is not None and equity is not None:
            invested_cap = (total_debt or 0.0) + equity - (cash_eq or 0.0)
            if invested_cap > 0:
                nopat = ebit * 0.78  # Effective statutory tax rate approximation
                roic = nopat / invested_cap

        int_cov = fmp_data.get("interest_coverage")
        if int_cov is None and ebit is not None and int_exp is not None and abs(int_exp) > 0:
            int_cov = ebit / abs(int_exp)

        net_debt = (total_debt - (cash_eq or 0.0)) if total_debt is not None else None
        dcf_fallback = _compute_statement_dcf_and_graham(
            current_price, info, fcf_curr, net_debt, shares, rev_cagr_3y or _safe_float(info.get("revenueGrowth"))
        )

        dcf_fair = fmp_data.get("dcf_fair_value") or dcf_fallback.get("dcf_fair_value")
        mos_pct = fmp_data.get("margin_of_safety_pct")
        val_sig = fmp_data.get("valuation_signal")
        if dcf_fair and current_price and dcf_fair > 0 and current_price > 0 and mos_pct is None:
            mos_pct = round(((dcf_fair - current_price) / dcf_fair) * 100.0, 2)
            val_sig = "UNDERVALUED" if mos_pct >= 15.0 else ("FAIR" if mos_pct >= -15.0 else "OVERVALUED")
        elif val_sig is None:
            val_sig = dcf_fallback.get("valuation_signal", "UNAVAILABLE")

        div_yield = fmp_data.get("dividend_yield") or _safe_float(info.get("dividendYield"))
        div_5y_avg = _safe_float(info.get("fiveYearAvgDividendYield"))
        payout_ratio = fmp_data.get("payout_ratio") or _safe_float(info.get("payoutRatio"))

        result = {
            "symbol": yahoo_symbol,
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("financialCurrency") or info.get("currency"),
            "current_price": current_price,
            "market_cap": market_cap,
            "trailing_pe": fmp_data.get("trailing_pe") or _safe_float(info.get("trailingPE")),
            "forward_pe": _safe_float(info.get("forwardPE")),
            "price_to_book": fmp_data.get("price_to_book") or _sane_price_to_book(_safe_float(info.get("priceToBook"))),
            "roe": fmp_data.get("roe") or _safe_float(info.get("returnOnEquity")),
            "roic": roic,
            "profit_margin": fmp_data.get("net_profit_margin") or _safe_float(info.get("profitMargins")),
            "revenue_growth": fmp_data.get("revenue_growth_latest") or _safe_float(info.get("revenueGrowth")),
            "revenue_cagr_3y": rev_cagr_3y,
            "revenue_cagr_5y": rev_cagr_5y,
            "net_income_cagr_3y": ni_cagr_3y,
            "eps_cagr_3y": eps_cagr_3y,
            "fcf_cagr_3y": fcf_cagr_3y,
            "dividend_yield": div_yield,
            "dividend_5y_avg": div_5y_avg,
            "payout_ratio": payout_ratio,
            "free_cash_flow": fcf_curr,
            "operating_cash_flow": ocf_curr,
            "debt_to_equity": fmp_data.get("debt_to_equity") or _safe_float(info.get("debtToEquity")),
            "interest_coverage": round(int_cov, 2) if int_cov is not None else None,
            "piotroski_f_score": piotroski,
            "altman_z_score": altman_z,
            "dcf_fair_value": dcf_fair,
            "graham_number": fmp_data.get("graham_number") or dcf_fallback.get("graham_number"),
            "margin_of_safety_pct": mos_pct,
            "valuation_signal": val_sig,
            "fair_value_source": "FMP DCF" if fmp_data.get("dcf_fair_value") is not None else dcf_fallback.get("fair_value_source"),
            "fmp_used": bool(fmp_data.get("available")),
            "total_assets": total_assets,
            "total_debt": total_debt,
            "total_revenue": rev_series[0] if rev_series else None,
            "interest_income": _first_row(
                income, ["Interest Income", "Interest Income Non Operating"]
            ),
            "statement_period": period,
        }
        core = ("market_cap", "trailing_pe", "total_assets", "total_revenue", "roe", "piotroski_f_score")
        result["available"] = any(result.get(k) is not None for k in core)
        return result

    try:
        return _cached(f"stock:{yahoo_symbol}", load)
    except Exception as e:
        logger.warning("Stock fundamentals failed for %s: %s", yahoo_symbol, e)
        return {"symbol": yahoo_symbol, "available": False}


def evaluate_sharia_screen(f: Dict[str, Any]) -> Dict[str, Any]:
    """Ratio-based Sharia screen computed from real statements.

    Status values: LIKELY_FAIL_BUSINESS, FAIL_FINANCIAL_RATIO, MANUAL_CHECK_REQUIRED,
    INDICATIVE_PASS, UNVERIFIED.
    Never returns a definitive halal verdict - DES membership is not checkable here.
    """
    notes: List[str] = []
    status = "UNVERIFIED"

    industry = (f.get("industry") or "").lower()
    business_flag = next((k for k in NON_HALAL_INDUSTRY_KEYWORDS if k in industry), None)
    finance_flag = next((k for k in FINANCE_REVIEW_KEYWORDS if k in industry), None)
    if business_flag:
        notes.append(
            f"Industri '{f.get('industry')}' berpotensi bertentangan dengan screening bisnis syariah."
        )
    if finance_flag:
        notes.append(
            f"Industri '{f.get('industry')}': Yahoo tidak membedakan lembaga keuangan konvensional "
            "dan syariah (mis. Bank Syariah Indonesia tercatat sebagai 'Banks - Regional'). "
            "Rasio utang/aset tidak bermakna untuk lembaga keuangan; periksa akad dan status "
            "syariah emiten secara manual."
        )

    debt_ratio = None
    if f.get("total_debt") is not None and f.get("total_assets"):
        debt_ratio = f["total_debt"] / f["total_assets"]
    income_ratio = None
    if f.get("interest_income") is not None and f.get("total_revenue"):
        income_ratio = f["interest_income"] / f["total_revenue"]

    debt_ok = None if debt_ratio is None else debt_ratio <= SHARIA_MAX_DEBT_TO_ASSETS
    income_ok = None if income_ratio is None else income_ratio <= SHARIA_MAX_NON_HALAL_INCOME

    if business_flag:
        status = "LIKELY_FAIL_BUSINESS"
    elif income_ok is False or (debt_ok is False and not finance_flag):
        status = "FAIL_FINANCIAL_RATIO"
    elif finance_flag:
        status = "MANUAL_CHECK_REQUIRED"
    elif debt_ok and income_ok:
        status = "INDICATIVE_PASS"
    else:
        missing = []
        if debt_ratio is None:
            missing.append("rasio utang/aset")
        if income_ratio is None:
            missing.append("rasio pendapatan non-halal (data pendapatan bunga tidak tersedia)")
        if missing:
            notes.append("Tidak dapat dihitung: " + ", ".join(missing) + ".")

    return {
        "status": status,
        "debt_to_assets": debt_ratio,
        "non_halal_income_ratio": income_ratio,
        "statement_period": f.get("statement_period"),
        "notes": notes,
    }


def _format_sharia_block(screen: Dict[str, Any]) -> str:
    lines = [
        "SHARIA SCREEN (computed from real financial statements; indicative only):",
        f"- Status: {screen['status']}",
        f"- Total Debt / Total Assets: {_fmt_pct(screen['debt_to_assets'])} "
        f"(limit <= {SHARIA_MAX_DEBT_TO_ASSETS * 100:.0f}%)",
        f"- Interest income / Revenue: {_fmt_pct(screen['non_halal_income_ratio'])} "
        f"(limit <= {SHARIA_MAX_NON_HALAL_INCOME * 100:.0f}%)",
        f"- Statement period: {screen.get('statement_period') or 'UNAVAILABLE'}",
    ]
    lines.extend(f"- Note: {n}" for n in screen["notes"])
    lines.append(f"- {SHARIA_DISCLAIMER}")
    return "\n".join(lines)


def _format_stock_block(f: Dict[str, Any], sharia: Optional[Dict[str, Any]]) -> str:
    cur = f.get("currency") or "market currency"
    provider_label = "FMP Institutional + Yahoo Statements" if f.get("fmp_used") else "Yahoo Finance Statements + Deterministic DCF/Piotroski Engine"
    lines = [
        f"FUNDAMENTAL DATA for {f.get('symbol')} (source: {provider_label}; "
        f"latest reported period: {f.get('statement_period') or 'UNAVAILABLE'}):",
        f"- Company: {f.get('name') or 'UNAVAILABLE'} | Sector: {f.get('sector') or 'UNAVAILABLE'} "
        f"| Industry: {f.get('industry') or 'UNAVAILABLE'}",
        f"- Market cap: {_fmt_big(f.get('market_cap'))} {cur} | Current Ref Price: {_fmt_num(f.get('current_price'))} {cur}",
        f"- Intrinsic / DCF Fair Value: {_fmt_num(f.get('dcf_fair_value'))} {cur} ({f.get('fair_value_source') or 'N/A'}) "
        f"| Margin of Safety: {_fmt_num(f.get('margin_of_safety_pct'), 2, '%')} | Valuation Status: {f.get('valuation_signal') or 'UNAVAILABLE'}",
        f"- Financial Health: Piotroski F-Score={f.get('piotroski_f_score') if f.get('piotroski_f_score') is not None else 'UNAVAILABLE'}/9 "
        f"| Altman Z-Score={_fmt_num(f.get('altman_z_score'))}",
        f"- Multi-Year CAGR Growth: Revenue 3Y={_fmt_pct(f.get('revenue_cagr_3y'))} | Revenue 5Y={_fmt_pct(f.get('revenue_cagr_5y'))} "
        f"| Net Income 3Y={_fmt_pct(f.get('net_income_cagr_3y'))} | EPS 3Y/Latest={_fmt_pct(f.get('eps_cagr_3y'))} | FCF Growth={_fmt_pct(f.get('fcf_cagr_3y'))}",
        f"- Valuation Multiples: P/E trailing={_fmt_num(f.get('trailing_pe'))} | P/E forward={_fmt_num(f.get('forward_pe'))} "
        f"| P/B={_fmt_num(f.get('price_to_book'))} | Graham Number={_fmt_num(f.get('graham_number'))}",
        f"- Quality & Solvency: ROIC={_fmt_pct(f.get('roic'))} | ROE={_fmt_pct(f.get('roe'))} "
        f"| Net Margin={_fmt_pct(f.get('profit_margin'))} | Debt/Equity={_fmt_num(f.get('debt_to_equity'))} | Interest Coverage={_fmt_num(f.get('interest_coverage'))}x",
        f"- Dividend Profile: Current Yield={_fmt_num(f.get('dividend_yield'), 2, '%')} "
        f"| 5Y Avg Yield={_fmt_num(f.get('dividend_5y_avg'), 2, '%')} | Payout Ratio={_fmt_pct(f.get('payout_ratio'))}",
        f"- Cash Flow & Scale: Free Cash Flow={_fmt_big(f.get('free_cash_flow'))} | Total Assets={_fmt_big(f.get('total_assets'))} "
        f"| Total Debt={_fmt_big(f.get('total_debt'))} | Revenue={_fmt_big(f.get('total_revenue'))}",
        "- Peer benchmarks not supplied in this block are UNAVAILABLE; do not invent numbers.",
    ]
    if sharia is not None:
        lines.append(_format_sharia_block(sharia))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# US ETFs via Yahoo Finance
# ---------------------------------------------------------------------------


def _safe_etf_info(info: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Fetch the first available key from a yfinance info dict; returns None if absent."""
    for key in keys:
        value = info.get(key)
        if value not in (None, "", "N/A"):
            return value
    return None


def fetch_etf_fundamentals(symbol: str) -> Dict[str, Any]:
    """Fetches ETF-specific metrics from Yahoo Finance.

    P/E, ROE, revenue growth, and single-stock valuation are NOT relevant for ETFs.
    Holdings, sector weights, and NAV premium/discount are not fetched to avoid
    fragile / slow yfinance endpoints; they are reported as UNAVAILABLE.
    """

    def load() -> Dict[str, Any]:
        ticker = yf.Ticker(symbol)
        info: Dict[str, Any] = {}
        try:
            info = ticker.info or {}
        except Exception as e:
            logger.warning("yfinance ETF info failed for %s: %s", symbol, e)

        # Yahoo uses inconsistent keys for the same concept; try several.
        expense_keys = ("netExpenseRatio", "annualReportExpenseRatio", "expenseRatio")
        yield_keys = ("yield", "dividendYield")
        ytd_keys = ("ytdReturn",)
        three_year_keys = ("threeYearAverageReturn", "3yAverageReturn")
        five_year_keys = ("fiveYearAverageReturn", "5yAverageReturn")

        aum = _safe_float(_safe_etf_info(info, "totalAssets"))
        expense_ratio = _safe_float(_safe_etf_info(info, *expense_keys))
        yield_value = _safe_float(_safe_etf_info(info, *yield_keys))
        ytd_return = _safe_float(_safe_etf_info(info, *ytd_keys))
        three_year = _safe_float(_safe_etf_info(info, *three_year_keys))
        five_year = _safe_float(_safe_etf_info(info, *five_year_keys))
        beta = _safe_float(_safe_etf_info(info, "beta3Year"))

        result = {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName"),
            "category": info.get("category"),
            "fund_family": info.get("fundFamily"),
            "aum": aum,
            "expense_ratio": expense_ratio,
            "yield": yield_value,
            "ytd_return": ytd_return,
            "three_year_return": three_year,
            "five_year_return": five_year,
            "beta_3y": beta,
            "available": any(v is not None for v in (aum, expense_ratio, yield_value, ytd_return, three_year, five_year, beta)),
        }
        return result

    try:
        return _cached(f"etf:{symbol}", load)
    except Exception as e:
        logger.warning("ETF fundamentals failed for %s: %s", symbol, e)
        return {"symbol": symbol, "available": False}


def _format_etf_block(f: Dict[str, Any]) -> str:
    lines = [
        f"ETF FUNDAMENTAL DATA for {f.get('symbol')} (source: Yahoo Finance; point-in-time):",
        f"- Name: {f.get('name') or 'UNAVAILABLE'} | Category: {f.get('category') or 'UNAVAILABLE'} "
        f"| Fund family: {f.get('fund_family') or 'UNAVAILABLE'}",
        f"- AUM: {_fmt_usd(f.get('aum'))}",
        f"- Expense ratio: {_fmt_num(f.get('expense_ratio') and f['expense_ratio'] * 100, 2, '%')}",
        f"- Distribution yield: {_fmt_num(f.get('yield') and f['yield'] * 100, 2, '%')}",
        f"- Return YTD: {_fmt_num(f.get('ytd_return') and f['ytd_return'] * 100, 1, '%')} | "
        f"3Y avg: {_fmt_num(f.get('three_year_return') and f['three_year_return'] * 100, 1, '%')} "
        f"| 5Y avg: {_fmt_num(f.get('five_year_return') and f['five_year_return'] * 100, 1, '%')}",
        f"- Beta (3Y): {_fmt_num(f.get('beta_3y'))}",
        "- Holdings breakdown, sector weights, NAV premium/discount, and fund flows: UNAVAILABLE "
        "(not fetched by this application). Do not quote them from memory.",
        "- P/E, ROE, revenue growth, and single-stock valuation multiples are NOT relevant for ETFs.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Crypto Long-Term Fundamentals via CoinGecko + DefiLlama (Spot & Tokenomics Only)
# ---------------------------------------------------------------------------


def _defillama_protocols() -> List[Dict[str, Any]]:
    return _cached(
        "defillama:protocols",
        lambda: _http_get_json("https://api.llama.fi/protocols", timeout=20.0),
        ttl=_DEFILLAMA_TTL,
    )


def _defillama_protocol_fees(slug: str) -> Dict[str, Optional[float]]:
    """Best-effort protocol revenue and daily fees lookup from DefiLlama."""
    if not slug:
        return {"daily_fees_usd": None, "daily_revenue_usd": None, "total_30d_fees_usd": None}

    def load_fees() -> Dict[str, Optional[float]]:
        fees_val = None
        rev_val = None
        total30_val = None
        try:
            f_data = _http_get_json(
                f"https://api.llama.fi/summary/fees/{urllib.parse.quote(slug)}?dataType=dailyFees",
                timeout=6.0,
                max_retries=1,
            )
            if isinstance(f_data, dict):
                fees_val = _safe_float(f_data.get("total24h"))
                total30_val = _safe_float(f_data.get("total30d"))
        except Exception as e:
            logger.debug("DefiLlama fees unavailable for %s: %s", slug, e)
        try:
            r_data = _http_get_json(
                f"https://api.llama.fi/summary/fees/{urllib.parse.quote(slug)}?dataType=dailyRevenue",
                timeout=6.0,
                max_retries=1,
            )
            if isinstance(r_data, dict):
                rev_val = _safe_float(r_data.get("total24h"))
        except Exception as e:
            logger.debug("DefiLlama revenue unavailable for %s: %s", slug, e)
        return {
            "daily_fees_usd": fees_val,
            "daily_revenue_usd": rev_val,
            "total_30d_fees_usd": total30_val,
        }

    return _cached(f"defillama_fees:{slug}", load_fees, ttl=_DEFILLAMA_TTL)


def _defillama_for(cg_id: str) -> Optional[Dict[str, Any]]:
    try:
        for p in _defillama_protocols():
            if p.get("gecko_id") == cg_id and _safe_float(p.get("tvl")) is not None:
                slug = str(p.get("slug") or "")
                fees_info = _defillama_protocol_fees(slug) if slug else {}
                return {
                    "name": p.get("name"),
                    "slug": slug,
                    "category": p.get("category"),
                    "tvl": _safe_float(p.get("tvl")),
                    "change_1d": _safe_float(p.get("change_1d")),
                    "change_7d": _safe_float(p.get("change_7d")),
                    "chains": p.get("chains"),
                    "daily_fees_usd": fees_info.get("daily_fees_usd"),
                    "daily_revenue_usd": fees_info.get("daily_revenue_usd"),
                    "total_30d_fees_usd": fees_info.get("total_30d_fees_usd"),
                }
    except Exception as e:
        logger.warning("DefiLlama lookup failed for %s: %s", cg_id, e)
    return None


def _evaluate_token_dilution(
    market_cap: Optional[float], fdv: Optional[float], circ: Optional[float], max_sup: Optional[float]
) -> Dict[str, Any]:
    """Evaluates long-term token unlock / supply dilution risk from Market Cap vs FDV."""
    mcap_fdv = None
    if market_cap and fdv and fdv > 0:
        mcap_fdv = round(market_cap / fdv, 4)

    supply_issued = None
    if circ and max_sup and max_sup > 0:
        supply_issued = round(circ / max_sup, 4)

    dilution_risk = "UNAVAILABLE"
    ratio = mcap_fdv if mcap_fdv is not None else supply_issued
    if ratio is not None:
        if ratio >= 0.80:
            dilution_risk = "LOW (Mayoritas suplai beredar; risiko dilusi rendah)"
        elif ratio >= 0.50:
            dilution_risk = "MODERATE (Perhatikan jadwal unlock token menengah)"
        else:
            dilution_risk = "HIGH (FDV jauh di atas Market Cap; risiko dilusi tinggi)"

    return {
        "mcap_to_fdv_ratio": mcap_fdv,
        "supply_issued_pct": supply_issued,
        "dilution_risk": dilution_risk,
    }


def fetch_crypto_fundamentals(symbol: str) -> Dict[str, Any]:
    """Long-term Tokenomics + Supply Dilution (CoinGecko) and TVL / Protocol Revenue (DefiLlama)."""
    base = symbol.strip().upper().split("/")[0].split("-")[0]

    def load() -> Dict[str, Any]:
        try:
            cg_id = resolve_coingecko_id(symbol)
            if not cg_id:
                return {"symbol": symbol, "available": False}
            url = (
                "https://api.coingecko.com/api/v3/coins/"
                + urllib.parse.quote(cg_id)
                + "?localization=false&tickers=false&community_data=false"
                "&developer_data=true&sparkline=false"
            )
            data = _http_get_json(url, timeout=6.0, max_retries=1)
        except Exception as e:
            logger.warning("Crypto fundamentals failed for %s: %s", symbol, e)
            return {"symbol": symbol, "available": False}

        md = data.get("market_data", {}) or {}
        dev = data.get("developer_data", {}) or {}
        mcap = _safe_float((md.get("market_cap") or {}).get("usd"))
        fdv = _safe_float((md.get("fully_diluted_valuation") or {}).get("usd"))
        circ = _safe_float(md.get("circulating_supply"))
        tot = _safe_float(md.get("total_supply"))
        mx = _safe_float(md.get("max_supply"))
        dilution = _evaluate_token_dilution(mcap, fdv, circ, mx)

        return {
            "symbol": symbol,
            "available": True,
            "cg_id": cg_id,
            "name": data.get("name"),
            "categories": [c for c in (data.get("categories") or []) if c][:4],
            "market_cap": mcap,
            "fdv": fdv,
            "circulating_supply": circ,
            "total_supply": tot,
            "max_supply": mx,
            "mcap_to_fdv_ratio": dilution["mcap_to_fdv_ratio"],
            "supply_issued_pct": dilution["supply_issued_pct"],
            "dilution_risk": dilution["dilution_risk"],
            "ath_change_pct": _safe_float((md.get("ath_change_percentage") or {}).get("usd")),
            "change_7d": _safe_float(md.get("price_change_percentage_7d")),
            "change_30d": _safe_float(md.get("price_change_percentage_30d")),
            "commits_4w": dev.get("commit_count_4_weeks"),
            "stars": dev.get("stars"),
            "forks": dev.get("forks"),
            "defillama": _defillama_for(cg_id),
        }

    try:
        result = _cached(f"crypto:{base}", load)
    except Exception as e:
        logger.warning("Crypto fundamentals failed for %s: %s", symbol, e)
        result = {"symbol": symbol, "available": False}
    return dict(result)


def _format_crypto_block(f: Dict[str, Any]) -> str:
    if not f.get("available"):
        return (
            f"FUNDAMENTAL / TOKENOMICS DATA for {f.get('symbol')}: UNAVAILABLE "
            "(CoinGecko lookup failed). Do not quote tokenomics, TVL, or on-chain metrics."
        )
    circ, mx, tot = f.get("circulating_supply"), f.get("max_supply"), f.get("total_supply")
    lines = [
        f"FUNDAMENTAL / TOKENOMICS DATA for {f.get('symbol')} "
        "(sources: CoinGecko, DefiLlama; long-term investment focus):",
        f"- Name: {f.get('name')} | Categories: {', '.join(f.get('categories') or []) or 'UNAVAILABLE'}",
        f"- Market cap: {_fmt_usd(f.get('market_cap'))} | FDV: {_fmt_usd(f.get('fdv'))} "
        f"| MCap/FDV Ratio: {_fmt_pct(f.get('mcap_to_fdv_ratio'))}",
        f"- Supply Dilution Risk: {f.get('dilution_risk') or 'UNAVAILABLE'}",
        f"- Circulating supply: {_fmt_big(circ)} | Total supply: {_fmt_big(tot)} | "
        f"Max supply: {_fmt_big(mx)} | Circulating/Max: {_fmt_pct(f.get('supply_issued_pct'))}",
        f"- Long-Term Distance from ATH: {_fmt_num(f.get('ath_change_pct'), 1, '%')} "
        f"| 30d Change: {_fmt_num(f.get('change_30d'), 2, '%')}",
        f"- GitHub Dev Activity (CoinGecko): commits 4w={f.get('commits_4w') if f.get('commits_4w') is not None else 'UNAVAILABLE'}, "
        f"stars={f.get('stars') if f.get('stars') is not None else 'UNAVAILABLE'}, "
        f"forks={f.get('forks') if f.get('forks') is not None else 'UNAVAILABLE'}",
    ]
    llama = f.get("defillama")
    if llama:
        lines.append(
            f"- DefiLlama TVL & Revenue: TVL={_fmt_usd(llama.get('tvl'))} (1d {_fmt_num(llama.get('change_1d'), 2, '%')}, "
            f"7d {_fmt_num(llama.get('change_7d'), 2, '%')}) | Daily Fees={_fmt_usd(llama.get('daily_fees_usd'))} "
            f"| Daily Revenue={_fmt_usd(llama.get('daily_revenue_usd'))}; category={llama.get('category')}"
        )
    else:
        lines.append("- DefiLlama TVL & Protocol Revenue: UNAVAILABLE (asset is L1 store-of-value or not tracked as DeFi protocol)")
    lines.append(
        "- Futures Funding Rate & Open Interest: NOT USED (long-term investment focus excludes leverage derivatives)."
    )
    return "\n".join(lines)


def _format_onchain_block(symbol: str, f: Dict[str, Any]) -> str:
    """Formats long-term tokenomics, MCap/FDV dilution, supply, and DefiLlama TVL/revenue metrics."""
    lines = [
        f"ON-CHAIN & TOKENOMICS CONTEXT for {symbol} (sources: CoinGecko & DefiLlama; long-term investing):",
        f"- Market Cap: {_fmt_usd(f.get('market_cap'))} | Fully Diluted Valuation (FDV): {_fmt_usd(f.get('fdv'))}",
        f"- MCap / FDV Ratio: {_fmt_pct(f.get('mcap_to_fdv_ratio'))} | Dilution Risk Assessment: {f.get('dilution_risk') or 'UNAVAILABLE'}",
        f"- Circulating / Max Supply: {_fmt_pct(f.get('supply_issued_pct'))} "
        f"({ _fmt_big(f.get('circulating_supply')) } / { _fmt_big(f.get('max_supply')) })",
        f"- Distance from All-Time High (ATH): {_fmt_num(f.get('ath_change_pct'), 1, '%')}",
    ]

    llama = f.get("defillama")
    if llama:
        lines.append(
            f"- DefiLlama TVL: {_fmt_usd(llama.get('tvl'))} "
            f"(1d {_fmt_num(llama.get('change_1d'), 2, '%')}, 7d {_fmt_num(llama.get('change_7d'), 2, '%')}); "
            f"category={llama.get('category') or 'UNAVAILABLE'}; chains={', '.join(llama.get('chains') or []) or 'UNAVAILABLE'}"
        )
        lines.append(
            f"- DefiLlama Protocol Economics: Daily Fees={_fmt_usd(llama.get('daily_fees_usd'))} | "
            f"Daily Protocol Revenue={_fmt_usd(llama.get('daily_revenue_usd'))} | 30d Fees={_fmt_usd(llama.get('total_30d_fees_usd'))}"
        )
    else:
        lines.append("- DefiLlama TVL & Protocol Revenue: UNAVAILABLE (asset is not a tracked DeFi protocol)")

    lines.extend([
        "- Whale wallet movements, exchange net-flows, active addresses, TX count, stablecoin mint/burn: UNAVAILABLE "
        "(no Glassnode / Whale Alert / Etherscan integration). Do not invent these metrics.",
        "- Futures leverage / perpetual funding rate / open interest intentionally excluded (non-speculative wealth compounding scope).",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def get_fundamental_context(market: str, symbol: str) -> Dict[str, Any]:
    """Builds the real-data block + raw institutional metrics for single-asset research."""
    norm = _normalize_market(market)
    if norm == "crypto":
        f = fetch_crypto_fundamentals(symbol)
        return {"text": _format_crypto_block(f), "available": bool(f.get("available")), "sharia": None, "sharia_reference": None, "raw": f}

    if norm == "us_etf":
        f = fetch_etf_fundamentals(symbol)
        return {"text": _format_etf_block(f), "available": bool(f.get("available")), "sharia": None, "sharia_reference": None, "raw": f}

    f = fetch_stock_fundamentals(resolve_yahoo_symbol(market, symbol))
    is_ihsg = norm == "ihsg"
    sharia_reference = get_sharia_reference_status(symbol) if is_ihsg else None
    if not f.get("available"):
        text = (
            f"FUNDAMENTAL DATA for {symbol}: UNAVAILABLE (FMP & Yahoo Finance returned no statements). "
            "Do not quote valuation multiples, ratios, or financial results from memory."
        )
        if is_ihsg:
            text += (
                "\nSHARIA SCREEN: UNVERIFIED. No financial statements were retrieved, so debt/assets "
                "and non-halal income ratios cannot be computed. Do NOT state that the stock is "
                "certified Sharia-compliant."
            )
            text += "\n" + _format_sharia_reference_block(symbol, sharia_reference)
        return {"text": text, "available": False, "sharia": None, "sharia_reference": sharia_reference, "raw": f}

    sharia = evaluate_sharia_screen(f) if is_ihsg else None
    text = _format_stock_block(f, sharia)
    if sharia_reference:
        text += "\n" + _format_sharia_reference_block(symbol, sharia_reference)
    return {"text": text, "available": True, "sharia": sharia, "sharia_reference": sharia_reference, "raw": f}


def get_onchain_context(market: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Builds a long-term tokenomics & DefiLlama TVL/Revenue context for the on-chain analyst."""
    if _normalize_market(market) != "crypto":
        return None
    f = fetch_crypto_fundamentals(symbol)
    return {
        "text": _format_onchain_block(symbol, f),
        "available": bool(f.get("available") or f.get("defillama")),
        "raw": f,
    }


def get_recommendation_fundamentals(market: str, symbols: List[str]) -> str:
    """Compact per-asset real fundamentals for the Quality, Value & Compounding Screener."""
    norm = _normalize_market(market)
    if not symbols:
        return ""

    if norm == "crypto":
        def one(sym: str) -> str:
            f = fetch_crypto_fundamentals(sym)
            if not f.get("available"):
                return f"- {sym}: fundamentals UNAVAILABLE"
            llama = f.get("defillama") or {}
            return (
                f"- {sym}: mcap={_fmt_usd(f.get('market_cap'))}, FDV={_fmt_usd(f.get('fdv'))}, "
                f"MCap/FDV={_fmt_pct(f.get('mcap_to_fdv_ratio'))}, "
                f"circ/max={_fmt_pct(f.get('supply_issued_pct'))}, "
                f"TVL={_fmt_usd(llama.get('tvl'))}, daily_rev={_fmt_usd(llama.get('daily_revenue_usd'))}"
            )
    elif norm == "us_etf":
        def one(sym: str) -> str:
            f = fetch_etf_fundamentals(sym)
            if not f.get("available"):
                return f"- {sym}: ETF fundamentals UNAVAILABLE"
            return (
                f"- {sym}: category={f.get('category') or 'UNAVAILABLE'}, "
                f"AUM={_fmt_big(f.get('aum'))} USD, "
                f"expense={_fmt_pct(f.get('expense_ratio'))}, "
                f"yield={_fmt_pct(f.get('yield'))}, "
                f"ytd={_fmt_pct(f.get('ytd_return'))}, "
                f"3y={_fmt_pct(f.get('three_year_return'))}, "
                f"5y={_fmt_pct(f.get('five_year_return'))}"
            )
    else:
        syariah = market == "ihsg_syariah"

        def one(sym: str) -> str:
            sharia_reference = get_sharia_reference_status(sym) if syariah else None
            f = fetch_stock_fundamentals(resolve_yahoo_symbol(market, sym))
            if not f.get("available"):
                suffix = " | SHARIA SCREEN: UNVERIFIED (no statements)" if syariah else ""
                if syariah and sharia_reference:
                    suffix += (
                        f" | supplied ISSI reference={sharia_reference['status']} "
                        f"(manual list; source_as_of={sharia_reference['source_as_of'] or 'UNSPECIFIED'})"
                    )
                return f"- {sym}: fundamentals UNAVAILABLE{suffix}"
            line = (
                f"- {sym}: industry={f.get('industry') or 'UNAVAILABLE'}, "
                f"FairVal={_fmt_num(f.get('dcf_fair_value'))}, MoS={_fmt_num(f.get('margin_of_safety_pct'), 1, '%')}, "
                f"F-Score={f.get('piotroski_f_score') if f.get('piotroski_f_score') is not None else 'UNAVAILABLE'}/9, "
                f"ROIC={_fmt_pct(f.get('roic'))}, ROE={_fmt_pct(f.get('roe'))}, "
                f"P/E={_fmt_num(f.get('trailing_pe'))}, DivYield={_fmt_num(f.get('dividend_yield'), 2, '%')}, "
                f"Rev3Y_CAGR={_fmt_pct(f.get('revenue_cagr_3y'))}"
            )
            if syariah:
                s = evaluate_sharia_screen(f)
                line += (
                    f" | SHARIA SCREEN={s['status']} (debt/assets={_fmt_pct(s['debt_to_assets'])}, "
                    f"interest income/revenue={_fmt_pct(s['non_halal_income_ratio'])})"
                )
                line += (
                    f" | supplied ISSI reference={sharia_reference['status']} "
                    f"(manual list; source_as_of={sharia_reference['source_as_of'] or 'UNSPECIFIED'})"
                )
            return line

    pool = ThreadPoolExecutor(max_workers=min(6, len(symbols)))
    try:
        sym_to_future = {sym: pool.submit(one, sym) for sym in symbols}
        done, _not_done = wait_futures(
            list(sym_to_future.values()),
            timeout=RECOMMENDATION_FUNDAMENTALS_STAGE_TIMEOUT,
        )
        lines = []
        for sym in symbols:
            fut = sym_to_future[sym]
            if fut not in done:
                logger.warning(
                    "Fundamental lookup exceeded %.1fs stage budget for %s",
                    RECOMMENDATION_FUNDAMENTALS_STAGE_TIMEOUT,
                    sym,
                )
                lines.append(f"- {sym}: fundamentals UNAVAILABLE (timeout)")
                continue
            try:
                lines.append(fut.result(timeout=0))
            except Exception as e:
                logger.warning("Fundamental lookup failed for %s: %s", sym, e)
                lines.append(f"- {sym}: fundamentals UNAVAILABLE")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    header = (
        "REAL FUNDAMENTAL DATA (FMP Institutional + Yahoo Statements / CoinGecko / DefiLlama). "
        "Any metric not listed here is UNAVAILABLE and must not be quoted from memory."
    )
    if market == "ihsg_syariah":
        header += " " + SHARIA_DISCLAIMER + " JII/JII70 membership is not present in the supplied CSV."
    if market == "us_etf":
        header = (
            "REAL ETF FUNDAMENTAL DATA (Yahoo Finance ETF metrics). "
            "P/E, ROE, revenue growth, and single-stock valuation are NOT relevant for ETFs. "
            "Any metric not listed here is UNAVAILABLE and must not be quoted from memory."
        )
    return header + "\n" + "\n".join(lines)
