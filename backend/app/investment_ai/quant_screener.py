"""Quantitative Screener Module.

Ranks market candidates across crypto, IHSG, and US equities from external market data.
The resulting heuristic score is a ranking aid, not an estimated probability.
"""

import json
import logging
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from app.investment_ai.cache_store import shared_cache_get, shared_cache_set
from app.investment_ai.fundamental_data import fetch_etf_fundamentals
from app.investment_ai.market_data import (
    _fetch_binance_batch,
    _fetch_yahoo_batch,
    _get_binance_24h_tickers,
    calculate_atr_levels,
    is_source_data_fresh,
    resolve_yahoo_symbol,
)
from app.investment_ai.sharia_reference import ShariaReferenceError, get_issi_universe, load_sharia_reference

logger = logging.getLogger(__name__)

_orig_fetch_binance_batch = _fetch_binance_batch
_orig_fetch_yahoo_batch = _fetch_yahoo_batch

# Conventional IDX screener remains a limited static candidate pool.
IDX_CONVENTIONAL_UNIVERSE = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BBTN.JK", "BDMN.JK", "ASII.JK",
    "TLKM.JK", "ADRO.JK", "ANTM.JK", "ICBP.JK", "GOTO.JK", "AMMN.JK", "BREN.JK",
    "BRIS.JK", "MDKA.JK", "UNVR.JK", "INDF.JK", "PTBA.JK", "CPIN.JK", "KLBF.JK",
    "MEDC.JK", "PGAS.JK", "INCO.JK", "TPIA.JK", "BRPT.JK", "ISAT.JK", "EXCL.JK",
    "AKRA.JK", "SMGR.JK", "INTP.JK", "MYOR.JK", "AMRT.JK", "ERAA.JK", "INKP.JK",
    "TKIM.JK", "BUMI.JK", "DOID.JK", "MBMA.JK", "NCKL.JK", "HRUM.JK", "ARTO.JK",
]

DEFAULT_CRYPTO_FALLBACK = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
    "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "SUI/USDT", "NEAR/USDT", "PEPE/USDT",
]

DEFAULT_US_FALLBACK = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "AVGO", "NFLX", "PLTR", "ARM", "SMCI", "COIN", "JPM", "V",
]

# Curated liquid US ETF universe. Leveraged/inverse products are excluded by default.
US_ETF_UNIVERSE = [
    # Broad market
    "SPY", "VOO", "IVV", "QQQ", "DIA", "IWM", "VTI",
    # Sectors
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH",
    # Fixed income
    "TLT", "IEF", "SHY", "BND", "HYG", "LQD", "AGG", "VCIT", "BSV",
    # Commodities / alternatives
    "GLD", "SLV", "USO", "IBIT", "GDX", "GDXJ",
    # International
    "EFA", "EEM", "VWO", "FXI",
    # Thematic / factor
    "ARKK", "ICLN", "LIT", "XBI", "BOTZ", "VYM", "SCHD", "DGRO",
]

TOKENIZED_EQUITY_CRYPTO_SYMBOLS = {"SKHYB", "MUB", "SNDKB"}
MIN_US_DOLLAR_VOLUME = 5_000_000.0
MIN_US_ETF_DOLLAR_VOLUME = 50_000_000.0

LEVERAGED_CRYPTO_PATTERNS = ["UPUSDT", "DOWNUSDT", "BEARUSDT", "BULLUSDT", "2LUSDT", "2SUSDT", "3LUSDT", "3SUSDT"]
EXCLUDED_US_ETFS = {"SOXL", "SOXS", "SQQQ", "TQQQ", "UVXY", "SPXU", "UPRO", "BOIL", "KOLD", "NUGT", "DUST", "YINN", "YANG"}


def fetch_live_crypto_universe(limit: int = 30) -> List[str]:
    """Fetches real-time highest volume and active crypto pairs from Binance.

    Dynamically discovers liquid active coins while filtering out leveraged tokens and stablecoins.
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
            if sym[:-4] in TOKENIZED_EQUITY_CRYPTO_SYMBOLS:
                continue
            if any(sym.endswith(pat) for pat in LEVERAGED_CRYPTO_PATTERNS):
                continue
            # Filter minimum daily quote volume: at least 1M USDT for liquidity
            quote_vol = float(d.get("quoteVolume", 0) or 0)
            if quote_vol < 1_000_000:
                continue
            usdt_pairs.append(d)

        # Sort by 24h quote volume descending
        usdt_pairs.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
        live_symbols = [d["symbol"][:-4] + "/USDT" for d in usdt_pairs[:limit]]

        if live_symbols:
            logger.info("Quant Screener: Fetched %d real-time live cryptos from Binance (vol > $1M)", len(live_symbols))
            return live_symbols
    except Exception as e:
        logger.warning("Live crypto discovery via Binance failed: %s (geo-restricted or offline). Using vetted liquid fallback.", e)

    logger.warning("Using static crypto fallback universe; dynamic Binance discovery was unavailable")
    return DEFAULT_CRYPTO_FALLBACK


def fetch_live_us_universe(limit: int = 30) -> List[str]:
    """Fetches real-time most active and day gainer US stocks from Yahoo Finance screener.

    Filters for equities with at least $5M recent dollar volume, excludes ETFs/warrants,
    and alternates discovery categories to avoid over-weighting one Yahoo list.
    """
    lists_by_screen: Dict[str, List[str]] = {"most_actives": [], "day_gainers": []}
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

    # Fetch both most actives and day gainers
    for scr_id in ["most_actives", "day_gainers"]:
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
                    quote_type = q.get("quoteType")
                    if quote_type != "EQUITY":
                        continue
                    # Skip penny stocks under $5 to avoid low-liquidity microcaps
                    price = q.get("regularMarketPrice") or q.get("price")
                    if price and price < 5.0:
                        continue
                    volume = q.get("regularMarketVolume")
                    if price is None or volume is None or float(price) * float(volume) < MIN_US_DOLLAR_VOLUME:
                        continue
                    lists_by_screen[scr_id].append(sym)
        except Exception as e:
            logger.warning("Live US stock discovery (%s) failed: %s", scr_id, e)

    symbols: List[str] = []
    positions = {scr_id: 0 for scr_id in lists_by_screen}
    screen_order = ["most_actives", "day_gainers"]
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
        logger.info("Quant Screener: Fetched %d real-time active US stocks from Yahoo Screener", len(symbols))
        return symbols

    logger.warning("Yahoo US stock discovery returned no liquid candidates; using static watchlist")
    return DEFAULT_US_FALLBACK


def get_universe_for_market(market: str) -> List[str]:
    """Resolves a market universe; IDX universes are maintained static lists."""
    market_lower = market.strip().lower()

    if "crypto" in market_lower:
        return fetch_live_crypto_universe(limit=30)

    if market_lower == "us_etf":
        logger.info("US ETF universe is a curated static list")
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
        logger.info("IHSG conventional universe is a static candidate list")
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


def score_asset_opportunity(
    price: float,
    change_pct: Optional[float],
    indicators: Dict[str, Any],
) -> Tuple[Optional[float], str]:
    """Calculates a heuristic ranking score; this is not a probability estimate."""
    score = 40.0  # Base score
    patterns: List[str] = []

    sma20 = indicators.get("sma20")
    sma50 = indicators.get("sma50")
    rsi = indicators.get("rsi")
    macd_trend = indicators.get("macd")
    macd_hist = indicators.get("macd_histogram")

    if sma20 is None or rsi is None or macd_hist is None:
        return None, "Insufficient indicator history"

    # 1. Trend Quality
    if sma20 is not None:
        if price > sma20:
            score += 15.0
            if sma50 is not None and sma20 > sma50:
                score += 15.0
                patterns.append("Golden Trend (Price > SMA20 > SMA50)")
        else:
            score -= 10.0

    # 2. RSI Assessment
    if rsi is not None:
        if 48.0 <= rsi <= 68.0:
            score += 20.0
            patterns.append(f"Bullish Momentum (RSI {rsi})")
        elif rsi < 32.0:
            score += 18.0
            patterns.append(f"Oversold Dip (RSI {rsi})")
        elif rsi > 75.0:
            score -= 15.0
            patterns.append(f"Caution: Overbought (RSI {rsi})")
        elif 32.0 <= rsi < 48.0:
            score += 5.0

    # 3. MACD Assessment
    if macd_trend == "bullish" or (macd_hist is not None and macd_hist > 0):
        score += 12.0
        patterns.append("MACD Bullish")
    else:
        score -= 5.0

    # 4. Price Velocity / Change Assessment
    if change_pct is not None and 1.0 <= change_pct <= 7.0:
        score += 10.0
        patterns.append(f"Active Momentum (+{change_pct}%)")
    elif change_pct is not None and change_pct > 7.0:
        score += 5.0
    elif (
        change_pct is not None
        and -5.0 <= change_pct <= -1.0
        and rsi is not None
        and rsi < 38.0
    ):
        score += 8.0
        patterns.append(f"Dip Buy Pullback ({change_pct}%)")

    final_score = max(5.0, min(99.0, score))
    pattern_label = " | ".join(patterns) if patterns else "Neutral Range"

    return round(final_score, 1), pattern_label


def screen_market_opportunities(
    market: str,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Ranks market candidates using fresh daily indicators; scores are heuristic points."""
    started_at = time.perf_counter()
    market_lower = market.strip().lower()
    use_screener_cache = (
        get_universe_for_market is _orig_get_universe_for_market
        and _fetch_binance_batch is _orig_fetch_binance_batch
        and _fetch_yahoo_batch is _orig_fetch_yahoo_batch
    )
    screener_cache_key = f"screener:v1:{market_lower}:{limit}"
    if use_screener_cache:
        hit, cached_top = shared_cache_get(screener_cache_key)
        if hit and isinstance(cached_top, list) and cached_top:
            logger.info(
                "Quant Screener: Returning %d cached candidates for '%s' (duration_ms=%.1f)",
                len(cached_top),
                market,
                (time.perf_counter() - started_at) * 1000,
            )
            return cached_top

    universe = get_universe_for_market(market)
    if "crypto" in market_lower:
        universe_source = "static_fallback" if universe == DEFAULT_CRYPTO_FALLBACK else "binance_24h_discovery"
    elif market_lower == "us_etf":
        universe_source = "us_etf_curated"
    elif market_lower == "us_stock":
        universe_source = "static_fallback" if universe == DEFAULT_US_FALLBACK else "yahoo_screener"
    elif market_lower == "ihsg_syariah":
        universe_source = "issi_reference_csv"
    elif "ihsg" in market_lower:
        universe_source = "static_idx_list"
    else:
        universe_source = "static_fallback"
    if not universe:
        logger.warning("Quant screener has no candidate universe; refusing to use unscored symbols")
        return []

    logger.info("Quant Screener: Scanning %d market candidates for '%s'...", len(universe), market)

    is_crypto = "crypto" in market.strip().lower()
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
            logger.warning("Binance crypto candle batch failed; will try Yahoo majors fallback: %s", e)
            batch_data = {}
        if not batch_data:
            # Only use a fixed major-coin list for the Yahoo fallback. Mapping arbitrary
            # Binance tickers to BASE-USD could silently resolve to a different asset.
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
            universe_source = "static_major_crypto_yahoo_fallback"
            if batch_data:
                logger.warning(
                    "Crypto screener is using Yahoo fallback for %d static major pairs because Binance candle data was unavailable",
                    len(batch_data),
                )
            else:
                logger.error("Binance and Yahoo returned no crypto candle data for the fallback universe")
    else:
        batch_data = (
            _fetch_yahoo_batch_chunked(yahoo_symbols)
            if market_lower == "ihsg_syariah"
            else _fetch_yahoo_batch(yahoo_symbols)
        )
    if not batch_data:
        logger.warning("Quant Screener: No candidate market data returned; refusing unscored fallback")
        return []

    scored_candidates: List[Dict[str, Any]] = []

    for data_key, data in batch_data.items():
        original_symbol = data_key if is_crypto else symbol_map.get(data_key)
        if not original_symbol:
            continue

        if not is_source_data_fresh(data.get("source_as_of"), market):
            logger.warning(
                "Quant Screener: Excluding stale or undated %s market data from %s",
                original_symbol,
                data.get("provider", "unknown provider"),
            )
            continue

        price = data.get("price")
        change_pct = data.get("change_pct")
        if price is None:
            continue

        score, pattern = score_asset_opportunity(price, change_pct, data)
        if score is None:
            logger.warning("Quant Screener: Excluding %s due to insufficient indicators", original_symbol)
            continue

        scored_candidates.append(
            {
                "symbol": original_symbol,
                "score": score,
                "score_type": "heuristic_rank_points",
                "universe_source": universe_source,
                "pattern": pattern,
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
                "macd": data.get("macd"),
                "macd_line": data.get("macd_line"),
                "macd_signal": data.get("macd_signal"),
                "macd_histogram": data.get("macd_histogram"),
                "atr14": data.get("atr14"),
                "support": data.get("support"),
                "resistance": data.get("resistance"),
                "suggested_levels": calculate_atr_levels(price, data["atr14"])
                if data.get("atr14") is not None
                else None,
                "issi_status": sharia_by_ticker.get(original_symbol, {}).get("issi_status")
                if sharia_reference
                else None,
                "sharia_reference_source_as_of": sharia_reference.get("source_as_of")
                if sharia_reference
                else None,
                "sharia_reference_valid_until": sharia_reference.get("valid_until")
                if sharia_reference
                else None,
                "sharia_reference_listed": bool(
                    sharia_by_ticker.get(original_symbol, {}).get("issi_status") == "Ya"
                ) if sharia_reference else False,
            }
        )

    # Sort descending by quantitative opportunity score
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)

    top_opportunities = scored_candidates[:limit]

    # Enrich US ETF candidates with ETF-specific fundamentals for multi-horizon watchlists.
    if market_lower == "us_etf" and scored_candidates:
        etf_enrich_limit = min(max(limit, 15), len(scored_candidates))
        etf_symbols = [c["symbol"] for c in scored_candidates[:etf_enrich_limit]]
        try:
            with ThreadPoolExecutor(max_workers=min(4, len(etf_symbols))) as pool:
                etf_fundamentals = list(pool.map(fetch_etf_fundamentals, etf_symbols))
            for candidate, etf_fund in zip(scored_candidates[:etf_enrich_limit], etf_fundamentals):
                candidate["etf_category"] = etf_fund.get("category") or "Uncategorized"
                candidate["aum"] = etf_fund.get("aum")
                candidate["expense_ratio"] = etf_fund.get("expense_ratio")
                candidate["ytd_return"] = etf_fund.get("ytd_return")
                candidate["three_year_return"] = etf_fund.get("three_year_return")
                candidate["five_year_return"] = etf_fund.get("five_year_return")
        except Exception as e:
            logger.warning("Failed to enrich US ETF candidates with fundamentals: %s", e)

    if use_screener_cache and top_opportunities:
        screener_ttl = 300.0 if market_lower == "ihsg_syariah" else 120.0
        shared_cache_set(screener_cache_key, top_opportunities, screener_ttl)

    logger.info(
        "Quant Screener: universe_source=%s candidates=%d scored=%d selected=%d duration_ms=%.0f selected_symbols=%s",
        universe_source,
        len(universe),
        len(scored_candidates),
        len(top_opportunities),
        (time.perf_counter() - started_at) * 1000,
        [c["symbol"] for c in top_opportunities],
    )

    return top_opportunities
