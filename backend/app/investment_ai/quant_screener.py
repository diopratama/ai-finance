"""Quality, Value & Compounding Screener Module.

Ranks market candidates across IHSG, US Equities, US ETFs, and Tier-1 Crypto
with 65% weight on institutional fundamental quality & valuation and 35% weight
on healthy market-cycle accumulation timing (near SMA 50/200, avoiding FOMO tops).
"""

import json
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.investment_ai.cache_store import shared_cache_get, shared_cache_set
from app.investment_ai.fundamental_data import (
    fetch_crypto_fundamentals,
    fetch_etf_fundamentals,
    fetch_stock_fundamentals,
)
from app.investment_ai.market_data import (
    _fetch_binance_batch,
    _fetch_yahoo_batch,
    _get_binance_24h_tickers,
    _normalize_market,
    calculate_investment_zones,
    is_source_data_fresh,
    resolve_yahoo_symbol,
)
from app.investment_ai.sharia_reference import ShariaReferenceError, get_issi_universe, load_sharia_reference

logger = logging.getLogger(__name__)

_orig_fetch_binance_batch = _fetch_binance_batch
_orig_fetch_yahoo_batch = _fetch_yahoo_batch

# Conventional IDX screener focuses on profitable liquid bluechips & compounders.
IDX_CONVENTIONAL_UNIVERSE = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BDMN.JK", "ASII.JK",
    "TLKM.JK", "ADRO.JK", "ANTM.JK", "ICBP.JK", "INDF.JK", "MYOR.JK",
    "AMRT.JK", "KLBF.JK", "PTBA.JK", "PGAS.JK", "UNTR.JK", "ITMG.JK",
    "CPIN.JK", "JPFA.JK", "SMGR.JK", "INTP.JK", "ISAT.JK", "EXCL.JK",
    "AKRA.JK", "BRIS.JK", "MEDC.JK", "AMMN.JK", "INKP.JK", "TKIM.JK",
]

# Tier-1 Bluechip & Real-Utility Infrastructure Crypto Universe (no meme coins)
DEFAULT_CRYPTO_FALLBACK = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "LINK/USDT", "AAVE/USDT",
    "UNI/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT", "AVAX/USDT", "TON/USDT",
    "RENDER/USDT", "TAO/USDT", "INJ/USDT", "NEAR/USDT", "DOT/USDT", "ATOM/USDT",
    "POL/USDT", "APT/USDT",
]

TIER1_UTILITY_CRYPTO_ALLOWLIST = {
    "BTC", "ETH", "SOL", "BNB", "LINK", "AAVE", "UNI", "ARB", "OP", "SUI",
    "AVAX", "TON", "RENDER", "TAO", "INJ", "NEAR", "DOT", "ATOM", "POL",
    "APT", "ADA", "XRP", "LTC", "HBAR", "XLM", "ONDO", "MKR", "PENDLE",
    "LDO", "GRT", "FIL", "ICP", "TIA", "SEI", "STX", "FET", "TRX",
}

MEME_AND_SPECULATIVE_CRYPTO_BASES = {
    "PEPE", "DOGE", "SHIB", "BONK", "WIF", "FLOKI", "MEME", "BOME", "TRUMP",
    "MELANIA", "PNUT", "NEIRO", "TURBO", "BABYDOGE", "MOG", "POPCAT", "BRETT",
    "FARTCOIN", "1000PEPE", "1000SHIB", "1000BONK", "1000FLOKI", "1000SATS",
    "LUNC", "USTC", "PEPE2", "LADYS", "ELON",
}

DEFAULT_US_FALLBACK = [
    "MSFT", "AAPL", "GOOGL", "AMZN", "NVDA", "META", "BRK-B", "JPM",
    "V", "MA", "UNH", "JNJ", "PG", "HD", "AVGO", "COST",
]

# Curated liquid US ETF universe. Leveraged/inverse products are excluded by default.
US_ETF_UNIVERSE = [
    # Broad market
    "SPY", "VOO", "IVV", "QQQ", "DIA", "IWM", "VTI",
    # Dividend & Quality Core
    "SCHD", "VYM", "DGRO", "VIG", "QUAL",
    # Sectors
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH",
    # Fixed income
    "TLT", "IEF", "SHY", "BND", "HYG", "LQD", "AGG", "VCIT", "BSV",
    # Commodities / alternatives
    "GLD", "SLV", "IBIT", "GDX",
    # International
    "EFA", "EEM", "VWO",
]

TOKENIZED_EQUITY_CRYPTO_SYMBOLS = {"SKHYB", "MUB", "SNDKB"}
MIN_US_DOLLAR_VOLUME = 5_000_000.0

LEVERAGED_CRYPTO_PATTERNS = ["UPUSDT", "DOWNUSDT", "BEARUSDT", "BULLUSDT", "2LUSDT", "2SUSDT", "3LUSDT", "3SUSDT"]
EXCLUDED_US_ETFS = {"SOXL", "SOXS", "SQQQ", "TQQQ", "UVXY", "SPXU", "UPRO", "BOIL", "KOLD", "NUGT", "DUST", "YINN", "YANG"}


def fetch_live_crypto_universe(limit: int = 30) -> List[str]:
    """Fetches liquid Tier-1 / Bluechip & Infrastructure crypto pairs from Binance.

    Strictly excludes meme coins, stablecoins, and leveraged tokens.
    """
    ignored_stables = {
        "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "EURUSDT", "USDPUSDT", "AEURUSDT", "USD1USDT", "USDGUSDT",
        "USDEUSDT", "DAIUSDT", "USDSUSDT",
    }

    try:
        data = _get_binance_24h_tickers()

        usdt_pairs = []
        for d in data:
            if not isinstance(d, dict):
                continue
            sym = d.get("symbol", "")
            if not sym.endswith("USDT") or sym in ignored_stables:
                continue
            base = sym[:-4].upper()
            if base in TOKENIZED_EQUITY_CRYPTO_SYMBOLS or base in MEME_AND_SPECULATIVE_CRYPTO_BASES:
                continue
            # Restrict crypto screener strictly to Tier-1 / Bluechip & Infrastructure utility assets
            if base not in TIER1_UTILITY_CRYPTO_ALLOWLIST:
                continue
            if any(sym.endswith(pat) for pat in LEVERAGED_CRYPTO_PATTERNS):
                continue
            quote_vol = float(d.get("quoteVolume", 0) or 0)
            if quote_vol < 5_000_000:
                continue
            usdt_pairs.append(d)

        usdt_pairs.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        live_symbols = [d["symbol"][:-4] + "/USDT" for d in usdt_pairs[:limit]]

        if live_symbols:
            logger.info("Quality Screener: Discovered %d Tier-1/Bluechip cryptos from Binance", len(live_symbols))
            return live_symbols
    except Exception as e:
        logger.warning("Live crypto discovery via Binance failed: %s. Using curated Tier-1 fallback.", e)

    return DEFAULT_CRYPTO_FALLBACK[:limit]


def fetch_live_us_universe(limit: int = 30) -> List[str]:
    """Fetches fundamentally active & undervalued US stocks from Yahoo Finance screener.

    Intentionally excludes ``day_gainers`` to avoid chasing short-term speculative pumps.
    """
    screen_order = ["undervalued_large_caps", "undervalued_growth_stocks", "most_actives"]
    lists_by_screen: Dict[str, List[str]] = {s: [] for s in screen_order}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    for scr_id in screen_order:
        url = f"https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=false&scrIds={scr_id}&count=25"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
                quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
                for q in quotes:
                    sym = q.get("symbol")
                    if not sym or any(sym in values for values in lists_by_screen.values()) or sym in EXCLUDED_US_ETFS:
                        continue
                    if any(ch in sym for ch in ["^", "=", "+", ".", "/"]):
                        continue
                    if q.get("quoteType") != "EQUITY":
                        continue
                    price = q.get("regularMarketPrice") or q.get("price")
                    if price and price < 10.0:
                        continue
                    volume = q.get("regularMarketVolume")
                    if price is None or volume is None or float(price) * float(volume) < MIN_US_DOLLAR_VOLUME:
                        continue
                    lists_by_screen[scr_id].append(sym)
        except Exception as e:
            logger.warning("Live US value/active discovery (%s) failed: %s", scr_id, e)

    symbols: List[str] = []
    positions = {scr_id: 0 for scr_id in screen_order}
    while len(symbols) < limit:
        added = False
        for scr_id in screen_order:
            candidates = lists_by_screen[scr_id]
            index = positions[scr_id]
            if index < len(candidates):
                symbols.append(candidates[index])
                positions[scr_id] += 1
                added = True
                if len(symbols) >= limit:
                    break
        if not added:
            break

    if symbols:
        logger.info("Quality Screener: Fetched %d value/quality US stocks from Yahoo Screener", len(symbols))
        return symbols

    logger.warning("Yahoo US stock discovery returned no candidates; using static compounder watchlist")
    return DEFAULT_US_FALLBACK


def get_universe_for_market(market: str) -> List[str]:
    """Resolves a market universe oriented around quality & long-term investability."""
    market_lower = market.strip().lower()

    if "crypto" in market_lower:
        return fetch_live_crypto_universe(limit=30)

    if market_lower == "us_etf":
        return list(US_ETF_UNIVERSE)

    if market_lower == "us_stock":
        return fetch_live_us_universe(limit=30)

    if market_lower == "ihsg_syariah":
        try:
            return get_issi_universe()
        except ShariaReferenceError as e:
            logger.error("Unable to load supplied ISSI reference: %s", e)
            return []

    if "ihsg" in market_lower:
        return list(IDX_CONVENTIONAL_UNIVERSE)

    return list(DEFAULT_US_FALLBACK)


_orig_get_universe_for_market = get_universe_for_market


def _fetch_yahoo_batch_chunked(
    yahoo_symbols: List[str], *, chunk_size: int = 80, max_workers: int = 1
) -> Dict[str, Dict[str, Any]]:
    """Fetch a large ISSI list in bounded, serialized Yahoo batches to prevent IP rate-limiting."""
    chunks = [yahoo_symbols[i : i + chunk_size] for i in range(0, len(yahoo_symbols), chunk_size)]
    if not chunks:
        return {}
    results: Dict[str, Dict[str, Any]] = {}
    is_default_fetcher = _fetch_yahoo_batch is _orig_fetch_yahoo_batch
    for idx, chunk in enumerate(chunks):
        batch = (
            _fetch_yahoo_batch(chunk, cache_ttl=600.0)
            if is_default_fetcher
            else _fetch_yahoo_batch(chunk)
        )
        results.update(batch)
        if is_default_fetcher and idx + 1 < len(chunks):
            time.sleep(0.1)
    return results


def _score_price_cycle(
    price: float,
    indicators: Dict[str, Any],
) -> Tuple[Optional[float], List[str]]:
    """Evaluates Market Cycle & Healthy Accumulation Timing (0-35 points)."""
    sma20 = indicators.get("sma20")
    sma50 = indicators.get("sma50")
    sma200 = indicators.get("sma200")
    rsi = indicators.get("rsi")
    macd_trend = indicators.get("macd")
    macd_hist = indicators.get("macd_histogram")

    if sma20 is None or rsi is None:
        return None, ["Insufficient cycle history"]

    pts = 15.0
    notes: List[str] = []

    # Reward price near healthy accumulation zone (near SMA50 / SMA200), penalize FOMO peaks
    ref_sma = sma200 or sma50
    if ref_sma and ref_sma > 0:
        dist_pct = ((price - ref_sma) / ref_sma) * 100.0
        if -12.0 <= dist_pct <= 8.0:
            pts += 12.0
            notes.append(f"Zona Akumulasi Sehat ({dist_pct:+.1f}% vs SMA{'200' if sma200 else '50'})")
        elif 8.0 < dist_pct <= 20.0:
            pts += 6.0
            notes.append(f"Uptrend Konstruktif ({dist_pct:+.1f}% vs SMA)")
        elif dist_pct > 25.0:
            pts -= 8.0
            notes.append(f"Overextended ({dist_pct:+.1f}% di atas SMA; lebih bijak cicil DCA)")
        elif dist_pct < -20.0:
            pts += 8.0
            notes.append(f"Diskon Siklus Dalam ({dist_pct:+.1f}% di bawah SMA)")

    # RSI accumulation range (35-62 ideal, >72 overheated)
    if 35.0 <= rsi <= 60.0:
        pts += 6.0
        notes.append(f"RSI Siklus Sehat ({rsi})")
    elif rsi < 35.0:
        pts += 5.0
        notes.append(f"Area Value Oversold (RSI {rsi})")
    elif rsi > 72.0:
        pts -= 7.0
        notes.append(f"Waspada Pucuk Overbought (RSI {rsi})")

    if macd_trend == "bullish" or (macd_hist is not None and macd_hist > 0):
        pts += 2.0

    return round(max(0.0, min(35.0, pts)), 1), notes


def _score_fundamental_quality(
    fundamentals: Optional[Dict[str, Any]],
    market: str = "ihsg",
) -> Tuple[float, List[str]]:
    """Evaluates Fundamental Quality, Growth & Margin of Safety (0-65 points)."""
    if not fundamentals or fundamentals.get("available") is False:
        return 30.0, ["Fundamental dalam proses verifikasi (Skor baseline netral)"]

    norm = _normalize_market(market)
    pts = 15.0
    notes: List[str] = []

    if norm == "crypto":
        mcap_fdv = fundamentals.get("mcap_to_fdv_ratio")
        supply_pct = fundamentals.get("supply_issued_pct")
        llama = fundamentals.get("defillama") or {}
        commits = fundamentals.get("commits_4w") or 0

        if mcap_fdv is not None:
            if mcap_fdv >= 0.80:
                pts += 20.0
                notes.append(f"Risiko Dilusi Rendah (MCap/FDV {mcap_fdv*100:.0f}%)")
            elif mcap_fdv >= 0.50:
                pts += 12.0
                notes.append(f"MCap/FDV Moderat ({mcap_fdv*100:.0f}%)")
            else:
                pts += 3.0
                notes.append(f"Risiko Dilusi Token Tinggi (MCap/FDV {mcap_fdv*100:.0f}%)")
        if supply_pct is not None and supply_pct >= 0.75:
            pts += 8.0
        if llama.get("tvl"):
            pts += 12.0
            notes.append("Utilitas DeFi/TVL Terverifikasi")
        elif (fundamentals.get("market_cap") or 0) >= 10_000_000_000:
            pts += 14.0
            notes.append("Layer-1 / Bluechip Market Cap > $10B")
        if commits and commits >= 20:
            pts += 8.0
            notes.append(f"Aktivitas Dev Aktif ({commits} commits/4w)")
        return round(max(5.0, min(65.0, pts)), 1), notes

    if norm == "us_etf":
        exp = fundamentals.get("expense_ratio")
        three_y = fundamentals.get("three_year_return")
        five_y = fundamentals.get("five_year_return")
        aum = fundamentals.get("aum")
        dy = fundamentals.get("yield")
        if exp is not None:
            pts += 15.0 if exp <= 0.002 else (10.0 if exp <= 0.005 else 4.0)
            if exp <= 0.002:
                notes.append(f"Expense Ratio Sangat Efisien ({exp*100:.2f}%)")
        if (five_y is not None and five_y > 0.08) or (three_y is not None and three_y > 0.08):
            pts += 18.0
            notes.append("Compounding 3Y/5Y Kuat (>8%/thn)")
        if aum is not None and aum >= 1e9:
            pts += 10.0
        if dy is not None and dy >= 0.02:
            pts += 7.0
        return round(max(5.0, min(65.0, pts)), 1), notes

    # Equities (IHSG & US Stocks)
    roe = fundamentals.get("roe")
    roic = fundamentals.get("roic")
    f_score = fundamentals.get("piotroski_f_score")
    mos = fundamentals.get("margin_of_safety_pct")
    pe = fundamentals.get("trailing_pe")
    rev_cagr = fundamentals.get("revenue_cagr_3y") or fundamentals.get("revenue_growth")
    div_yield = fundamentals.get("dividend_yield")

    # 1. Capital efficiency (ROE / ROIC) -> max +16 pts
    eff = roic if roic is not None else roe
    if eff is not None:
        if eff >= 0.15:
            pts += 16.0
            notes.append(f"{'ROIC' if roic is not None else 'ROE'} Prima ({eff*100:.1f}%)")
        elif eff >= 0.10:
            pts += 10.0

    # 2. Financial Health (Piotroski F-Score) -> max +14 pts
    if f_score is not None:
        if f_score >= 7:
            pts += 14.0
            notes.append(f"Piotroski F-Score Kuat ({f_score}/9)")
        elif f_score >= 5:
            pts += 8.0
        elif f_score <= 3:
            pts -= 6.0

    # 3. Multi-Year Growth -> max +10 pts
    if rev_cagr is not None and rev_cagr > 0.05:
        pts += 10.0
        notes.append(f"Pertumbuhan Pendapatan Positif ({rev_cagr*100:.1f}%)")

    # 4. Valuation Discount & Dividend -> max +15 pts
    if mos is not None:
        if mos >= 15.0:
            pts += 12.0
            notes.append(f"Diskon Valuasi MoS +{mos:.1f}%")
        elif mos >= 0.0:
            pts += 6.0
    elif pe is not None and 0 < pe <= 18.0:
        pts += 8.0
        notes.append(f"Valuasi P/E Atraktif ({pe:.1f}x)")

    if div_yield is not None and div_yield >= 2.0:
        pts += 5.0
        notes.append(f"Dividen {div_yield:.1f}%")

    return round(max(5.0, min(65.0, pts)), 1), notes


def compute_screener_breakdown(
    price: float,
    change_pct: Optional[float],
    indicators: Dict[str, Any],
    fundamentals: Optional[Dict[str, Any]] = None,
    market: str = "ihsg",
) -> Dict[str, Any]:
    """Computes full Quality (65%) + Cycle (35%) scoring breakdown."""
    cycle_score, cycle_notes = _score_price_cycle(price, indicators)
    if cycle_score is None:
        return {"score": None, "cycle_score": None, "fundamental_score": None, "pattern": "Insufficient indicator history"}

    fund_score, fund_notes = _score_fundamental_quality(fundamentals, market=market)
    total_score = round(max(5.0, min(99.0, fund_score + cycle_score)), 1)
    all_notes = fund_notes + cycle_notes
    return {
        "score": total_score,
        "fundamental_score": fund_score,
        "cycle_score": cycle_score,
        "pattern": " | ".join(all_notes) if all_notes else "Quality Compounding Watchlist",
    }


def score_asset_opportunity(
    price: float,
    change_pct: Optional[float],
    indicators: Dict[str, Any],
    fundamentals: Optional[Dict[str, Any]] = None,
    market: str = "ihsg",
) -> Tuple[Optional[float], str]:
    """Calculates 65% Fundamental Quality + 35% Accumulation Cycle score."""
    bd = compute_screener_breakdown(price, change_pct, indicators, fundamentals=fundamentals, market=market)
    return bd["score"], bd["pattern"]


def _fetch_fundamentals_for_candidate(market: str, symbol: str) -> Dict[str, Any]:
    norm = _normalize_market(market)
    try:
        if norm == "crypto":
            return fetch_crypto_fundamentals(symbol)
        if norm == "us_etf":
            return fetch_etf_fundamentals(symbol)
        return fetch_stock_fundamentals(resolve_yahoo_symbol(market, symbol))
    except Exception as e:
        logger.debug("Screener fundamental enrich failed for %s: %s", symbol, e)
        return {"symbol": symbol, "available": False}


def screen_market_opportunities(
    market: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Quality, Value & Compounding Screener (65% Fundamental + 35% Cycle Accumulation)."""
    started_at = time.perf_counter()
    market_lower = market.strip().lower()
    use_screener_cache = (
        get_universe_for_market is _orig_get_universe_for_market
        and _fetch_binance_batch is _orig_fetch_binance_batch
        and _fetch_yahoo_batch is _orig_fetch_yahoo_batch
    )
    screener_cache_key = f"screener:v2:{market_lower}:{limit}"
    if use_screener_cache:
        hit, cached_top = shared_cache_get(screener_cache_key)
        if hit and isinstance(cached_top, list) and cached_top:
            logger.info(
                "Quality Screener: Returning %d cached candidates for '%s' (duration_ms=%.1f)",
                len(cached_top),
                market,
                (time.perf_counter() - started_at) * 1000,
            )
            return cached_top

    universe = get_universe_for_market(market)
    if "crypto" in market_lower:
        universe_source = "tier1_utility_fallback" if universe == DEFAULT_CRYPTO_FALLBACK[:len(universe)] else "binance_tier1_utility_discovery"
    elif market_lower == "us_etf":
        universe_source = "us_etf_curated"
    elif market_lower == "us_stock":
        universe_source = "static_compounder_fallback" if universe == DEFAULT_US_FALLBACK else "yahoo_undervalued_screener"
    elif market_lower == "ihsg_syariah":
        universe_source = "issi_reference_csv"
    elif "ihsg" in market_lower:
        universe_source = "static_idx_quality_list"
    else:
        universe_source = "static_fallback"

    if not universe:
        logger.warning("Quality screener has no candidate universe")
        return []

    is_crypto = "crypto" in market_lower
    sharia_reference = None
    sharia_by_ticker: Dict[str, Dict[str, Any]] = {}
    if market_lower == "ihsg_syariah":
        try:
            sharia_reference = load_sharia_reference()
            sharia_by_ticker = {row["ticker"]: row for row in sharia_reference["issuers"]}
        except ShariaReferenceError as e:
            logger.error("ISSI reference unavailable during screening: %s", e)
            return []

    yahoo_symbols = [resolve_yahoo_symbol(market, s) for s in universe]
    symbol_map = {ys: s for s, ys in zip(universe, yahoo_symbols)}
    if is_crypto:
        try:
            batch_data = _fetch_binance_batch(universe)
        except Exception as e:
            logger.warning("Binance crypto batch failed; trying Yahoo Tier-1 fallback: %s", e)
            batch_data = {}
        if not batch_data:
            universe = list(DEFAULT_CRYPTO_FALLBACK)
            yahoo_symbols = [resolve_yahoo_symbol("crypto", s) for s in universe]
            symbol_map = {ys: s for s, ys in zip(universe, yahoo_symbols)}
            yahoo_batch = _fetch_yahoo_batch(yahoo_symbols)
            batch_data = {}
            for yahoo_symbol, data in yahoo_batch.items():
                display_symbol = symbol_map.get(yahoo_symbol)
                if not display_symbol:
                    continue
                data["provider"] = "yahoo"
                data["change_period"] = "daily_close_to_close"
                batch_data[display_symbol] = data
            universe_source = "tier1_crypto_yahoo_fallback"
    else:
        batch_data = (
            _fetch_yahoo_batch_chunked(yahoo_symbols)
            if market_lower == "ihsg_syariah"
            else _fetch_yahoo_batch(yahoo_symbols)
        )

    if not batch_data:
        logger.warning("Quality Screener: No market data returned")
        return []

    # Stage 1: Filter fresh quotes and compute Market Cycle pre-score (0-35)
    stage1_candidates: List[Tuple[float, str, Dict[str, Any]]] = []
    for data_key, data in batch_data.items():
        original_symbol = data_key if is_crypto else symbol_map.get(data_key)
        if not original_symbol:
            continue
        if not is_source_data_fresh(data.get("source_as_of"), market):
            continue
        price = data.get("price")
        if price is None:
            continue
        cycle_pts, _ = _score_price_cycle(price, data)
        if cycle_pts is None:
            continue
        stage1_candidates.append((cycle_pts, original_symbol, data))

    if not stage1_candidates:
        return []

    # Keep bounded pool for fast parallel fundamental enrichment
    stage1_candidates.sort(key=lambda item: item[0], reverse=True)
    enrich_pool = stage1_candidates[: min(max(limit + 8, 16), len(stage1_candidates))]
    enrich_symbols = [sym for _, sym, _ in enrich_pool]

    fundamentals_by_sym: Dict[str, Dict[str, Any]] = {}
    try:
        with ThreadPoolExecutor(max_workers=min(6, len(enrich_symbols))) as pool:
            f_results = list(pool.map(lambda s: _fetch_fundamentals_for_candidate(market, s), enrich_symbols))
        for sym, f_res in zip(enrich_symbols, f_results):
            fundamentals_by_sym[sym] = f_res
    except Exception as e:
        logger.warning("Parallel fundamental enrichment failed: %s", e)

    scored_candidates: List[Dict[str, Any]] = []
    for _, original_symbol, data in enrich_pool:
        price = data["price"]
        change_pct = data.get("change_pct")
        fund_data = fundamentals_by_sym.get(original_symbol) or {}
        bd = compute_screener_breakdown(price, change_pct, data, fundamentals=fund_data, market=market)
        if bd["score"] is None:
            continue

        zones = calculate_investment_zones(
            price=price,
            stats=data,
            long_term_metrics=None,
            fundamental_data=fund_data,
            market=market,
        )
        acc_z = zones.get("accumulation_zone") or {}
        fv_t = zones.get("fair_value_target") or {}
        inv_t = zones.get("thesis_invalidation") or {}

        candidate: Dict[str, Any] = {
            "symbol": original_symbol,
            "score": bd["score"],
            "fundamental_score": bd["fundamental_score"],
            "cycle_score": bd["cycle_score"],
            "score_type": "quality_value_compounding_rank",
            "universe_source": universe_source,
            "pattern": bd["pattern"],
            "price": price,
            "change_pct": change_pct,
            "change_period": data.get("change_period", "daily_close_to_close"),
            "provider": data.get("provider", "yahoo"),
            "source_as_of": data.get("source_as_of"),
            "captured_at": data.get("captured_at"),
            "volume": data.get("volume"),
            "rsi": data.get("rsi"),
            "sma20": data.get("sma20"),
            "sma50": data.get("sma50"),
            "sma200": data.get("sma200"),
            "macd": data.get("macd"),
            "macd_line": data.get("macd_line"),
            "macd_signal": data.get("macd_signal"),
            "macd_histogram": data.get("macd_histogram"),
            "support": data.get("support"),
            "resistance": data.get("resistance"),
            # Investment-oriented fundamental & zone fields
            "piotroski_f_score": fund_data.get("piotroski_f_score"),
            "altman_z_score": fund_data.get("altman_z_score"),
            "fair_value_estimate": fv_t.get("fair_value"),
            "margin_of_safety_pct": fv_t.get("margin_of_safety_pct"),
            "valuation_status": fv_t.get("valuation_status"),
            "roic_pct": round(fund_data["roic"] * 100.0, 2) if fund_data.get("roic") is not None else None,
            "roe_pct": round(fund_data["roe"] * 100.0, 2) if fund_data.get("roe") is not None else None,
            "dividend_yield_pct": round(fund_data["dividend_yield"], 2) if fund_data.get("dividend_yield") is not None else None,
            "revenue_cagr_3y_pct": round(fund_data["revenue_cagr_3y"] * 100.0, 2) if fund_data.get("revenue_cagr_3y") is not None else None,
            "mcap_to_fdv_pct": round(fund_data["mcap_to_fdv_ratio"] * 100.0, 1) if fund_data.get("mcap_to_fdv_ratio") is not None else None,
            "accumulation_zone": acc_z,
            "fair_value_target": fv_t,
            "thesis_invalidation": inv_t,
            "investment_zones": zones,
            "issi_status": sharia_by_ticker.get(original_symbol, {}).get("issi_status") if sharia_reference else None,
            "sharia_reference_source_as_of": sharia_reference.get("source_as_of") if sharia_reference else None,
            "sharia_reference_valid_until": sharia_reference.get("valid_until") if sharia_reference else None,
            "sharia_reference_listed": bool(
                sharia_by_ticker.get(original_symbol, {}).get("issi_status") == "Ya"
            ) if sharia_reference else False,
        }

        if market_lower == "us_etf":
            candidate["etf_category"] = fund_data.get("category") or "Uncategorized"
            candidate["aum"] = fund_data.get("aum")
            candidate["expense_ratio"] = fund_data.get("expense_ratio")
            candidate["ytd_return"] = fund_data.get("ytd_return")
            candidate["three_year_return"] = fund_data.get("three_year_return")
            candidate["five_year_return"] = fund_data.get("five_year_return")

        scored_candidates.append(candidate)

    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    top_opportunities = scored_candidates[:limit]

    if use_screener_cache and top_opportunities:
        screener_ttl = 300.0 if market_lower == "ihsg_syariah" else 180.0
        shared_cache_set(screener_cache_key, top_opportunities, screener_ttl)

    logger.info(
        "Quality Screener: universe_source=%s candidates=%d enriched=%d selected=%d duration_ms=%.0f",
        universe_source,
        len(universe),
        len(enrich_pool),
        len(top_opportunities),
        (time.perf_counter() - started_at) * 1000,
    )
    return top_opportunities
