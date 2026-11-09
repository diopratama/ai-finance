import logging
import time
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Fallback default constants if network or external providers are unavailable
DEFAULT_USD_IDR: float = 16250.0
DEFAULT_GOLD_IDR_PER_GRAM: float = 1495000.0
CACHE_TTL_SECONDS: int = 1200  # 20 minutes

# In-memory rate cache
_rates_cache: Dict[str, Any] = {
    "usd_idr": DEFAULT_USD_IDR,
    "gold_idr_per_gram": DEFAULT_GOLD_IDR_PER_GRAM,
    "last_updated": 0.0,
    "source": "FALLBACK_INITIAL",
}


def _is_cache_fresh() -> bool:
    return (time.time() - _rates_cache.get("last_updated", 0.0)) < CACHE_TTL_SECONDS


def fetch_live_market_rates(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetches real-time USD/IDR exchange rate and Gold Price (IDR/gram).
    Uses in-memory cache to stay fast and avoid external API rate limits.
    """
    global _rates_cache

    if not force_refresh and _is_cache_fresh():
        return {
            "usd_idr": _rates_cache["usd_idr"],
            "usd_to_idr": _rates_cache["usd_idr"],
            "gold_idr_per_gram": _rates_cache["gold_idr_per_gram"],
            "gold_per_gram_idr": _rates_cache["gold_idr_per_gram"],
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_rates_cache["last_updated"])),
            "source": _rates_cache["source"],
        }

    usd_rate = _rates_cache["usd_idr"] or DEFAULT_USD_IDR
    gold_price = _rates_cache["gold_idr_per_gram"] or DEFAULT_GOLD_IDR_PER_GRAM
    fetched_sources = []

    # 1. Fetch USD/IDR from free exchange rate providers
    fx_endpoints = [
        "https://open.er-api.com/v6/latest/USD",
        "https://api.exchangerate-api.com/v4/latest/USD",
    ]
    for url in fx_endpoints:
        try:
            with httpx.Client(timeout=4.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    rates = data.get("rates", {})
                    idr = rates.get("IDR")
                    if idr and isinstance(idr, (int, float)) and 10000 <= idr <= 30000:
                        usd_rate = float(idr)
                        fetched_sources.append("open.er-api (USD/IDR)")
                        break
        except Exception as e:
            logger.debug("FX rate fetch failed on %s: %s", url, e)

    # 2. Fetch or compute Gold Price per gram in IDR
    # Spot gold XAU/USD: 1 troy ounce = 31.1034768 grams
    try:
        with httpx.Client(timeout=4.0) as client:
            res = client.get("https://open.er-api.com/v6/latest/XAU")
            if res.status_code == 200:
                data = res.json()
                xau_idr = data.get("rates", {}).get("IDR")
                if xau_idr and isinstance(xau_idr, (int, float)) and xau_idr > 0:
                    gold_price = round(float(xau_idr) / 31.1034768, 2)
                    fetched_sources.append("open.er-api (XAU/IDR)")
                else:
                    xau_usd = data.get("rates", {}).get("USD")
                    if xau_usd and isinstance(xau_usd, (int, float)) and xau_usd > 0:
                        # 1 USD in XAU -> XAU/USD price is 1 / xau_usd
                        gold_price_usd_per_oz = 1.0 / float(xau_usd)
                        gold_price = round((gold_price_usd_per_oz / 31.1034768) * usd_rate, 2)
                        fetched_sources.append("open.er-api (XAU/USD)")
    except Exception as e:
        logger.debug("Gold rate fetch notice: %s", e)

    source_label = ", ".join(fetched_sources) if fetched_sources else "CACHE_FALLBACK"
    _rates_cache = {
        "usd_idr": usd_rate,
        "gold_idr_per_gram": gold_price,
        "last_updated": time.time(),
        "source": source_label,
    }

    return {
        "usd_idr": usd_rate,
        "usd_to_idr": usd_rate,
        "gold_idr_per_gram": gold_price,
        "gold_per_gram_idr": gold_price,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_rates_cache["last_updated"])),
        "source": source_label,
    }


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


def format_currency_with_base(
    amount: float,
    currency_or_unit: Optional[str] = "IDR",
    rates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns native string and IDR base converted string.
    e.g. 10.5 GRAM -> native: '10.50 gram', base_idr: 15697500.0, formatted_idr: 'Rp 15.697.500'
         $150 USD  -> native: '$150.00', base_idr: 2437500.0, formatted_idr: 'Rp 2.437.500'
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
    """Returns a single user-friendly string e.g. '2.5 gram (≈ Rp 3.737.500)' or '$50.00 (≈ Rp 812.500)'."""
    info = format_currency_with_base(amount, currency_or_unit)
    return info["display"]

