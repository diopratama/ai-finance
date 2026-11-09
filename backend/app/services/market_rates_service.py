import logging
import re
import time
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Fallback default constants (reflecting current realistic market baseline)
DEFAULT_USD_IDR: float = 16850.0
DEFAULT_GOLD_IDR_PER_GRAM: float = 2539000.0
DEFAULT_GOLD_BUYBACK_IDR: float = 2373000.0
DEFAULT_GOLD_SPOT_IDR: float = 2390000.0
DEFAULT_GOLD_XAU_USD: float = 4110.0
TROY_OUNCE_GRAMS: float = 31.1034768
CACHE_TTL_SECONDS: int = 1200  # 20 minutes

# In-memory rate cache
_rates_cache: Dict[str, Any] = {
    "usd_idr": DEFAULT_USD_IDR,
    "gold_idr_per_gram": DEFAULT_GOLD_IDR_PER_GRAM,
    "gold_antam_idr": DEFAULT_GOLD_IDR_PER_GRAM,
    "gold_buyback_idr": DEFAULT_GOLD_BUYBACK_IDR,
    "gold_spot_idr": DEFAULT_GOLD_SPOT_IDR,
    "gold_xau_usd": DEFAULT_GOLD_XAU_USD,
    "last_updated": 0.0,
    "source": "FALLBACK_INITIAL",
}

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _is_cache_fresh() -> bool:
    return (time.time() - _rates_cache.get("last_updated", 0.0)) < CACHE_TTL_SECONDS


def _parse_idr_digits(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d]", "", raw or "")
    if not cleaned:
        return None
    val = float(cleaned)
    if 1_000_000 <= val <= 10_000_000:
        return val
    return None


def _fetch_antam_retail_prices(client: httpx.Client) -> Dict[str, Any]:
    """
    Scrapes live Indonesian Antam 1-gram retail buy & buyback prices from
    trusted Indonesian bullion portals (IndoGold & Aneka Logam).
    """
    result: Dict[str, Any] = {}

    # Source A: IndoGold (Harga Emas Hari Ini - Antam 1 gram)
    try:
        res = client.get("https://www.indogold.id/harga-emas-hari-ini", headers=_BROWSER_HEADERS)
        if res.status_code == 200:
            html_text = res.text
            # Meta description pattern:
            # "Harga Beli Rp 2.539.000/gram, Harga Jual/Buyback Rp 2.373.000/gram"
            m = re.search(
                r"Harga\s+Beli\s+Rp\s*([\d.]+)\s*/\s*gram.*?Buyback\s+Rp\s*([\d.]+)\s*/\s*gram",
                html_text,
                re.IGNORECASE | re.DOTALL,
            )
            if m:
                buy = _parse_idr_digits(m.group(1))
                buyback = _parse_idr_digits(m.group(2))
                if buy:
                    result["gold_antam_idr"] = buy
                    result["source_antam"] = "IndoGold Antam"
                if buyback:
                    result["gold_buyback_idr"] = buyback
    except Exception as e:
        logger.debug("IndoGold Antam fetch notice: %s", e)

    # Source B: Aneka Logam (if IndoGold didn't return both buy and buyback)
    if "gold_antam_idr" not in result:
        try:
            res = client.get("https://anekalogam.co.id/id", headers=_BROWSER_HEADERS)
            if res.status_code == 200:
                html_text = res.text
                # Look for 1gram price or Harga Jual / Harga Beli
                m_1g = re.search(r"1\s*gram\s*Rp\s*([\d.]+)", html_text, re.IGNORECASE)
                m_buyback = re.search(r"Harga\s+Beli\s*Rp\s*([\d.]+)", html_text, re.IGNORECASE)
                if m_1g:
                    buy = _parse_idr_digits(m_1g.group(1))
                    if buy:
                        result["gold_antam_idr"] = buy
                        result["source_antam"] = "AnekaLogam Antam"
                if m_buyback and "gold_buyback_idr" not in result:
                    bb = _parse_idr_digits(m_buyback.group(1))
                    if bb:
                        result["gold_buyback_idr"] = bb
        except Exception as e:
            logger.debug("AnekaLogam Antam fetch notice: %s", e)

    return result


def _build_rates_response(cache_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "usd_idr": cache_data["usd_idr"],
        "usd_to_idr": cache_data["usd_idr"],
        "gold_idr_per_gram": cache_data["gold_idr_per_gram"],
        "gold_per_gram_idr": cache_data["gold_idr_per_gram"],
        "gold_antam_idr": cache_data["gold_antam_idr"],
        "gold_buyback_idr": cache_data["gold_buyback_idr"],
        "gold_spot_idr": cache_data["gold_spot_idr"],
        "gold_xau_usd": cache_data["gold_xau_usd"],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cache_data["last_updated"])),
        "source": cache_data["source"],
    }


def fetch_live_market_rates(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetches real-time USD/IDR exchange rate, Indonesian Antam Gold Price (IDR/gram),
    Buyback price, and Global Spot Gold (XAU/USD & IDR/gram).
    Uses in-memory cache (20m TTL) to stay fast and avoid external rate limits.
    """
    global _rates_cache

    if not force_refresh and _is_cache_fresh():
        return _build_rates_response(_rates_cache)

    usd_rate = _rates_cache.get("usd_idr") or DEFAULT_USD_IDR
    gold_antam = _rates_cache.get("gold_antam_idr") or DEFAULT_GOLD_IDR_PER_GRAM
    gold_buyback = _rates_cache.get("gold_buyback_idr") or DEFAULT_GOLD_BUYBACK_IDR
    gold_spot_idr = _rates_cache.get("gold_spot_idr") or DEFAULT_GOLD_SPOT_IDR
    gold_xau_usd = _rates_cache.get("gold_xau_usd") or DEFAULT_GOLD_XAU_USD
    fetched_sources = []

    with httpx.Client(timeout=4.5, follow_redirects=True) as client:
        # 1. Fetch USD/IDR from reliable FX APIs
        fx_endpoints = [
            "https://open.er-api.com/v6/latest/USD",
            "https://api.exchangerate-api.com/v4/latest/USD",
        ]
        fx_fetched = False
        for url in fx_endpoints:
            try:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    idr = data.get("rates", {}).get("IDR")
                    if idr and isinstance(idr, (int, float)) and 10000 <= idr <= 30000:
                        usd_rate = round(float(idr), 2)
                        fetched_sources.append("open.er-api (USD/IDR)")
                        fx_fetched = True
                        break
            except Exception as e:
                logger.debug("FX rate fetch failed on %s: %s", url, e)

        if not fx_fetched:
            try:
                res = client.get("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json")
                if res.status_code == 200:
                    idr = res.json().get("usd", {}).get("idr")
                    if idr and 10000 <= float(idr) <= 30000:
                        usd_rate = round(float(idr), 2)
                        fetched_sources.append("currency-api (USD/IDR)")
            except Exception as e:
                logger.debug("Fallback FX rate fetch failed: %s", e)

        # 2. Fetch Global Spot Gold (XAU/USD & XAU/IDR)
        spot_fetched = False
        try:
            res = client.get("https://api.gold-api.com/price/XAU")
            if res.status_code == 200:
                data = res.json()
                price_oz = data.get("price")
                if price_oz and isinstance(price_oz, (int, float)) and price_oz > 1000:
                    gold_xau_usd = round(float(price_oz), 2)
                    gold_spot_idr = round((gold_xau_usd * usd_rate) / TROY_OUNCE_GRAMS, 2)
                    fetched_sources.append("gold-api (Spot XAU)")
                    spot_fetched = True
        except Exception as e:
            logger.debug("gold-api fetch notice: %s", e)

        if not spot_fetched:
            try:
                res = client.get("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/xau.json")
                if res.status_code == 200:
                    xau_data = res.json().get("xau", {})
                    xau_idr = xau_data.get("idr")
                    xau_usd = xau_data.get("usd")
                    if xau_usd and float(xau_usd) > 1000:
                        gold_xau_usd = round(float(xau_usd), 2)
                    if xau_idr and float(xau_idr) > 30_000_000:
                        gold_spot_idr = round(float(xau_idr) / TROY_OUNCE_GRAMS, 2)
                        fetched_sources.append("currency-api (Spot XAU)")
                        spot_fetched = True
            except Exception as e:
                logger.debug("currency-api XAU fetch notice: %s", e)

        # 3. Fetch Indonesian Retail Antam 1-gram Buy & Buyback price
        antam_info = _fetch_antam_retail_prices(client)
        if "gold_antam_idr" in antam_info:
            gold_antam = antam_info["gold_antam_idr"]
            fetched_sources.append(antam_info.get("source_antam", "Antam Retail"))
            if "gold_buyback_idr" in antam_info:
                gold_buyback = antam_info["gold_buyback_idr"]
            else:
                gold_buyback = round(gold_antam * 0.935, -3)
        elif spot_fetched:
            # If retail scraping is unreachable, estimate Indonesian retail 1g Antam from Spot (~6.2% minting/retail spread)
            gold_antam = round(gold_spot_idr * 1.062, -3)
            gold_buyback = round(gold_spot_idr * 0.992, -3)

    # Primary gold_idr_per_gram uses official Indonesian Antam 1g price
    gold_price = gold_antam
    source_label = ", ".join(fetched_sources) if fetched_sources else "CACHE_FALLBACK"

    _rates_cache = {
        "usd_idr": usd_rate,
        "gold_idr_per_gram": gold_price,
        "gold_antam_idr": gold_antam,
        "gold_buyback_idr": gold_buyback,
        "gold_spot_idr": gold_spot_idr,
        "gold_xau_usd": gold_xau_usd,
        "last_updated": time.time(),
        "source": source_label,
    }

    return _build_rates_response(_rates_cache)


def get_usd_to_idr_rate() -> float:
    rates = fetch_live_market_rates()
    return rates["usd_idr"]


def get_gold_price_per_gram_idr() -> float:
    rates = fetch_live_market_rates()
    return rates["gold_idr_per_gram"]


def normalize_currency_unit(raw_unit: Optional[str]) -> str:
    """Normalizes currency or unit code to IDR, USD, or GRAM."""
    u = (raw_unit or "IDR").strip().upper()
    if u in ("GRAM", "GRAMS", "GR", "G", "XAU", "EMAS"):
        return "GRAM"
    if u in ("USD", "$", "DOLLAR", "US DOLLAR"):
        return "USD"
    return "IDR"


def convert_to_idr(
    amount: float,
    currency_or_unit: Optional[str] = "IDR",
    rates: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Converts amount in any supported currency/unit (IDR, USD, GRAM) to IDR base.
    """
    if not amount:
        return 0.0

    unit = normalize_currency_unit(currency_or_unit)
    if unit == "USD":
        rate = (rates.get("usd_to_idr") or rates.get("usd_idr")) if rates else get_usd_to_idr_rate()
        return round(amount * rate, 2)
    elif unit == "GRAM":
        price = (rates.get("gold_per_gram_idr") or rates.get("gold_idr_per_gram")) if rates else get_gold_price_per_gram_idr()
        return round(amount * price, 2)
    return round(float(amount), 2)


def convert_between_currencies(
    amount: float,
    from_currency: Optional[str],
    to_currency: Optional[str],
    rates: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Converts an amount from one currency/unit to another via IDR as the common pivot.
    Supports IDR, USD, and GRAM.
    """
    if not amount:
        return 0.0
    from_u = normalize_currency_unit(from_currency)
    to_u = normalize_currency_unit(to_currency)
    if from_u == to_u:
        return round(float(amount), 4)

    # 1. Convert source to IDR
    idr_val = convert_to_idr(amount, from_u, rates)

    # 2. Convert IDR to target unit
    if to_u == "IDR":
        return round(idr_val, 2)
    elif to_u == "USD":
        usd_rate = (rates.get("usd_to_idr") or rates.get("usd_idr")) if rates else get_usd_to_idr_rate()
        if not usd_rate:
            usd_rate = DEFAULT_USD_IDR
        return round(idr_val / usd_rate, 4)
    elif to_u == "GRAM":
        gold_price = (rates.get("gold_per_gram_idr") or rates.get("gold_idr_per_gram")) if rates else get_gold_price_per_gram_idr()
        if not gold_price:
            gold_price = DEFAULT_GOLD_IDR_PER_GRAM
        return round(idr_val / gold_price, 4)

    return round(idr_val, 2)


def format_currency_with_base(
    amount: float,
    currency_or_unit: Optional[str] = "IDR",
    rates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns native string and IDR base converted string.
    """
    unit = normalize_currency_unit(currency_or_unit)
    idr_val = convert_to_idr(amount, unit, rates)
    fmt_idr = f"Rp {int(round(idr_val)):,}".replace(",", ".")

    if unit == "USD":
        native = f"${amount:,.2f}"
    elif unit == "GRAM":
        native = f"{amount:,.2f} gram"
    else:
        native = f"Rp {int(round(amount)):,}".replace(",", ".")

    display = f"{native} (≈ {fmt_idr})" if unit != "IDR" else native

    return {
        "unit": unit,
        "amount": amount,
        "native": native,
        "base_idr": idr_val,
        "formatted_idr": fmt_idr,
        "display": display,
    }


def format_currency_display_string(amount: float, currency_or_unit: Optional[str] = "IDR") -> str:
    """Returns a single user-friendly string e.g. '2.50 gram (≈ Rp 6.347.500)' or '$50.00 (≈ Rp 842.500)'."""
    info = format_currency_with_base(amount, currency_or_unit)
    return info["display"]
