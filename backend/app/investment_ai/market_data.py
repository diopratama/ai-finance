"""Real-time market data fetchers.

Yahoo Finance (via the ``yfinance`` library) is the primary source — it handles
the cookie/crumb handshake that Yahoo now requires and is far more reliable than
hitting the chart API directly. CoinGecko is used as a fallback for crypto only.
"""
import csv
import io
import json
import logging
import math
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import yfinance as yf

from app.config import settings
from app.investment_ai.cache_store import redis_get_json, redis_set_json, shared_cache_get, shared_cache_set

logger = logging.getLogger(__name__)

# Isolate yfinance SQLite timezone cache per worker process to avoid [Errno 17] races,
# and serialize yf.download calls so global yfinance.shared._DFS is never mutated concurrently.
_yfinance_lock = threading.Lock()
try:
    if hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(os.path.join(tempfile.gettempdir(), f"py-yfinance-{os.getpid()}"))
except Exception as _tz_err:
    logger.debug("Could not set custom yfinance tz cache location: %s", _tz_err)

# Timeframe -> (yfinance interval, yfinance period, optional resample rule).
# Long-term wealth compounding focuses on Daily (1D), Weekly (1W), and Monthly (1M) cycles.
TIMEFRAME_CONFIG = {
    "1D": {"interval": "1d", "period": "1y", "resample": None},
    "1W": {"interval": "1wk", "period": "5y", "resample": None},
    "1M": {"interval": "1mo", "period": "10y", "resample": None},
}

# CoinGecko fallback: timeframe -> days of history.
COINGECKO_DAYS = {
    "1D": 90,
    "1W": 365,
    "1M": 365,
}

MAX_CANDLES = 260

# Primary-source retry settings for get_market_quote.
PRIMARY_RETRIES = 2
PRIMARY_RETRY_BASE_DELAY = 0.6

# Symbol -> CoinGecko ID for common crypto assets.
COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
    "SUI": "sui",
    "NEAR": "near",
    "APT": "aptos",
    "BONK": "bonk",
    "WIF": "dogwifcoin",
    "FLOKI": "floki",
    "RENDER": "render-token",
    "FET": "fetch-ai",
    "TAO": "bittensor",
    "INJ": "injective-protocol",
    "SEI": "sei-network",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "TRX": "tron",
    "ARB": "arbitrum",
    "OP": "optimism",
    "TON": "the-open-network",
    "AAVE": "aave",
    "PENDLE": "pendle",
    "ENA": "ethena",
    "JUP": "jupiter-exchange-solana",
    "ONDO": "ondo-finance",
    "TIA": "celestia",
    "ORDI": "ordi",
    "XLM": "stellar",
    "HBAR": "hedera-hashgraph",
    "ALGO": "algorand",
    "FIL": "filecoin",
    "ICP": "internet-computer",
    "ETC": "ethereum-classic",
    "BCH": "bitcoin-cash",
    "LDO": "lido-dao",
    "GRT": "the-graph",
    "IMX": "immutable-x",
    "STX": "blockstack",
    "USDT": "tether",
    "USDC": "usd-coin",
}


class MarketDataError(Exception):
    """Raised when market data cannot be fetched from any provider."""


def _normalize_market(market: str) -> str:
    if "ihsg" in market:
        return "ihsg"
    if "crypto" in market:
        return "crypto"
    return market


def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to float, returning None for NaN or unparseable values."""
    try:
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _round_significant(value: float, digits: int = 8) -> float:
    """Round display/storage values without zeroing small-priced tokens such as PEPE."""
    if value == 0 or not math.isfinite(value):
        return value
    decimals = digits - 1 - math.floor(math.log10(abs(value)))
    return round(value, decimals)


def _sma(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _ema_series(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    k = 2 / (period + 1)
    ema = [values[0]]
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, Any]]:
    if len(closes) < slow + signal:
        return None
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema_series(macd_line, signal)
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    return {
        "macd": _round_significant(macd_val),
        "signal": _round_significant(signal_val),
        "histogram": _round_significant(macd_val - signal_val),
        "trend": "bullish" if macd_val > signal_val else "bearish",
    }


def compute_atr(candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
    """Computes Average True Range (ATR) across candle series."""
    if not candles or len(candles) < period + 1:
        return None
    tr_list: List[float] = []
    for i in range(1, len(candles)):
        h = _safe_float(candles[i].get("high"))
        l = _safe_float(candles[i].get("low"))
        prev_c = _safe_float(candles[i - 1].get("close"))
        if h is None or l is None or prev_c is None:
            continue
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
    if len(tr_list) < period:
        return None
    sample = tr_list[-period:]
    return _round_significant(sum(sample) / len(sample))


def calibrate_confidence(
    price: Optional[float],
    indicators: Dict[str, Any],
    stance: str,
    change_pct: Optional[float] = None,
) -> Optional[float]:
    """Deterministic 0..1 heuristic confidence derived from supplied indicators.

    Replaces an LLM self-assessed confidence with a reproducible, source-grounded
    number. It is a heuristic score, NOT a calibrated win probability.
    """
    if stance not in {"BUY", "SELL"}:
        return None

    sma20 = indicators.get("sma20")
    sma50 = indicators.get("sma50")
    rsi = indicators.get("rsi")
    macd = indicators.get("macd")
    macd_hist = indicators.get("macd_histogram")

    if sma20 is None or rsi is None:
        return None

    score = 0.5

    if stance == "BUY":
        if price is not None and price > sma20:
            score += 0.10
        elif price is not None:
            score -= 0.10
        if sma50 is not None:
            score += 0.10 if sma20 > sma50 else -0.10
        if 48.0 <= rsi <= 68.0:
            score += 0.12
        elif 32.0 <= rsi < 48.0:
            score += 0.04
        elif rsi < 32.0:
            score += 0.06
        elif rsi > 75.0:
            score -= 0.12
        if macd == "bullish" or (macd_hist is not None and macd_hist > 0):
            score += 0.10
        elif macd == "bearish":
            score -= 0.08
        if change_pct is not None and 1.0 <= change_pct <= 7.0:
            score += 0.06
        elif change_pct is not None and -5.0 <= change_pct <= -1.0 and rsi < 38.0:
            score += 0.04
    else:  # SELL / exit-reduce
        if price is not None and price < sma20:
            score += 0.10
        elif price is not None:
            score -= 0.10
        if sma50 is not None:
            score += 0.10 if sma20 < sma50 else -0.10
        if rsi > 70.0:
            score += 0.12
        elif 68.0 <= rsi <= 75.0:
            score += 0.06
        elif rsi < 40.0:
            score += 0.04
        if macd == "bearish" or (macd_hist is not None and macd_hist < 0):
            score += 0.10
        elif macd == "bullish":
            score -= 0.08

    return round(max(0.05, min(0.95, score)), 2)


def compute_support_resistance(
    candles: List[Dict[str, Any]], lookback: int = 20
) -> Tuple[Optional[float], Optional[float]]:
    """Calculates recent swing support (lowest low) and resistance (highest high)."""
    if not candles or len(candles) < lookback:
        return None, None
    recent = candles[-lookback:]
    lows = [_safe_float(c.get("low")) for c in recent if _safe_float(c.get("low")) is not None]
    highs = [_safe_float(c.get("high")) for c in recent if _safe_float(c.get("high")) is not None]
    support = min(lows) if lows else None
    resistance = max(highs) if highs else None
    return (
        _round_significant(support) if support is not None else None,
        _round_significant(resistance) if resistance is not None else None,
    )


def calculate_investment_zones(
    price: float,
    stats: Dict[str, Any],
    long_term_metrics: Optional[Dict[str, Any]] = None,
    fundamental_data: Optional[Dict[str, Any]] = None,
    market: str = "ihsg",
) -> Dict[str, Any]:
    """Computes the 3 long-term Investment Price Zones (replacing ATR SL & R-multiples):

    1. accumulation_zone: Buy-on-Dip / DCA Ideal zone near major support & SMA 50/200.
    2. fair_value_target: 1-3Y Fundamental Fair Value (DCF/Graham) & Margin of Safety.
    3. thesis_invalidation: Fundamental structural invalidation triggers (not daily volatility).
    """
    if not math.isfinite(price) or price <= 0:
        return {}

    lt = long_term_metrics or {}
    fund = fundamental_data or {}
    norm = _normalize_market(market)
    is_syariah = "syariah" in (market or "").lower()

    # 1. Zona Akumulasi / DCA Ideal (Buy on Dip Zone)
    anchors = [
        _safe_float(stats.get("support")),
        _safe_float(lt.get("sma200_day")) or _safe_float(stats.get("sma200")),
        _safe_float(lt.get("sma50_day")) or _safe_float(stats.get("sma50")),
        _safe_float(lt.get("sma200_week")),
    ]
    valid_anchors = sorted(a for a in anchors if a is not None and 0.4 * price <= a <= 1.05 * price)
    if len(valid_anchors) >= 2:
        ideal_low = _round_significant(min(valid_anchors[0], price * 0.94))
        ideal_high = _round_significant(min(valid_anchors[-1], price * 1.02))
    elif len(valid_anchors) == 1:
        anchor = valid_anchors[0]
        ideal_low = _round_significant(anchor * 0.96)
        ideal_high = _round_significant(min(max(anchor * 1.02, anchor), price * 1.02))
    else:
        ideal_low = _round_significant(price * 0.88)
        ideal_high = _round_significant(price * 0.96)

    if ideal_low > ideal_high:
        ideal_low, ideal_high = ideal_high, ideal_low

    cycle_pos = lt.get("cycle_position") or "NEUTRAL_CONSOLIDATION"
    rsi_val = _safe_float(stats.get("rsi"))
    if price <= ideal_high * 1.01 and (rsi_val is None or rsi_val <= 65):
        dca_guidance = (
            "Harga berada di Zona Akumulasi Ideal / Buy on Dip; sesuai untuk akumulasi bertahap (DCA) "
            "atau entry terukur."
        )
        dca_status = "IN_ACCUMULATION_ZONE"
    elif cycle_pos == "OVEREXTENDED_WAIT_DIP" or (rsi_val is not None and rsi_val > 70):
        dca_guidance = (
            "Harga sedang overextended jauh di atas rata-rata historis; utamakan cicil DCA nominal kecil "
            "dan tahan alokasi ekstra hingga pullback menuju Zona Akumulasi."
        )
        dca_status = "OVEREXTENDED_WAIT_DIP"
    else:
        dca_guidance = (
            "Harga dalam fase konsolidasi wajar; jalankan DCA rutin sesuai jadwal bulanan dan manfaatkan "
            "koreksi menuju area SMA 50/200 untuk top-up."
        )
        dca_status = "NEUTRAL_DCA"

    # 2. Target Nilai Wajar 1-3 Tahun (Fair Value Target & Margin of Safety)
    dcf_fair = _safe_float(fund.get("dcf_fair_value"))
    graham = _safe_float(fund.get("graham_number"))
    mos_pct = _safe_float(fund.get("margin_of_safety_pct"))
    val_status = fund.get("valuation_signal") or "UNAVAILABLE"
    fair_source = fund.get("fair_value_source")

    if dcf_fair is not None and dcf_fair > 0:
        fv_price = _round_significant(dcf_fair)
        if mos_pct is None:
            mos_pct = round(((fv_price - price) / fv_price) * 100.0, 2)
        if not val_status or val_status == "UNAVAILABLE":
            val_status = "UNDERVALUED" if mos_pct >= 15 else ("FAIR" if mos_pct >= -15 else "OVERVALUED")
        target_1y_3y_high = _round_significant(max(fv_price, price * 1.15))
    elif graham is not None and graham > 0:
        fv_price = _round_significant(graham)
        mos_pct = round(((fv_price - price) / fv_price) * 100.0, 2)
        val_status = "UNDERVALUED" if mos_pct >= 15 else ("FAIR" if mos_pct >= -15 else "OVERVALUED")
        fair_source = "Graham Intrinsic Value"
        target_1y_3y_high = _round_significant(max(fv_price, price * 1.15))
    else:
        # Fallback for ETF / Crypto or equities without DCF: 1-3Y CAGR projection band (conservatively clamped)
        hist_cagr = _safe_float(lt.get("cagr_3y_pct")) or _safe_float(lt.get("cagr_1y_pct"))
        annual_est = min(0.18, max(0.08, (hist_cagr / 100.0) if hist_cagr is not None else 0.10))
        fv_price = _round_significant(price * ((1.0 + annual_est) ** 2))
        target_1y_3y_high = _round_significant(price * ((1.0 + annual_est) ** 3))
        mos_pct = None
        val_status = "CAGR_PROJECTION"
        fair_source = "1-3Y Historical CAGR Band (Bukan DCF)"

    # 3. Kondisi Invalidasi Tesis (Fundamental Exit Trigger - bukan stop loss harian)
    invalidation_triggers: List[str] = []
    if is_syariah:
        invalidation_triggers.append("Saham dikeluarkan dari daftar efek syariah (ISSI / DES OJK).")
        invalidation_triggers.append("Rasio utang berbunga / total aset menembus > 45% atau pendapatan non-halal > 10%.")
    if norm in {"ihsg", "us_stock"}:
        invalidation_triggers.extend([
            "Piotroski F-Score turun ke < 4/9 atau Altman Z-Score masuk zona distress (< 1.8).",
            "Kontraksi struktural pendapatan & laba bersih > 2 kuartal beruntun disertai arus kas bebas (FCF) negatif berkepanjangan.",
            "Kenaikan Debt-to-Equity drastis dengan Interest Coverage < 1.5x.",
        ])
    elif norm == "us_etf":
        invalidation_triggers.extend([
            "Perubahan mandat indeks acuan atau kenaikan tajam Expense Ratio dibanding peer.",
            "Penurunan drastis likuiditas atau penyusutan AUM yang mengganggu tracking error.",
        ])
    elif norm == "crypto":
        invalidation_triggers.extend([
            "Penurunan struktural TVL & Protocol Revenue > 50% secara berkelanjutan (bukan sekadar fluktuasi harga).",
            "Risiko dilusi ekstrem akibat jadwal token unlock besar tanpa pertumbuhan adopsi pengguna nyata.",
            "Kerusakan fundamental jaringan (insiden keamanan/eksploitasi fatal atau pelarangan regulasi inti).",
        ])

    return {
        "reference_price": _round_significant(price),
        "accumulation_zone": {
            "ideal_low": ideal_low,
            "ideal_high": ideal_high,
            "status": dca_status,
            "guidance": dca_guidance,
        },
        "fair_value_target": {
            "fair_value": fv_price,
            "horizon_3y_upper": target_1y_3y_high,
            "margin_of_safety_pct": mos_pct,
            "valuation_status": val_status,
            "source": fair_source or "Valuation Estimate",
        },
        "thesis_invalidation": {
            "summary": " ".join(invalidation_triggers[:2]),
            "triggers": invalidation_triggers,
        },
    }


def compute_indicators(
    closes: List[float],
    volume: Optional[float],
    candles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute a compact technical-indicator summary from a close-price series and optional candles."""
    ind: Dict[str, Any] = {}
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    rsi = _rsi(closes, 14)
    macd = _macd(closes)
    if sma20 is not None:
        ind["sma20"] = _round_significant(sma20)
    if sma50 is not None:
        ind["sma50"] = _round_significant(sma50)
    if sma200 is not None:
        ind["sma200"] = _round_significant(sma200)
    if rsi is not None:
        ind["rsi"] = round(rsi, 1)
    if macd is not None:
        ind["macd"] = macd["trend"]
        ind["macd_line"] = _round_significant(macd["macd"])
        ind["macd_signal"] = _round_significant(macd["signal"])
        ind["macd_histogram"] = _round_significant(macd["histogram"])
    if volume is not None:
        ind["volume"] = volume

    if candles:
        atr = compute_atr(candles, 14)
        lookback = min(len(candles), 50) if len(candles) >= 20 else len(candles)
        sup, res = compute_support_resistance(candles, lookback) if lookback >= 5 else (None, None)
        if atr is not None:
            ind["atr14"] = _round_significant(atr)
        if sup is not None:
            ind["support"] = sup
        if res is not None:
            ind["resistance"] = res

        if closes:
            zones = calculate_investment_zones(closes[-1], ind)
            if zones:
                ind["investment_zones"] = zones

    return ind


def resolve_yahoo_symbol(market: str, symbol: str) -> str:
    """Maps a user-facing symbol to a Yahoo Finance ticker."""
    norm = _normalize_market(market)
    s = symbol.strip().upper()
    if norm == "crypto":
        base = s.split("/")[0].split("-")[0]
        return f"{base}-USD"
    if norm == "ihsg" or "ihsg" in (market or "").lower() or "syariah" in (market or "").lower():
        if not s.endswith(".JK"):
            return f"{s}.JK"
    return s


def resolve_stooq_symbol(market: str, symbol: str) -> Optional[str]:
    """Maps a user-facing symbol to a Stooq ticker (US stocks and US ETFs)."""
    norm = _normalize_market(market)
    s = symbol.strip().lower()
    if norm in {"us_stock", "us_etf"} and s:
        return f"{s}.us"
    return None


def _fetch_stooq_quote(stooq_symbol: str) -> Dict[str, Any]:
    """Fetches a daily quote from Stooq's free CSV endpoint (stocks fallback)."""
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(stooq_symbol)}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", "ignore")
    except Exception as e:
        raise MarketDataError(f"Stooq request failed for {stooq_symbol}: {e}") from e

    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise MarketDataError(f"Stooq returned no data for {stooq_symbol}")

    header = [h.strip().lower() for h in rows[0]]
    try:
        idx_date = header.index("date")
        idx_open = header.index("open")
        idx_high = header.index("high")
        idx_low = header.index("low")
        idx_close = header.index("close")
    except ValueError:
        raise MarketDataError(f"Stooq returned an unexpected format for {stooq_symbol}")

    candles: List[Dict[str, Any]] = []
    for row in rows[1:]:
        if len(row) <= idx_close:
            continue
        o = _safe_float(row[idx_open])
        h = _safe_float(row[idx_high])
        l = _safe_float(row[idx_low])
        c = _safe_float(row[idx_close])
        if o is None or h is None or l is None or c is None:
            continue
        candles.append({"open": o, "high": h, "low": l, "close": c})

    if len(candles) < 2:
        raise MarketDataError(f"Stooq returned insufficient data for {stooq_symbol}")

    price = candles[-1]["close"]
    prev_close = candles[-2]["close"]
    change_pct = (
        round((price - prev_close) / prev_close * 100, 2)
        if prev_close is not None and prev_close != 0
        else None
    )

    return {
        "provider": "stooq",
        "price": price,
        "change_pct": change_pct,
        "source_as_of": rows[-1][idx_date],
        "candles": candles[-MAX_CANDLES:],
    }


def _fetch_yahoo(
    yahoo_symbol: str, interval: str, period: str, resample: Optional[str] = None
) -> Dict[str, Any]:
    """Fetches OHLCV data from Yahoo Finance using the yfinance library."""
    try:
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=False, prepost=False)
    except Exception as e:
        raise MarketDataError(f"yfinance failed to load {yahoo_symbol}: {e}") from e

    if df is None or df.empty:
        raise MarketDataError(f"No data from Yahoo Finance for {yahoo_symbol}")

    # Downsample when requested (e.g. build 4H candles from 1H data).
    if resample:
        agg: Dict[str, str] = {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
        }
        if "Volume" in df.columns:
            agg["Volume"] = "sum"
        df = df.resample(resample).agg(agg)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        if df.empty:
            raise MarketDataError(f"No candle data after resampling for {yahoo_symbol}")

    # Current price and previous close (24h change reference).
    price = _current_price(ticker, df)
    prev_close = _previous_close(ticker, df)

    candles: List[Dict[str, Any]] = []
    for idx, row in df.iterrows():
        o = _safe_float(row.get("Open"))
        h = _safe_float(row.get("High"))
        l = _safe_float(row.get("Low"))
        c = _safe_float(row.get("Close"))
        if o is None or h is None or l is None or c is None:
            continue
        candle: Dict[str, Any] = {
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "time": int(idx.timestamp()),
        }
        if "Volume" in row:
            v = _safe_float(row.get("Volume"))
            if v is not None:
                candle["volume"] = v
        candles.append(candle)

    if not candles:
        raise MarketDataError(f"No candle data from Yahoo Finance for {yahoo_symbol}")

    if price is None:
        price = candles[-1]["close"]

    prev_close = _safe_float(prev_close)
    price = _safe_float(price)
    if price is not None:
        price = _round_significant(price, 7)
    change_pct = None
    if prev_close is not None and prev_close != 0 and price is not None:
        change_pct = round((price - prev_close) / prev_close * 100, 2)

    return {
        "provider": "yahoo",
        "price": price,
        "change_pct": change_pct,
        "change_period": "daily_close_to_close",
        "source_as_of": candles[-1].get("time"),
        "candles": candles[-MAX_CANDLES:],
    }


def _current_price(ticker: Any, df: Any) -> Optional[float]:
    """Best-effort current (intraday) price."""
    price = None
    try:
        fi = ticker.fast_info
        if isinstance(fi, dict):
            price = fi.get("last_price")
        else:
            price = getattr(fi, "last_price", None)
    except Exception:
        pass
    if price is None and not df.empty:
        price = _safe_float(df["Close"].iloc[-1])
    return price


def _previous_close(ticker: Any, df: Any) -> Optional[float]:
    """Best-effort previous daily close (for 24h change)."""
    prev_close = None
    try:
        fi = ticker.fast_info
        if isinstance(fi, dict):
            prev_close = fi.get("previous_close")
        else:
            prev_close = getattr(fi, "previous_close", None)
    except Exception:
        pass
    if prev_close is None:
        # Fallback: use the previous daily bar.
        try:
            daily = ticker.history(period="5d", interval="1d")
            if daily is not None and len(daily) >= 2:
                prev_close = _safe_float(daily["Close"].iloc[-2])
        except Exception:
            pass
    if prev_close is None and len(df) >= 2:
        prev_close = _safe_float(df["Close"].iloc[-2])
    return prev_close


_YAHOO_BATCH_CACHE_TTL = 180.0
_YAHOO_MISSING_CACHE_TTL = 21600.0  # 6h negative cache for genuinely delisted/empty tickers


def _fetch_yahoo_batch(
    yahoo_symbols: List[str],
    *,
    cache_ttl: float = _YAHOO_BATCH_CACHE_TTL,
) -> Dict[str, Dict[str, Any]]:
    """Fetches price, change, and technical indicators for many tickers in one Yahoo request.

    Returns a mapping of ``yahoo_symbol -> {"price", "change_pct", ...indicators}``.
    Symbols that could not be resolved are simply omitted so callers can fall back.
    """
    if not yahoo_symbols:
        return {}

    unique_symbols: List[str] = list(dict.fromkeys(s for s in yahoo_symbols if s))
    result: Dict[str, Dict[str, Any]] = {}
    missing_symbols: List[str] = []

    for sym in unique_symbols:
        hit, cached_entry = shared_cache_get(f"yf_batch_inv_1d:{sym}")
        if hit and isinstance(cached_entry, dict):
            result[sym] = cached_entry
            continue
        neg_hit, _ = shared_cache_get(f"yf_missing_1d:{sym}")
        if neg_hit:
            continue
        missing_symbols.append(sym)

    if not missing_symbols:
        return result

    try:
        with _yfinance_lock:
            df = yf.download(
                tickers=missing_symbols,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=min(4, max(1, len(missing_symbols))),
            )
    except Exception as e:
        logger.warning("yf.download batch failed: %s", e)
        return result

    if df is None or df.empty:
        return result

    fresh_parsed: Dict[str, Dict[str, Any]] = {}
    empty_in_batch: List[str] = []

    for sym in missing_symbols:
        try:
            # group_by="ticker" yields MultiIndex columns, though fallback cleanly if flat.
            history = df[sym] if sym in df else (df if len(missing_symbols) == 1 else None)
            if history is None or getattr(history, "empty", True) or "Close" not in history:
                empty_in_batch.append(sym)
                continue
            close = history["Close"].dropna()
            if len(close) < 2:
                empty_in_batch.append(sym)
                continue
            price = _safe_float(close.iloc[-1])
            prev = _safe_float(close.iloc[-2])
            if price is None or prev is None or prev == 0:
                empty_in_batch.append(sym)
                continue
            price = _round_significant(price, 7)

            closes = [float(x) for x in close.tolist()]
            candles: List[Dict[str, Any]] = []
            for idx, row in history.iterrows():
                o = _safe_float(row.get("Open"))
                h = _safe_float(row.get("High"))
                l = _safe_float(row.get("Low"))
                c = _safe_float(row.get("Close"))
                if o is None or h is None or l is None or c is None:
                    continue
                candle: Dict[str, Any] = {
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "time": int(idx.timestamp()),
                }
                v = _safe_float(row.get("Volume"))
                if v is not None:
                    candle["volume"] = v
                candles.append(candle)

            volume = None
            try:
                vol_series = history["Volume"].dropna()
                if len(vol_series) > 0:
                    volume = _safe_float(vol_series.iloc[-1])
            except Exception:
                pass

            entry: Dict[str, Any] = {
                "price": price,
                "change_pct": round((price - prev) / prev * 100, 2),
                "change_period": "daily_close_to_close",
                "source_as_of": close.index[-1].isoformat(),
                "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "provider": "yahoo",
                "candles": candles[-MAX_CANDLES:],
            }
            entry.update(compute_indicators(closes, volume, candles=candles))
            fresh_parsed[sym] = entry
            result[sym] = entry
            if cache_ttl > 0:
                shared_cache_set(f"yf_batch_inv_1d:{sym}", entry, cache_ttl)
        except Exception as e:
            logger.warning("Batch extract failed for %s: %s", sym, e)

    # Only negative-cache missing symbols when the batch itself succeeded for peer symbols,
    # proving Yahoo Finance is reachable and the missing tickers are delisted/untraded.
    if fresh_parsed and empty_in_batch:
        for sym in empty_in_batch:
            shared_cache_set(f"yf_missing_1d:{sym}", True, _YAHOO_MISSING_CACHE_TTL, l1_ttl_seconds=3600.0)

    return result


def _crypto_market_metrics() -> str:
    """BTC dominance, total market cap, and Fear & Greed from free endpoints."""
    hit, cached = shared_cache_get("market_metrics:crypto")
    if hit and isinstance(cached, str) and cached:
        return cached

    parts: List[str] = []
    try:
        g = _http_get_json("https://api.coingecko.com/api/v3/global", timeout=5.0, max_retries=1)
        data = g.get("data", {})
        mcap = data.get("total_market_cap", {}).get("usd")
        btc_dom = data.get("market_cap_percentage", {}).get("btc")
        if mcap is not None:
            parts.append(f"Total Market Cap: ${mcap / 1e12:.2f}T (CoinGecko Global)")
        if btc_dom is not None:
            parts.append(f"BTC Dominance: {btc_dom:.1f}% (CoinGecko Global)")
        updated_at = data.get("updated_at")
        if updated_at:
            parts.append(
                "CoinGecko metrics as-of: "
                + datetime.fromtimestamp(int(updated_at), timezone.utc).isoformat(timespec="seconds")
            )
    except Exception as e:
        logger.warning("CoinGecko /global fetch failed: %s", e)

    try:
        fng = _http_get_json("https://api.alternative.me/fng/", timeout=5.0, max_retries=1)
        items = fng.get("data", [])
        if items:
            value = items[0].get("value")
            classification = items[0].get("value_classification")
            parts.append(f"Fear & Greed Index: {value} ({classification}; Alternative.me)")
            timestamp = items[0].get("timestamp")
            if timestamp:
                parts.append(
                    "Fear & Greed as-of: "
                    + datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat(timespec="seconds")
                )
    except Exception as e:
        logger.warning("Fear & Greed fetch failed: %s", e)

    joined = " | ".join(parts)
    if joined:
        shared_cache_set("market_metrics:crypto", joined, 120.0)
    return joined


def _index_metrics(tickers: List[str], labels: List[str]) -> str:
    cache_key = f"index_metrics:{','.join(tickers)}"
    hit, cached = shared_cache_get(cache_key)
    if hit and isinstance(cached, str) and cached:
        return cached

    try:
        with _yfinance_lock:
            df = yf.download(
                tickers=tickers,
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
    except Exception as e:
        logger.warning("Index download failed: %s", e)
        return ""

    if df is None or df.empty:
        return ""

    parts: List[str] = []
    for ticker, label in zip(tickers, labels):
        try:
            history = df[ticker] if ticker in df else (df if len(tickers) == 1 else None)
            if history is None:
                continue
            close = history["Close"].dropna()
            if len(close) < 2:
                continue
            price = _safe_float(close.iloc[-1])
            prev = _safe_float(close.iloc[-2])
            if price is None or prev is None or prev == 0:
                continue
            change = round((price - prev) / prev * 100, 2)
            bar_as_of = close.index[-1].isoformat()
            parts.append(
                f"{label}: {price:,.2f} ({change:+.2f}%; Yahoo Finance daily bar as-of {bar_as_of})"
            )
        except Exception:
            pass
    joined = " | ".join(parts)
    if joined:
        shared_cache_set(cache_key, joined, 120.0)
    return joined


def fetch_market_metrics(market: str) -> str:
    """Fetches market-level metrics relevant to the given market (best effort)."""
    norm = _normalize_market(market)
    try:
        if norm == "crypto":
            return _crypto_market_metrics()
        if norm == "us_stock":
            return _index_metrics(
                ["^GSPC", "^IXIC", "^DJI"],
                ["S&P 500", "NASDAQ", "Dow Jones"],
            )
        if norm == "us_etf":
            return _index_metrics(
                ["^VIX", "^TNX", "DX-Y.NYB", "SPY"],
                ["VIX", "US10Y", "DXY", "SPY"],
            )
        if norm == "ihsg":
            index_line = _index_metrics(["^JKSE"], ["IHSG"])
            foreign_flow_line = _ihsg_foreign_flow_metrics()
            return " | ".join(part for part in (index_line, foreign_flow_line) if part)
    except Exception as e:
        logger.warning("Market metrics fetch failed for %s: %s", market, e)
    return ""


def _ihsg_foreign_flow_metrics() -> str:
    """Best-effort aggregate IHSG net foreign flow summary for the market overview."""
    try:
        from app.foreign_flow import format_market_foreign_flow, get_idx_foreign_flow

        flow = get_idx_foreign_flow()
        if not flow:
            return ""
        return format_market_foreign_flow(flow)
    except Exception as e:
        logger.debug("IHSG foreign flow metrics unavailable: %s", e)
        return ""


def _http_get_json(url: str, timeout: float = 10.0, max_retries: int = 3) -> Any:
    """Fetches JSON from a URL with retry logic for transient failures."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    last_error = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_error = MarketDataError(f"HTTP {e.code} from {url}")
            if 400 <= e.code < 500:
                raise last_error from e
            if attempt < max_retries - 1:
                logger.warning("HTTP %d error, retrying (%d/%d): %s", e.code, attempt + 1, max_retries, url)
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise last_error from e
        except urllib.error.URLError as e:
            last_error = MarketDataError(f"URL error: {e}")
            if attempt < max_retries - 1:
                logger.warning("Network error, retrying (%d/%d): %s", attempt + 1, max_retries, url)
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise last_error from e
        except Exception as e:
            last_error = MarketDataError(f"Unexpected error: {e}")
            if attempt < max_retries - 1:
                logger.warning("Unexpected error, retrying (%d/%d): %s", attempt + 1, max_retries, url)
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise last_error from e
    raise last_error


BINANCE_API_BASE = "https://data-api.binance.vision/api/v3"
BINANCE_API_FALLBACKS = ("https://api.binance.com/api/v3",)
_BINANCE_TICKER_TTL = 20.0
_binance_ticker_cache: Dict[str, Any] = {"_cached_at": 0.0, "data": []}
_binance_ticker_lock = threading.Lock()
_BINANCE_KLINE_TTL = 30.0
_binance_kline_cache: Dict[tuple[str, str, int], Dict[str, Any]] = {}
_binance_kline_lock = threading.Lock()


def _get_binance_24h_tickers() -> List[Dict[str, Any]]:
    """Returns the public Binance 24h ticker snapshot with a short in-process cache."""
    now = time.monotonic()
    with _binance_ticker_lock:
        cached = _binance_ticker_cache
        if now - cached["_cached_at"] < _BINANCE_TICKER_TTL and cached["data"]:
            return list(cached["data"])

    data = _binance_get_json("/ticker/24hr", timeout=8.0, max_retries=1)
    if not isinstance(data, list):
        raise MarketDataError("Binance returned an invalid 24h ticker response")
    tickers = [item for item in data if isinstance(item, dict) and item.get("symbol")]
    with _binance_ticker_lock:
        _binance_ticker_cache.update({"_cached_at": now, "data": tickers})
    return tickers


def _binance_get_json(path: str, timeout: float = 8.0, max_retries: int = 1) -> Any:
    """Queries Binance public market data through reachable public-data domains."""
    last_error: Optional[MarketDataError] = None
    bases = (BINANCE_API_BASE, *BINANCE_API_FALLBACKS)
    for index, base in enumerate(bases):
        try:
            return _http_get_json(f"{base}{path}", timeout=timeout, max_retries=max_retries)
        except MarketDataError as e:
            last_error = e
            if index + 1 < len(bases):
                logger.warning("Binance endpoint %s failed; trying alternate public-data host: %s", base, e)
    raise last_error or MarketDataError("All Binance public-data endpoints failed")


def _binance_spot_symbol(symbol: str) -> Optional[str]:
    """Normalizes a crypto pair to Binance spot USDT notation."""
    raw = symbol.strip().upper().replace("-", "/")
    if "/" in raw:
        base, quote = raw.split("/", 1)
        if quote not in {"USDT", "USD"}:
            return None
    else:
        base = raw
    if not base or not base.isalnum():
        return None
    return f"{base}USDT"


def _binance_interval(timeframe: str) -> str:
    return {"1D": "1d", "1W": "1w", "1M": "1M"}.get(timeframe, "1d")


def _parse_binance_klines(rows: Any) -> List[Dict[str, Any]]:
    candles: List[Dict[str, Any]] = []
    if not isinstance(rows, list):
        return candles
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        o = _safe_float(row[1])
        h = _safe_float(row[2])
        l = _safe_float(row[3])
        c = _safe_float(row[4])
        v = _safe_float(row[5])
        if o is None or h is None or l is None or c is None:
            continue
        candle: Dict[str, Any] = {
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "time": int(row[0] / 1000),
        }
        if v is not None:
            candle["volume"] = v
        candles.append(candle)
    return candles


def _fetch_binance_klines(symbol: str, interval: str, limit: int = MAX_CANDLES) -> List[Dict[str, Any]]:
    key = (symbol.upper(), interval, limit)
    now = time.monotonic()
    with _binance_kline_lock:
        cached = _binance_kline_cache.get(key)
        if cached and now - cached["_cached_at"] < _BINANCE_KLINE_TTL:
            return [dict(candle) for candle in cached["data"]]

    params = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    rows = _binance_get_json(f"/klines?{params}", timeout=10.0, max_retries=1)
    candles = _parse_binance_klines(rows)
    if not candles:
        raise MarketDataError(f"Binance returned no candles for {symbol} ({interval})")
    with _binance_kline_lock:
        _binance_kline_cache[key] = {"_cached_at": now, "data": candles}
    return [dict(candle) for candle in candles]


def _ticker_change_pct(ticker: Dict[str, Any]) -> Optional[float]:
    value = _safe_float(ticker.get("priceChangePercent"))
    return round(value, 2) if value is not None else None


def _fetch_binance_quote(symbol: str, timeframe: str) -> Dict[str, Any]:
    """Fetches a crypto quote and candles from the same Binance spot market."""
    pair = _binance_spot_symbol(symbol)
    if pair is None:
        raise MarketDataError(f"Unsupported Binance spot symbol: {symbol}")
    params = urllib.parse.urlencode({"symbol": pair})
    ticker = _binance_get_json(f"/ticker/24hr?{params}", timeout=8.0, max_retries=1)
    candles = _fetch_binance_klines(pair, _binance_interval(timeframe), limit=MAX_CANDLES)
    price = _safe_float(ticker.get("lastPrice")) if isinstance(ticker, dict) else None
    if price is None:
        raise MarketDataError(f"Binance returned no current price for {pair}")
    return {
        "provider": "binance",
        "price": price,
        "change_pct": _ticker_change_pct(ticker),
        "change_period": "rolling_24h",
        "source_as_of": candles[-1]["time"],
        "candles": candles[-MAX_CANDLES:],
    }


def _fetch_binance_batch(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetches rolling 24h quotes and daily candles for a crypto candidate batch."""
    if not symbols:
        return {}
    tickers = _get_binance_24h_tickers()
    ticker_by_pair = {str(item.get("symbol", "")).upper(): item for item in tickers}
    normalized: List[tuple[str, str]] = []
    for display_symbol in symbols:
        pair = _binance_spot_symbol(display_symbol)
        if pair and pair in ticker_by_pair:
            normalized.append((display_symbol, pair))
    if not normalized:
        return {}

    def fetch_one(item: tuple[str, str]) -> tuple[str, Optional[Dict[str, Any]]]:
        display_symbol, pair = item
        try:
            candles = _fetch_binance_klines(pair, "1d", limit=220)
            ticker = ticker_by_pair[pair]
            price = _safe_float(ticker.get("lastPrice"))
            if price is None or len(candles) < 2:
                return display_symbol, None
            closes = [c["close"] for c in candles]
            volume = candles[-1].get("volume")
            entry: Dict[str, Any] = {
                "price": price,
                "change_pct": _ticker_change_pct(ticker),
                "change_period": "rolling_24h",
                "source_as_of": candles[-1]["time"],
                "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "provider": "binance",
                "candles": candles,
                "volume": volume,
            }
            entry.update(compute_indicators(closes, volume, candles=candles))
            return display_symbol, entry
        except Exception as e:
            logger.warning("Binance batch fetch failed for %s: %s", display_symbol, e)
            return display_symbol, None

    result: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(normalized))) as pool:
        for display_symbol, data in pool.map(fetch_one, normalized):
            if data is not None:
                result[display_symbol] = data
    return result


def is_source_data_fresh(
    source_as_of: Any,
    market: str,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Rejects missing or old market bars before they are used for recommendations."""
    if source_as_of is None:
        return False
    try:
        if isinstance(source_as_of, (int, float)):
            observed = datetime.fromtimestamp(source_as_of, timezone.utc)
        else:
            raw = str(source_as_of).strip()
            try:
                observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                observed = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            observed = observed.astimezone(timezone.utc)
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age_seconds = (current - observed).total_seconds()
        max_age_seconds = 48 * 3600 if _normalize_market(market) == "crypto" else 5 * 24 * 3600
        return 0 <= age_seconds <= max_age_seconds
    except (TypeError, ValueError, OSError, OverflowError):
        return False


_fx_cache: Dict[str, Any] = {}
_fx_cache_lock = threading.Lock()
FX_CACHE_TTL = 300.0
FX_FAILURE_CACHE_TTL = 15.0


def get_usd_idr_rate() -> Dict[str, Any]:
    """Gets an indicative USD/IDR reference rate; never substitutes a hardcoded rate.

    Yahoo Finance is tried first. Public daily reference-rate APIs are fallbacks.
    Every returned rate is explicitly labeled non-real-time because none of these
    free sources guarantees an executable live FX quote.
    """
    now_mono = time.monotonic()
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _fx_cache_lock:
        cached = _fx_cache.get("usd_idr")
        cached_ttl = (
            FX_CACHE_TTL
            if cached and cached["data"].get("rate") is not None
            else FX_FAILURE_CACHE_TTL
        )
        if cached and now_mono - cached["_cached_at"] < cached_ttl:
            payload = dict(cached["data"])
            payload["served_at"] = captured_at
            payload["cache_age_seconds"] = round(now_mono - cached["_cached_at"], 1)
            return payload

    result: Dict[str, Any] = {
        "rate": None,
        "provider": None,
        "source_as_of": None,
        "captured_at": captured_at,
        "served_at": captured_at,
        "cache_age_seconds": 0,
        "freshness": "non-real-time",
        "note": "Kurs indikatif; bukan feed FX streaming atau harga eksekusi.",
    }

    # Yahoo Finance FX ticker. Prefer its latest quote when available, while
    # retaining the timestamp of the latest daily bar as a freshness reference.
    try:
        ticker = yf.Ticker("USDIDR=X")
        history = ticker.history(period="5d", interval="1d", auto_adjust=False)
        source_as_of = None
        if history is not None and not history.empty:
            source_as_of = history.index[-1].isoformat()

        rate = None
        try:
            fast_info = ticker.fast_info
            rate = _safe_float(
                fast_info.get("last_price")
                if isinstance(fast_info, dict)
                else getattr(fast_info, "last_price", None)
            )
        except Exception:
            pass
        if rate is None and history is not None and not history.empty:
            rate = _safe_float(history["Close"].iloc[-1])

        if rate is not None and rate > 0:
            result.update(
                {
                    "rate": rate,
                    "provider": "Yahoo Finance USDIDR=X",
                    "source_as_of": source_as_of,
                }
            )
    except Exception as e:
        logger.warning("Yahoo USD/IDR lookup failed: %s", e)

    # Free public reference-rate fallbacks. These are daily reference rates,
    # not real-time executable FX prices.
    if result["rate"] is None:
        fallback_urls = [
            (
                "Frankfurter daily reference",
                "https://api.frankfurter.app/latest?from=USD&to=IDR",
                lambda data: (data.get("rates", {}).get("IDR"), data.get("date")),
            ),
            (
                "Open ER API daily reference",
                "https://open.er-api.com/v6/latest/USD",
                lambda data: (
                    data.get("rates", {}).get("IDR"),
                    data.get("time_last_update_utc"),
                ),
            ),
        ]
        for provider, url, extract in fallback_urls:
            try:
                data = _http_get_json(url, timeout=8.0)
                raw_rate, source_as_of = extract(data)
                rate = _safe_float(raw_rate)
                if rate is not None and rate > 0:
                    result.update(
                        {
                            "rate": rate,
                            "provider": provider,
                            "source_as_of": source_as_of,
                        }
                    )
                    break
            except Exception as e:
                logger.warning("%s USD/IDR lookup failed: %s", provider, e)

    with _fx_cache_lock:
        _fx_cache["usd_idr"] = {"_cached_at": now_mono, "data": dict(result)}
    return result


_coingecko_search_cache: Dict[str, Optional[str]] = {}
_orig_http_get_json = _http_get_json


def resolve_coingecko_id(symbol: str) -> Optional[str]:
    """Resolves a crypto ticker to a CoinGecko coin id (cached)."""
    base = symbol.strip().upper().split("/")[0].split("-")[0]
    if base in COINGECKO_IDS:
        return COINGECKO_IDS[base]
    if base in _coingecko_search_cache:
        return _coingecko_search_cache[base]

    use_shared_cache = _http_get_json is _orig_http_get_json
    if use_shared_cache:
        hit, cached_id = redis_get_json(f"cg_id:{base}")
        if hit and (cached_id is None or isinstance(cached_id, str)):
            _coingecko_search_cache[base] = cached_id
            return cached_id

    cg_id = None
    search_failed = False
    try:
        url = f"https://api.coingecko.com/api/v3/search?query={urllib.parse.quote(base.lower())}"
        data = _http_get_json(url, timeout=5.0, max_retries=1)
        coins = data.get("coins", [])
        matches = [
            coin
            for coin in coins
            if coin.get("symbol", "").upper() == base and coin.get("id")
        ]
        if len(matches) == 1:
            cg_id = matches[0]["id"]
        elif len(matches) > 1:
            # Disambiguate only when CoinGecko provides a strictly unique top market-cap rank;
            # otherwise refuse to guess so ambiguous unranked tickers return None.
            ranked = [
                m
                for m in matches
                if isinstance(m.get("market_cap_rank"), int)
                and not isinstance(m.get("market_cap_rank"), bool)
                and m["market_cap_rank"] > 0
            ]
            ranked.sort(key=lambda x: x["market_cap_rank"])
            if ranked and (
                len(ranked) == 1 or ranked[0]["market_cap_rank"] < ranked[1]["market_cap_rank"]
            ):
                cg_id = ranked[0]["id"]
                logger.info(
                    "CoinGecko symbol %s had %d matches; selected uniquely top-ranked '%s' (rank #%d)",
                    base,
                    len(matches),
                    cg_id,
                    ranked[0]["market_cap_rank"],
                )
            else:
                logger.warning(
                    "Ambiguous CoinGecko symbol %s (%d matches without unique rank); refusing to guess",
                    base,
                    len(matches),
                )
    except MarketDataError as e:
        search_failed = True
        logger.warning("CoinGecko search failed for %s: %s", base, e)

    if not search_failed:
        _coingecko_search_cache[base] = cg_id
        if use_shared_cache:
            redis_set_json(f"cg_id:{base}", cg_id, 86400.0 if cg_id else 3600.0)
    return cg_id


def _fetch_coingecko(cg_id: str, days: int) -> Dict[str, Any]:
    """Fetches market data from CoinGecko (crypto fallback)."""
    ohlc_url = "https://api.coingecko.com/api/v3/coins/" + urllib.parse.quote(cg_id) + "/ohlc"
    ohlc_params = urllib.parse.urlencode({"vs_currency": "usd", "days": days})
    try:
        ohlc_data = _http_get_json(f"{ohlc_url}?{ohlc_params}", timeout=15.0)
    except MarketDataError as e:
        logger.warning("CoinGecko OHLC fetch failed for %s: %s", cg_id, e)
        raise

    candles = []
    for row in ohlc_data:
        if len(row) != 5:
            continue
        ts, o, h, l, c = row
        o = _safe_float(o)
        h = _safe_float(h)
        l = _safe_float(l)
        c = _safe_float(c)
        if o is None or h is None or l is None or c is None:
            continue
        candles.append({"open": o, "high": h, "low": l, "close": c, "time": int(ts / 1000)})

    price = None
    change_pct = None
    try:
        price_url = "https://api.coingecko.com/api/v3/simple/price"
        price_params = urllib.parse.urlencode(
            {"ids": cg_id, "vs_currencies": "usd", "include_24hr_change": "true"}
        )
        price_data = _http_get_json(f"{price_url}?{price_params}", timeout=10.0)
        info = price_data.get(cg_id, {})
        price = _safe_float(info.get("usd"))
        raw_change_pct = _safe_float(info.get("usd_24h_change"))
        if raw_change_pct is not None:
            change_pct = round(raw_change_pct, 2)
    except MarketDataError as e:
        logger.warning("CoinGecko price fetch failed for %s: %s", cg_id, e)

    if not candles:
        raise MarketDataError(f"No candle data from CoinGecko for {cg_id}")

    if price is None:
        price = candles[-1]["close"]

    return {
        "provider": "coingecko",
        "price": price,
        "change_pct": change_pct,
        "source_as_of": candles[-1].get("time"),
        "candles": candles[-MAX_CANDLES:],
    }


_quote_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()
CACHE_TTL = 20.0


def _twelvedata_symbol(market: str, symbol: str) -> Optional[str]:
    """Formats symbol for Twelve Data API; returns None for unsupported markets like IDX."""
    norm = _normalize_market(market)
    s = symbol.strip().upper()
    if norm == "crypto":
        base = s.split("/")[0].split("-")[0]
        return f"{base}/USD"
    if norm == "ihsg" or s.endswith(".JK"):
        return None  # Twelve Data free tier does not cover IDX
    return s


def _fetch_twelvedata_series(td_symbol: str, interval: str, outputsize: int) -> List[float]:
    """Fetches chronological closes (oldest -> newest) from Twelve Data API."""
    api_key = (getattr(settings, "TWELVE_DATA_API_KEY", "") or "").strip()
    if not api_key or not td_symbol:
        return []
    params = urllib.parse.urlencode(
        {
            "symbol": td_symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": api_key,
            "order": "ASC",
        }
    )
    try:
        data = _http_get_json(f"https://api.twelvedata.com/time_series?{params}", timeout=10.0, max_retries=1)
        if not isinstance(data, dict) or data.get("status") != "ok":
            return []
        values = data.get("values") or []
        closes = [_safe_float(v.get("close")) for v in values]
        return [c for c in closes if c is not None and c > 0]
    except Exception as e:
        logger.debug("Twelve Data time_series failed for %s (%s): %s", td_symbol, interval, e)
        return []


def _compute_max_drawdown_pct(closes: List[float]) -> Optional[float]:
    """Computes maximum peak-to-trough percentage drawdown (negative pct, e.g. -25.4)."""
    if len(closes) < 5:
        return None
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (c - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return round(max_dd * 100.0, 2)


def _compute_annualized_volatility_pct(closes: List[float], periods_per_year: int) -> Optional[float]:
    """Computes annualized standard deviation of daily returns in percent."""
    if len(closes) < 20:
        return None
    rets: List[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev > 0:
            rets.append((closes[i] - prev) / prev)
    if len(rets) < 15:
        return None
    mean_r = sum(rets) / len(rets)
    var = sum((r - mean_r) ** 2 for r in rets) / (len(rets) - 1)
    vol = math.sqrt(max(0.0, var)) * math.sqrt(periods_per_year) * 100.0
    return round(vol, 2) if math.isfinite(vol) else None


def _compute_period_cagr(closes: List[float], bars_back: int, years: float) -> Optional[float]:
    """Computes annualized CAGR (%) across `bars_back` bars over `years` years."""
    if len(closes) < 2 or years <= 0:
        return None
    idx = -min(len(closes), bars_back)
    start_val = closes[idx]
    end_val = closes[-1]
    effective_years = years if len(closes) >= bars_back else years * (len(closes) / float(bars_back))
    if start_val <= 0 or end_val <= 0 or effective_years < 0.7:
        return None
    cagr = ((end_val / start_val) ** (1.0 / effective_years) - 1.0) * 100.0
    return round(cagr, 2) if math.isfinite(cagr) else None


def fetch_long_term_market_metrics(market: str, symbol: str) -> Dict[str, Any]:
    """Fetches multi-year historical data (Twelve Data primary, yfinance/Binance fallback)
    to compute long-term investing metrics: 1Y/3Y/5Y CAGR, Max Drawdown, Annualized
    Volatility, SMA 50-Day, SMA 200-Day, SMA 200-Week, and market cycle position.
    """
    norm = _normalize_market(market)
    cache_key = f"lt_metrics:{norm}:{symbol.upper()}"
    hit, cached = shared_cache_get(cache_key)
    if hit and isinstance(cached, dict):
        return cached

    daily_closes: List[float] = []
    weekly_closes: List[float] = []
    provider = None

    td_sym = _twelvedata_symbol(market, symbol)
    if td_sym and (getattr(settings, "TWELVE_DATA_API_KEY", "") or "").strip():
        daily_closes = _fetch_twelvedata_series(td_sym, "1day", 1280)
        weekly_closes = _fetch_twelvedata_series(td_sym, "1week", 260)
        if daily_closes or weekly_closes:
            provider = "Twelve Data (Multi-Year)"

    # Graceful fallback to Yahoo Finance (or Binance for crypto)
    if len(daily_closes) < 200:
        if norm == "crypto":
            pair = _binance_spot_symbol(symbol)
            if pair:
                try:
                    c_1d = _fetch_binance_klines(pair, "1d", limit=1000)
                    c_1w = _fetch_binance_klines(pair, "1w", limit=260)
                    if not daily_closes:
                        daily_closes = [c["close"] for c in c_1d if c.get("close")]
                    if not weekly_closes:
                        weekly_closes = [c["close"] for c in c_1w if c.get("close")]
                    if daily_closes:
                        provider = "Binance Historical (Fallback)"
                except Exception as e:
                    logger.debug("Binance multi-year fallback failed for %s: %s", symbol, e)

        if len(daily_closes) < 200:
            ys = resolve_yahoo_symbol(market, symbol)
            try:
                t = yf.Ticker(ys)
                if not daily_closes:
                    hd = t.history(period="5y", interval="1d", auto_adjust=True)
                    if hd is not None and not hd.empty and "Close" in hd:
                        daily_closes = [float(x) for x in hd["Close"].dropna().tolist() if float(x) > 0]
                if not weekly_closes:
                    hw = t.history(period="5y", interval="1wk", auto_adjust=True)
                    if hw is not None and not hw.empty and "Close" in hw:
                        weekly_closes = [float(x) for x in hw["Close"].dropna().tolist() if float(x) > 0]
                if daily_closes and not provider:
                    provider = "Yahoo Finance 5Y History"
            except Exception as e:
                logger.warning("Yahoo multi-year fallback failed for %s: %s", symbol, e)

    is_crypto = norm == "crypto"
    trading_days_1y = 365 if is_crypto else 252
    cagr_1y = _compute_period_cagr(daily_closes, trading_days_1y, 1.0)
    cagr_3y = _compute_period_cagr(weekly_closes, 156, 3.0) or _compute_period_cagr(daily_closes, trading_days_1y * 3, 3.0)
    cagr_5y = _compute_period_cagr(weekly_closes, 260, 5.0) or _compute_period_cagr(daily_closes, trading_days_1y * 5, 5.0)

    max_dd = _compute_max_drawdown_pct(daily_closes or weekly_closes)
    ann_vol = _compute_annualized_volatility_pct(daily_closes, trading_days_1y)

    curr_p = daily_closes[-1] if daily_closes else (weekly_closes[-1] if weekly_closes else None)
    sma50_d = _sma(daily_closes, 50)
    sma200_d = _sma(daily_closes, 200)
    sma200_w = _sma(weekly_closes, 200)

    def _pct_diff(p: Optional[float], ref: Optional[float]) -> Optional[float]:
        if p is None or ref is None or ref <= 0:
            return None
        return round(((p - ref) / ref) * 100.0, 2)

    vs_sma50 = _pct_diff(curr_p, sma50_d)
    vs_sma200 = _pct_diff(curr_p, sma200_d)
    vs_sma200w = _pct_diff(curr_p, sma200_w)

    rsi_1d = _rsi(daily_closes, 14) if len(daily_closes) >= 15 else None
    cycle_position = "NEUTRAL_CONSOLIDATION"
    if vs_sma200 is not None:
        if vs_sma200 <= -5.0 or (vs_sma200w is not None and vs_sma200w <= 5.0) or (vs_sma200 <= 3.0 and rsi_1d is not None and rsi_1d <= 45):
            cycle_position = "DEEP_VALUE_ACCUMULATION"
        elif vs_sma200 >= 22.0 or (rsi_1d is not None and rsi_1d >= 72.0 and (vs_sma50 is not None and vs_sma50 >= 10.0)):
            cycle_position = "OVEREXTENDED_WAIT_DIP"
        elif -5.0 < vs_sma200 < 15.0:
            cycle_position = "HEALTHY_DCA_ZONE"

    payload = {
        "available": bool(daily_closes or weekly_closes),
        "provider": provider or "UNAVAILABLE",
        "cagr_1y_pct": cagr_1y,
        "cagr_3y_pct": cagr_3y,
        "cagr_5y_pct": cagr_5y,
        "max_drawdown_pct": max_dd,
        "annualized_volatility_pct": ann_vol,
        "sma50_day": _round_significant(sma50_d) if sma50_d is not None else None,
        "sma200_day": _round_significant(sma200_d) if sma200_d is not None else None,
        "sma200_week": _round_significant(sma200_w) if sma200_w is not None else None,
        "price_vs_sma50_pct": vs_sma50,
        "price_vs_sma200_pct": vs_sma200,
        "price_vs_sma200w_pct": vs_sma200w,
        "cycle_position": cycle_position,
    }
    if payload["available"]:
        shared_cache_set(cache_key, payload, 1800.0)
    return payload


def get_market_quote(market: str, symbol: str, timeframe: str = "1D") -> Dict[str, Any]:
    """Fetches crypto quotes from Binance first and equity quotes from Yahoo Finance."""
    tf = timeframe if timeframe in TIMEFRAME_CONFIG else "1D"
    cfg = TIMEFRAME_CONFIG[tf]
    norm = _normalize_market(market)
    cache_key = f"{norm}:{symbol.upper()}:{tf}"

    now = time.monotonic()
    with _cache_lock:
        cached = _quote_cache.get(cache_key)
        if cached and now - cached["_ts"] < CACHE_TTL:
            return cached["_data"]

    hit_redis, redis_payload = redis_get_json(f"quote:{cache_key}")
    if hit_redis and isinstance(redis_payload, dict):
        with _cache_lock:
            _quote_cache[cache_key] = {"_ts": now, "_data": redis_payload}
        return redis_payload

    result = None

    if norm == "crypto":
        try:
            result = _fetch_binance_quote(symbol, tf)
        except MarketDataError as e:
            logger.warning("Binance spot quote failed for %s: %s", symbol, e)

    # Yahoo Finance is primary for equities and a secondary crypto provider.
    if result is None:
        yahoo_symbol = resolve_yahoo_symbol(market, symbol)
        for attempt in range(PRIMARY_RETRIES):
            try:
                result = _fetch_yahoo(
                    yahoo_symbol,
                    cfg["interval"],
                    cfg["period"],
                    cfg.get("resample"),
                )
                break
            except MarketDataError as e:
                logger.warning(
                    "Yahoo (yfinance) fetch attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    PRIMARY_RETRIES,
                    symbol,
                    e,
                )
                if attempt < PRIMARY_RETRIES - 1:
                    time.sleep(PRIMARY_RETRY_BASE_DELAY * (2 ** attempt))

    # Fallback to an alternate provider when the primary source failed.
    if result is None:
        if norm == "crypto":
            cg_id = resolve_coingecko_id(symbol)
            if cg_id:
                try:
                    result = _fetch_coingecko(cg_id, COINGECKO_DAYS.get(tf, 90))
                except MarketDataError as cg_err:
                    logger.warning("CoinGecko fetch failed for %s: %s", symbol, cg_err)
        else:
            stooq_symbol = resolve_stooq_symbol(market, symbol)
            if stooq_symbol:
                try:
                    result = _fetch_stooq_quote(stooq_symbol)
                except MarketDataError as stooq_err:
                    logger.warning("Stooq fetch failed for %s: %s", symbol, stooq_err)

    if result is None:
        raise MarketDataError(f"Unable to fetch market data for {symbol}")

    payload = {
        "market": norm,
        "symbol": symbol.upper(),
        "provider": result["provider"],
        "price": result["price"],
        "change_pct": result["change_pct"],
        "change_period": result.get("change_period", "daily_close_to_close"),
        "source_as_of": result.get("source_as_of") or (
            result.get("candles", [])[-1].get("time") if result.get("candles") else None
        ),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candles": result["candles"],
    }

    with _cache_lock:
        _quote_cache[cache_key] = {"_ts": now, "_data": payload}
    redis_set_json(f"quote:{cache_key}", payload, CACHE_TTL)

    return payload


def fetch_snapshot(
    market: str,
    symbols: List[str],
    on_error: Optional[Callable[[str, str], None]] = None,
    preferred_provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetches a compact price/change snapshot for a watchlist of symbols."""
    norm = _normalize_market(market)
    snapshot_captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    yahoo_symbols = [resolve_yahoo_symbol(market, s) for s in symbols]
    if norm == "crypto" and preferred_provider == "yahoo":
        batch = _fetch_yahoo_batch(yahoo_symbols)
    elif norm == "crypto":
        try:
            batch = _fetch_binance_batch(symbols)
        except Exception as e:
            logger.warning("Binance batch snapshot failed; attempting per-symbol fallback: %s", e)
            batch = {}
    else:
        batch = _fetch_yahoo_batch(yahoo_symbols)

    results: List[Dict[str, Any]] = []
    for s, ys in zip(symbols, yahoo_symbols):
        batch_key = ys if norm != "crypto" or preferred_provider == "yahoo" else s
        if batch_key in batch:
            b = batch[batch_key]
            results.append(
                {
                    "symbol": s,
                    "price": b["price"],
                    "change_pct": b["change_pct"],
                    "change_period": b.get("change_period", "daily_close_to_close"),
                    "provider": b.get("provider", "yahoo"),
                    "source_as_of": b.get("source_as_of"),
                    "captured_at": b.get("captured_at", snapshot_captured_at),
                    "volume": b.get("volume"),
                    "sma20": b.get("sma20"),
                    "sma50": b.get("sma50"),
                    "sma200": b.get("sma200"),
                    "rsi": b.get("rsi"),
                    "macd": b.get("macd"),
                    "macd_line": b.get("macd_line"),
                    "macd_signal": b.get("macd_signal"),
                    "macd_histogram": b.get("macd_histogram"),
                    "atr14": b.get("atr14"),
                    "support": b.get("support"),
                    "resistance": b.get("resistance"),
                    "investment_zones": b.get("investment_zones"),
                }
            )
            continue

        item: Optional[Dict[str, Any]] = None

        # A Yahoo-scored crypto fallback must stay on Yahoo; do not silently switch provider.
        if not (norm == "crypto" and preferred_provider == "yahoo"):
            try:
                q = get_market_quote(market, s, "1D")
                item = {
                    "symbol": s,
                    "price": q["price"],
                    "change_pct": q["change_pct"],
                    "change_period": q.get("change_period", "daily_close_to_close"),
                    "provider": q["provider"],
                    "source_as_of": q.get("source_as_of"),
                    "captured_at": q.get("captured_at") or snapshot_captured_at,
                }
            except MarketDataError:
                pass

        # Fallback 2: alternate provider (CoinGecko for crypto, Stooq for stocks).
        if item is None and not (norm == "crypto" and preferred_provider == "yahoo"):
            try:
                if norm == "crypto":
                    cg_id = resolve_coingecko_id(s)
                    if cg_id:
                        q = _fetch_coingecko(cg_id, 1)
                        item = {
                            "symbol": s,
                            "price": q["price"],
                            "change_pct": q["change_pct"],
                            "change_period": "rolling_24h",
                            "provider": "coingecko",
                            "source_as_of": q.get("source_as_of"),
                            "captured_at": snapshot_captured_at,
                        }
                else:
                    stooq_symbol = resolve_stooq_symbol(market, s)
                    if stooq_symbol:
                        q = _fetch_stooq_quote(stooq_symbol)
                        item = {
                            "symbol": s,
                            "price": q["price"],
                            "change_pct": q["change_pct"],
                            "change_period": "daily_close_to_close",
                            "provider": "stooq",
                            "source_as_of": q.get("source_as_of"),
                            "captured_at": snapshot_captured_at,
                        }
            except MarketDataError as e:
                if on_error:
                    on_error(s, str(e))

        if item is None:
            if on_error:
                on_error(s, "no provider returned data")
            results.append({"symbol": s, "error": "unavailable"})
        else:
            results.append(item)

    return results
