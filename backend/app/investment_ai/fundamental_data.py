"""Real fundamental data providers for the Fundamental / On-Chain agents.

Before this module existed the agent skills referenced tools (``fetch_idx_financials``,
``check_sharia_compliance``, ``fetch_tokenomics`` ...) that were never implemented, so
the LLM filled P/E, ROE, TVL or "halal status" from memory. Everything here is fetched
from a real provider (Yahoo Finance statements, CoinGecko, DefiLlama, Binance Futures).
When a value cannot be fetched it is reported as UNAVAILABLE, never estimated.
"""

import logging
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait as wait_futures
from typing import Any, Callable, Dict, List, Optional

# pyrefly: ignore[missing-import]
import yfinance as yf

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
# Stocks (IHSG / US) via Yahoo Finance statements
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
    """Fetches valuation + balance sheet/income statement data for one stock."""

    def load() -> Dict[str, Any]:
        ticker = yf.Ticker(yahoo_symbol)

        info: Dict[str, Any] = {}
        try:
            info = ticker.info or {}
        except Exception as e:
            logger.warning("yfinance info failed for %s: %s", yahoo_symbol, e)

        balance_sheet = income = None
        try:
            balance_sheet = ticker.balance_sheet
        except Exception as e:
            logger.warning("yfinance balance_sheet failed for %s: %s", yahoo_symbol, e)
        try:
            income = ticker.income_stmt
        except Exception as e:
            logger.warning("yfinance income_stmt failed for %s: %s", yahoo_symbol, e)

        period = None
        try:
            if balance_sheet is not None and not balance_sheet.empty:
                period = str(balance_sheet.columns[0].date())
        except Exception:
            period = None

        result = {
            "symbol": yahoo_symbol,
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "currency": info.get("financialCurrency") or info.get("currency"),
            "market_cap": _safe_float(info.get("marketCap")),
            "trailing_pe": _safe_float(info.get("trailingPE")),
            "forward_pe": _safe_float(info.get("forwardPE")),
            "price_to_book": _sane_price_to_book(_safe_float(info.get("priceToBook"))),
            "roe": _safe_float(info.get("returnOnEquity")),
            "profit_margin": _safe_float(info.get("profitMargins")),
            "revenue_growth": _safe_float(info.get("revenueGrowth")),
            "dividend_yield": _safe_float(info.get("dividendYield")),
            "free_cash_flow": _safe_float(info.get("freeCashflow")),
            "debt_to_equity": _safe_float(info.get("debtToEquity")),
            "total_assets": _first_row(balance_sheet, ["Total Assets"]),
            "total_debt": _first_row(balance_sheet, ["Total Debt"]),
            "total_revenue": _first_row(income, ["Total Revenue", "Operating Revenue"]),
            "interest_income": _first_row(
                income, ["Interest Income", "Interest Income Non Operating"]
            ),
            "statement_period": period,
        }
        core = ("market_cap", "trailing_pe", "total_assets", "total_revenue", "roe")
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
    lines = [
        f"FUNDAMENTAL DATA for {f.get('symbol')} (source: Yahoo Finance statements; "
        f"latest reported period: {f.get('statement_period') or 'UNAVAILABLE'}):",
        f"- Company: {f.get('name') or 'UNAVAILABLE'} | Sector: {f.get('sector') or 'UNAVAILABLE'} "
        f"| Industry: {f.get('industry') or 'UNAVAILABLE'}",
        f"- Market cap: {_fmt_big(f.get('market_cap'))} {cur}",
        f"- P/E trailing: {_fmt_num(f.get('trailing_pe'))} | P/E forward: {_fmt_num(f.get('forward_pe'))} "
        f"| P/B: {_fmt_num(f.get('price_to_book'))}",
        f"- ROE: {_fmt_pct(f.get('roe'))} | Profit margin: {_fmt_pct(f.get('profit_margin'))} "
        f"| Revenue growth: {_fmt_pct(f.get('revenue_growth'))}",
        f"- Debt/Equity: {_fmt_num(f.get('debt_to_equity'))} | Free cash flow: {_fmt_big(f.get('free_cash_flow'))}",
        f"- Total assets: {_fmt_big(f.get('total_assets'))} | Total debt: {_fmt_big(f.get('total_debt'))} "
        f"| Revenue: {_fmt_big(f.get('total_revenue'))}",
        f"- Dividend yield: {_fmt_num(f.get('dividend_yield'), 2, '%')} (Yahoo-reported, percent)",
        "- Peer/industry benchmark multiples, SEC filings text, and analyst consensus are "
        "UNAVAILABLE: do not quote them.",
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
# Crypto via CoinGecko / DefiLlama / Binance Futures
# ---------------------------------------------------------------------------


def _defillama_protocols() -> List[Dict[str, Any]]:
    return _cached(
        "defillama:protocols",
        lambda: _http_get_json("https://api.llama.fi/protocols", timeout=20.0),
        ttl=_DEFILLAMA_TTL,
    )


def _defillama_for(cg_id: str) -> Optional[Dict[str, Any]]:
    try:
        for p in _defillama_protocols():
            if p.get("gecko_id") == cg_id and _safe_float(p.get("tvl")) is not None:
                return {
                    "name": p.get("name"),
                    "category": p.get("category"),
                    "tvl": _safe_float(p.get("tvl")),
                    "change_1d": _safe_float(p.get("change_1d")),
                    "change_7d": _safe_float(p.get("change_7d")),
                    "chains": p.get("chains"),
                }
    except Exception as e:
        logger.warning("DefiLlama lookup failed for %s: %s", cg_id, e)
    return None


def _binance_futures(base: str) -> Optional[Dict[str, Any]]:
    """Funding rate and open interest (public endpoints; supports micro-tokens like 1000PEPE)."""
    raw_base = base.upper()
    candidate_symbols = [f"{raw_base}USDT"]
    # Common Binance micro-cap futures multiplier prefix
    if not raw_base.startswith("1000"):
        candidate_symbols.append(f"1000{raw_base}USDT")

    for sym in candidate_symbols:
        try:
            prem = _http_get_json(
                f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={sym}", timeout=6.0, max_retries=1
            )
            oi = _http_get_json(
                f"https://fapi.binance.com/fapi/v1/openInterest?symbol={sym}", timeout=6.0, max_retries=1
            )
            return {
                "futures_symbol": sym,
                "funding_rate": _safe_float(prem.get("lastFundingRate")),
                "mark_price": _safe_float(prem.get("markPrice")),
                "open_interest": _safe_float(oi.get("openInterest")),
            }
        except Exception as e:
            logger.debug("Binance futures lookup failed for %s: %s", sym, e)
            continue

    logger.info("Binance futures data unavailable for %s (tried %s)", base, candidate_symbols)
    return None


def fetch_crypto_fundamentals(symbol: str) -> Dict[str, Any]:
    """Tokenomics + developer activity (CoinGecko), TVL (DefiLlama), derivatives (Binance)."""
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
        return {
            "symbol": symbol,
            "available": True,
            "cg_id": cg_id,
            "name": data.get("name"),
            "categories": [c for c in (data.get("categories") or []) if c][:4],
            "market_cap": _safe_float((md.get("market_cap") or {}).get("usd")),
            "fdv": _safe_float((md.get("fully_diluted_valuation") or {}).get("usd")),
            "circulating_supply": _safe_float(md.get("circulating_supply")),
            "total_supply": _safe_float(md.get("total_supply")),
            "max_supply": _safe_float(md.get("max_supply")),
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
    result = dict(result)
    result["futures"] = _cached(f"futures:{base}", lambda: _binance_futures(base), ttl=120.0)
    return result


def _format_crypto_block(f: Dict[str, Any]) -> str:
    if not f.get("available"):
        return (
            f"FUNDAMENTAL / ON-CHAIN DATA for {f.get('symbol')}: UNAVAILABLE "
            "(CoinGecko lookup failed). Do not quote tokenomics, TVL, or on-chain metrics."
        )
    circ, mx, tot = f.get("circulating_supply"), f.get("max_supply"), f.get("total_supply")
    circ_pct = (circ / mx) if circ and mx else None
    lines = [
        f"FUNDAMENTAL / ON-CHAIN DATA for {f.get('symbol')} "
        "(sources: CoinGecko, DefiLlama, Binance Futures; point-in-time):",
        f"- Name: {f.get('name')} | Categories: {', '.join(f.get('categories') or []) or 'UNAVAILABLE'}",
        f"- Market cap: {_fmt_usd(f.get('market_cap'))} | FDV: {_fmt_usd(f.get('fdv'))}",
        f"- Circulating supply: {_fmt_big(circ)} | Total supply: {_fmt_big(tot)} | "
        f"Max supply: {_fmt_big(mx)} | Circulating/Max: {_fmt_pct(circ_pct)}",
        f"- Price change 7d: {_fmt_num(f.get('change_7d'), 2, '%')} | 30d: "
        f"{_fmt_num(f.get('change_30d'), 2, '%')} | From ATH: {_fmt_num(f.get('ath_change_pct'), 1, '%')}",
        f"- GitHub (CoinGecko): commits 4w={f.get('commits_4w') if f.get('commits_4w') is not None else 'UNAVAILABLE'}, "
        f"stars={f.get('stars') if f.get('stars') is not None else 'UNAVAILABLE'}, "
        f"forks={f.get('forks') if f.get('forks') is not None else 'UNAVAILABLE'}",
    ]
    llama = f.get("defillama")
    if llama:
        lines.append(
            f"- DefiLlama TVL: {_fmt_usd(llama.get('tvl'))} (1d {_fmt_num(llama.get('change_1d'), 2, '%')}, "
            f"7d {_fmt_num(llama.get('change_7d'), 2, '%')}); category={llama.get('category')}"
        )
    else:
        lines.append("- DefiLlama TVL: UNAVAILABLE (asset is not a tracked DeFi protocol or lookup failed)")
    fut = f.get("futures")
    if fut:
        lines.append(
            f"- Binance perpetual: funding rate={_fmt_num(fut.get('funding_rate') and fut['funding_rate'] * 100, 4, '%')}, "
            f"open interest={_fmt_big(fut.get('open_interest'))} units"
        )
    else:
        lines.append("- Binance perpetual funding/open interest: UNAVAILABLE")
    lines.append(
        "- Whale wallet movements, exchange net-flows, and holder distribution: UNAVAILABLE "
        "(no Glassnode / Whale Alert / Etherscan integration). State this explicitly; do NOT "
        "invent whale transactions, inflow/outflow numbers, or addresses."
    )
    return "\n".join(lines)


def _format_onchain_block(symbol: str, f: Dict[str, Any]) -> str:
    """Formats derivatives + DeFi metrics from existing providers for the on-chain analyst."""
    base = symbol.strip().upper().split("/")[0].split("-")[0]
    lines = [
        f"ON-CHAIN / DERIVATIVES CONTEXT for {symbol} (no new APIs; uses data already fetched by backend):",
        "- Whale wallet movements, exchange net-flows, active addresses, TX count, stablecoin mint/burn: UNAVAILABLE "
        "(no Glassnode / Whale Alert / Etherscan / stablecoin-issuer integration). Do not invent these metrics.",
    ]

    fut = f.get("futures")
    if fut:
        lines.append(
            f"- Binance perpetual (public): funding_rate={_fmt_num(fut.get('funding_rate') and fut['funding_rate'] * 100, 4, '%')}, "
            f"open_interest={_fmt_big(fut.get('open_interest'))} {base}, mark_price={_fmt_num(fut.get('mark_price'))}"
        )
    else:
        lines.append("- Binance perpetual funding rate / open interest: UNAVAILABLE")

    llama = f.get("defillama")
    if llama:
        lines.append(
            f"- DefiLlama TVL (if asset is a tracked DeFi protocol): {_fmt_usd(llama.get('tvl'))} "
            f"(1d {_fmt_num(llama.get('change_1d'), 2, '%')}, 7d {_fmt_num(llama.get('change_7d'), 2, '%')}); "
            f"category={llama.get('category') or 'UNAVAILABLE'}; chains={', '.join(llama.get('chains') or []) or 'UNAVAILABLE'}"
        )
    else:
        lines.append("- DefiLlama TVL: UNAVAILABLE (asset is not a tracked DeFi protocol or lookup failed)")

    lines.append(
        "- Use only the metrics above and the supplied market/news context. "
        "Do not present exchange flows, whale transfers, active addresses, or stablecoin flows as available."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def get_fundamental_context(market: str, symbol: str) -> Dict[str, Any]:
    """Builds the real-data block for a single-asset analysis.

    Returns ``{"text": str, "available": bool, "sharia": Optional[dict]}``.
    """
    norm = _normalize_market(market)
    if norm == "crypto":
        f = fetch_crypto_fundamentals(symbol)
        return {"text": _format_crypto_block(f), "available": bool(f.get("available")), "sharia": None, "sharia_reference": None}

    if norm == "us_etf":
        f = fetch_etf_fundamentals(symbol)
        return {"text": _format_etf_block(f), "available": bool(f.get("available")), "sharia": None, "sharia_reference": None}

    f = fetch_stock_fundamentals(resolve_yahoo_symbol(market, symbol))
    sharia_reference = get_sharia_reference_status(symbol) if market == "ihsg_syariah" else None
    if not f.get("available"):
        text = (
            f"FUNDAMENTAL DATA for {symbol}: UNAVAILABLE (Yahoo Finance returned no statements). "
            "Do not quote valuation multiples, ratios, or financial results from memory."
        )
        if market == "ihsg_syariah":
            text += (
                "\nSHARIA SCREEN: UNVERIFIED. No financial statements were retrieved, so debt/assets "
                "and non-halal income ratios cannot be computed. Do NOT state that the stock is "
                "certified Sharia-compliant."
            )
            text += "\n" + _format_sharia_reference_block(symbol, sharia_reference)
        return {"text": text, "available": False, "sharia": None, "sharia_reference": sharia_reference}

    sharia = evaluate_sharia_screen(f) if market == "ihsg_syariah" else None
    text = _format_stock_block(f, sharia)
    if sharia_reference:
        text += "\n" + _format_sharia_reference_block(symbol, sharia_reference)
    return {"text": text, "available": True, "sharia": sharia, "sharia_reference": sharia_reference}


def get_onchain_context(market: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Builds a real-data block for the on-chain analyst.

    Returns ``None`` for non-crypto markets. For crypto, returns
    ``{"text": str, "available": bool}`` with derivatives and DeFi TVL data
    already fetched by the backend (Binance Futures + DefiLlama).
    """
    if _normalize_market(market) != "crypto":
        return None
    f = fetch_crypto_fundamentals(symbol)
    return {
        "text": _format_onchain_block(symbol, f),
        "available": bool(f.get("available") or f.get("futures") or f.get("defillama")),
    }


def get_recommendation_fundamentals(market: str, symbols: List[str]) -> str:
    """Compact per-asset real fundamentals for the recommendation scan."""
    norm = _normalize_market(market)
    if not symbols:
        return ""

    if norm == "crypto":
        def one(sym: str) -> str:
            f = fetch_crypto_fundamentals(sym)
            if not f.get("available"):
                return f"- {sym}: fundamentals UNAVAILABLE"
            llama = f.get("defillama") or {}
            fut = f.get("futures") or {}
            return (
                f"- {sym}: mcap={_fmt_usd(f.get('market_cap'))}, FDV={_fmt_usd(f.get('fdv'))}, "
                f"circ/max={_fmt_pct((f['circulating_supply'] / f['max_supply']) if f.get('circulating_supply') and f.get('max_supply') else None)}, "
                f"7d={_fmt_num(f.get('change_7d'), 1, '%')}, 30d={_fmt_num(f.get('change_30d'), 1, '%')}, "
                f"TVL={_fmt_usd(llama.get('tvl'))}, "
                f"funding={_fmt_num(fut.get('funding_rate') and fut['funding_rate'] * 100, 4, '%')}"
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
                f"mcap={_fmt_big(f.get('market_cap'))}, P/E={_fmt_num(f.get('trailing_pe'))}, "
                f"P/B={_fmt_num(f.get('price_to_book'))}, ROE={_fmt_pct(f.get('roe'))}, "
                f"D/E={_fmt_num(f.get('debt_to_equity'))}, rev_growth={_fmt_pct(f.get('revenue_growth'))}"
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
        "REAL FUNDAMENTAL DATA (Yahoo Finance statements / CoinGecko / DefiLlama / Binance Futures). "
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
