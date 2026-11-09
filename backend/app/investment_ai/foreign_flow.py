"""IDX foreign flow provider (Foreign Buy / Foreign Sell per stock).

Reads the official IDX daily Trading Summary endpoint and exposes net foreign
flow per stock plus an aggregate market summary. The endpoint is best-effort:
IDX sits behind Cloudflare and may reject non-browser requests, and the figures
are traded shares for the regular board (end-of-day for the latest session).
When unavailable the module returns empty results so callers report UNAVAILABLE
instead of guessing.
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.investment_ai.cache_store import shared_cache_get, shared_cache_set

logger = logging.getLogger(__name__)

_IDX_STOCK_SUMMARY_URL = "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
_CACHE_TTL = 300.0
_FAILURE_CACHE_TTL = 120.0
_REQUEST_TIMEOUT = 6.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.idx.co.id/",
    "X-Requested-With": "XMLHttpRequest",
}

_CACHE_KEY = "idx:foreign_flow:latest"
_FAILURE_SENTINEL = "__UNAVAILABLE__"


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _parse_summary(raw: Any) -> Optional[Dict[str, Any]]:
    """Parses one IDX Trading Summary response into per-ticker foreign flow."""
    if not isinstance(raw, dict):
        return None
    data = raw.get("data")
    if not isinstance(data, list) or not data:
        return None

    rows: List[Dict[str, Any]] = []
    session_date: Optional[str] = None
    for item in data:
        if not isinstance(item, dict):
            continue
        code = item.get("StockCode")
        if not code:
            continue
        buy = _safe_float(item.get("ForeignBuy"))
        sell = _safe_float(item.get("ForeignSell"))
        volume = _safe_float(item.get("Volume"))
        value = _safe_float(item.get("Value"))
        date_val = item.get("Date")
        if isinstance(date_val, str) and date_val:
            session_date = session_date or date_val
        avg_price = None
        if value is not None and volume:
            avg_price = value / volume
        net_shares = None
        if buy is not None and sell is not None:
            net_shares = buy - sell
        net_value = None
        if net_shares is not None and avg_price is not None:
            net_value = net_shares * avg_price
        rows.append(
            {
                "code": str(code).strip().upper(),
                "foreign_buy": buy,
                "foreign_sell": sell,
                "net_shares": net_shares,
                "net_value": net_value,
                "volume": volume,
                "value": value,
            }
        )

    if not rows:
        return None

    total_net_value = sum(r["net_value"] for r in rows if r["net_value"] is not None)
    net_buyers = sum(1 for r in rows if (r["net_shares"] or 0) > 0)
    net_sellers = sum(1 for r in rows if (r["net_shares"] or 0) < 0)
    return {
        "session_date": session_date,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
        "total_net_value": total_net_value,
        "net_buyers": net_buyers,
        "net_sellers": net_sellers,
    }


def get_idx_foreign_flow() -> Optional[Dict[str, Any]]:
    """Returns parsed foreign flow for the latest IDX session, or None when unavailable."""
    hit, cached = shared_cache_get(_CACHE_KEY)
    if hit:
        if cached == _FAILURE_SENTINEL:
            return None
        if isinstance(cached, dict) and cached.get("rows"):
            return cached
        return None

    params = urllib.parse.urlencode({"length": 9999, "start": 0})
    url = f"{_IDX_STOCK_SUMMARY_URL}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS)
    result: Optional[Dict[str, Any]] = None
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            result = _parse_summary(raw)
    except Exception as e:
        logger.warning("IDX foreign flow fetch failed: %s", e)

    if result:
        shared_cache_set(_CACHE_KEY, result, _CACHE_TTL)
        return result
    shared_cache_set(_CACHE_KEY, _FAILURE_SENTINEL, _FAILURE_CACHE_TTL)
    return None


def _fmt_idr(value: Optional[float]) -> str:
    if value is None:
        return "UNAVAILABLE"
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(value) >= div:
            return f"Rp {value / div:+,.2f}{unit}"
    return f"Rp {value:+,.0f}"


def format_market_foreign_flow(flow: Dict[str, Any]) -> str:
    """Aggregate net foreign flow line for the market overview."""
    date_label = flow.get("session_date") or "session date unavailable"
    return (
        f"Net foreign flow (IDX Trading Summary, EOD {date_label}, estimate): "
        f"{_fmt_idr(flow.get('total_net_value'))} "
        f"({flow.get('net_buyers', 0)} net-buy / {flow.get('net_sellers', 0)} net-sell stocks)"
    )


def format_symbol_foreign_flow(flow: Dict[str, Any], symbol: str) -> str:
    """Per-symbol foreign flow context line for an IHSG ticker."""
    base = symbol.strip().upper().split(".")[0]
    row = next((r for r in flow.get("rows", []) if r["code"] == base), None)
    if row is None:
        return (
            f"- Foreign flow for {symbol}: UNAVAILABLE in the supplied IDX Trading Summary "
            "(symbol not present in latest session data)."
        )
    return (
        f"- Foreign flow for {symbol} (IDX Trading Summary, EOD {flow.get('session_date') or 'unavailable'}, "
        f"shares on regular board): Foreign buy={_fmt_shares(row.get('foreign_buy'))}, "
        f"Foreign sell={_fmt_shares(row.get('foreign_sell'))}, "
        f"Net shares={_fmt_shares(row.get('net_shares'))}, "
        f"Est. net value={_fmt_idr(row.get('net_value'))} (net shares at session average price)."
    )


def _fmt_shares(value: Optional[float]) -> str:
    if value is None:
        return "UNAVAILABLE"
    return f"{value:,.0f}"
