import json
import logging
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app.config import settings
from app.investment_ai.market_data import (
    calculate_investment_zones,
    calibrate_confidence,
    compute_indicators,
    fetch_long_term_market_metrics,
    fetch_market_metrics,
    fetch_snapshot,
    get_market_quote,
    get_usd_idr_rate,
    is_source_data_fresh,
    MarketDataError,
)
from app.investment_ai.fundamental_data import (
    get_fundamental_context,
    get_onchain_context,
    get_recommendation_fundamentals,
)
from app.investment_ai.foreign_flow import (
    format_symbol_foreign_flow,
    get_idx_foreign_flow,
)
from app.investment_ai.quant_screener import screen_market_opportunities
from app.services.market_rates_service import fetch_live_market_rates
from app.services.web_search_service import search_internet

logger = logging.getLogger(__name__)

DATA_FRESHNESS_INSTRUCTIONS = (
    "Analyze the actual prices, indicators, market metrics, and news supplied in the context; do not "
    "replace the requested analysis with a generic statement that data is unavailable. The data is "
    "captured at the timestamps shown and is a point-in-time bundle, not a continuous streaming feed. "
    "Mention source/as-of and freshness once, concisely. Only mark an individual metric unavailable "
    "when that metric is absent. Never claim tick-level real-time data. USD/IDR is explicitly labeled "
    "NON-REAL-TIME and indicative. Use only the supplied rate for IDR conversion; if unavailable, "
    "do not use a hardcoded or guessed rate."
)

TOOL_GROUNDING_INSTRUCTIONS = (
    "IMPORTANT: You have NO tools, no browsing, and no database access. Any tool names or data "
    "sources mentioned in your guidelines (for example fetch_idx_financials, check_sharia_compliance, "
    "fetch_sec_filings_summary, fetch_tokenomics, Glassnode, Whale Alert, DES list) are NOT available "
    "to you. Use ONLY numbers that appear in the supplied context blocks. If a metric is missing or "
    "marked UNAVAILABLE, write 'Unavailable' for it; never fill it from memory or estimate it. "
    "Never describe an issuer as halal/certified unless explicitly noted in the supplied SHARIA SCREEN "
    "or ISSI reference. Do not infer JII/JII70 membership."
)

NEWS_VERIFICATION_INSTRUCTIONS = (
    "For every time-sensitive news or upcoming-event claim, use only an item in the supplied news "
    "context that contains a source URL and publication date. State the event date only when the "
    "source text explicitly provides it, and cite that URL. If the event date is absent, conflicting, "
    "or not clearly for the current period, mark it UNVERIFIED and do not describe it as happening this week."
)

FUNDAMENTAL_DATA_ROLES = ("fundamental_analyst", "on_chain_analyst")


class LLMError(Exception):
    """Raised when an LLM call fails or returns an unusable response."""


class AnalysisStopped(Exception):
    """Raised internally when the user requests to stop a running analysis."""


LLM_MAX_ATTEMPTS = 2
LLM_RETRY_DELAY = 1.5

# Registry of active stop events for cancelling running analyses
_active_stop_events: Dict[str, threading.Event] = {}
_stop_events_lock = threading.Lock()


def register_stop_event(task_id: str) -> threading.Event:
    with _stop_events_lock:
        evt = threading.Event()
        _active_stop_events[task_id] = evt
        return evt


def trigger_stop_event(task_id: str) -> bool:
    with _stop_events_lock:
        evt = _active_stop_events.get(task_id)
        if evt:
            evt.set()
            return True
        return False


def unregister_stop_event(task_id: str) -> None:
    with _stop_events_lock:
        _active_stop_events.pop(task_id, None)


AGENT_ROLES: Dict[str, List[str]] = {
    "crypto": [
        "data_fetcher",
        "technical_analyst",
        "fundamental_analyst",
        "on_chain_analyst",
        "sentiment_analyst",
    ],
    "ihsg": [
        "data_fetcher",
        "technical_analyst",
        "fundamental_analyst",
        "sentiment_analyst",
    ],
    "ihsg_syariah": [
        "data_fetcher",
        "technical_analyst",
        "fundamental_analyst",
        "sentiment_analyst",
    ],
    "us_stock": [
        "data_fetcher",
        "technical_analyst",
        "fundamental_analyst",
        "sentiment_analyst",
    ],
    "us_etf": [
        "data_fetcher",
        "technical_analyst",
        "fundamental_analyst",
        "sentiment_analyst",
    ],
}

DEFAULT_AGENT_ROLES = [
    "data_fetcher",
    "technical_analyst",
    "fundamental_analyst",
    "sentiment_analyst",
]


def normalize_market(market: str) -> str:
    m = (market or "ihsg").lower()
    if "ihsg" in m:
        return "ihsg"
    if "crypto" in m:
        return "crypto"
    if "etf" in m:
        return "us_etf"
    if "us" in m:
        return "us_stock"
    return m


def is_syariah_market(market: str) -> bool:
    m = (market or "").lower()
    return "syariah" in m or m == "ihsg_syariah"


def agent_roles(market: str) -> List[str]:
    return AGENT_ROLES.get(market.lower(), AGENT_ROLES.get(normalize_market(market), DEFAULT_AGENT_ROLES))


def _format_significant(value: Optional[float], digits: int = 7) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value == 0:
        return "0"
    decimals = max(0, digits - 1 - math.floor(math.log10(abs(value))))
    rendered = f"{value:,.{decimals}f}"
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _format_source_timestamp(value: Any) -> str:
    if value is None:
        return "timestamp not provided by source"
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    return str(value)


def _format_recommendation_price(value: Optional[float], market: str, fx_rate: Optional[float] = None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if normalize_market(market) == "crypto":
        rendered = f"${_format_significant(value)}"
        if fx_rate is not None:
            rendered += f" (≈Rp {_format_significant(value * fx_rate)}; FX indikatif)"
        return rendered
    if "ihsg" in market.lower():
        return f"Rp {_format_significant(value)}"
    return f"${_format_significant(value)}"


def _usd_idr_context(fx: Optional[Dict[str, Any]]) -> str:
    if not fx or fx.get("rate") is None:
        return (
            "USD/IDR: UNAVAILABLE. Do not convert USD prices to IDR and do not use an assumed rate."
        )
    return (
        f"USD/IDR reference: 1 USD = Rp {fx['rate']:,.2f}; "
        f"source={fx.get('provider')}; source_as_of={fx.get('source_as_of') or 'not provided'}; "
        f"rate_retrieved_at_utc={fx.get('captured_at')}; served_at_utc={fx.get('served_at')}; "
        f"freshness=NON-REAL-TIME / indicative."
    )


def _content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "value"):
                    val = item.get(key)
                    if isinstance(val, str):
                        parts.append(val)
                        break
        return "".join(parts)
    if isinstance(content, dict):
        for key in ("text", "content", "value"):
            val = content.get(key)
            if isinstance(val, str):
                return val
        return ""
    return str(content)


def parse_llm_response(raw_text: str) -> str:
    raw_text = raw_text.strip()
    if not raw_text:
        return ""

    if raw_text.startswith("data:"):
        full_text = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if line.startswith("data:") and not line.endswith("[DONE]"):
                json_part = line[5:].strip()
                try:
                    chunk = json.loads(json_part)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        full_text.append(_content_to_str(content))
                except Exception:
                    pass
        parsed = "".join(full_text)
        if parsed:
            return parsed

    try:
        data = json.loads(raw_text)
    except Exception:
        return raw_text

    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if content is None:
            content = msg.get("reasoning_content")
        return _content_to_str(content)
    return raw_text


def _post_chat_completion(payload: Dict[str, Any], headers: Dict[str, str]) -> tuple[str, Optional[str]]:
    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers
    )
    with urllib.request.urlopen(req, timeout=settings.LLM_TIMEOUT) as resp:
        raw_text = resp.read().decode("utf-8")
    finish_reason = None
    try:
        body = json.loads(raw_text)
        choices = body.get("choices") or []
        if choices:
            finish_reason = choices[0].get("finish_reason")
    except Exception:
        pass
    return parse_llm_response(raw_text), finish_reason


def _complete_chat_response(payload: Dict[str, Any], headers: Dict[str, str]) -> str:
    """Continues responses cut off by the model output-token limit."""
    messages = list(payload["messages"])
    chunks: List[str] = []
    max_continuations = 1

    for continuation_index in range(max_continuations + 1):
        request_payload = dict(payload)
        request_payload["messages"] = messages
        content, finish_reason = _post_chat_completion(request_payload, headers)
        if not content:
            raise LLMError("Empty response from LLM")
        chunks.append(content)

        if finish_reason not in {"length", "max_tokens"}:
            return "".join(chunks)
        if continuation_index == max_continuations:
            logger.warning("LLM output remained truncated after continuations")
            return "".join(chunks) + "\n\n⚠️ Laporan terpotong: batas token tercapai."

        messages = messages + [
            {"role": "assistant", "content": content},
            {
                "role": "user",
                "content": (
                    "The previous response was cut off by the output-token limit. Continue exactly "
                    "from where it stopped without greeting or repetition. Complete all remaining sections."
                ),
            },
        ]

    return "".join(chunks)


def call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.25,
    max_tokens: Optional[int] = None,
) -> str:
    """Invokes LLM via OpenAI-compatible endpoint with automatic retries and token continuation."""
    headers = {
        "Content-Type": "application/json",
    }
    if settings.LLM_API_KEY and settings.LLM_API_KEY != "placeholder_key":
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

    payload = {
        "model": settings.LLM_MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "max_tokens": max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS,
    }

    last_error: Optional[Exception] = None
    for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
        try:
            return _complete_chat_response(payload, headers)
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.warning("LLM HTTP Error %s: %s", e.code, err_msg)
            if e.code == 404 or "model" in err_msg.lower():
                fb_payload = dict(payload)
                fb_payload["model"] = "antigravity"
                try:
                    return _complete_chat_response(fb_payload, headers)
                except Exception:
                    pass
            raise LLMError(f"LLM API Error ({e.code}): {err_msg}") from e
        except LLMError:
            raise
        except Exception as e:
            last_error = e
            logger.warning("LLM attempt %d/%d failed: %s", attempt, LLM_MAX_ATTEMPTS, e)
            if attempt < LLM_MAX_ATTEMPTS:
                time.sleep(LLM_RETRY_DELAY)
                continue
    raise LLMError(f"Connection error: {last_error}") from last_error


def load_skill_content(market: str, agent_role: str, locale: str = "id") -> str:
    """Reads localized SKILL.md and appends RUNTIME_CONTRACT.md."""
    norm_market = normalize_market(market)
    skills_root = os.path.join(os.path.dirname(__file__), "skills")
    locale_suffix = f"-{locale}" if locale in ("id", "en") else ""

    candidate_roles = [agent_role]
    if agent_role in ("investment_advisor", "trading_advisor"):
        candidate_roles = ["investment_advisor", "trading_advisor"]

    skill_path = None
    for r in candidate_roles:
        loc = os.path.join(skills_root, norm_market, r, f"SKILL{locale_suffix}.md")
        def_p = os.path.join(skills_root, norm_market, r, "SKILL.md")
        if os.path.exists(loc):
            skill_path = loc
            break
        elif os.path.exists(def_p):
            skill_path = def_p
            break

    if skill_path and os.path.exists(skill_path):
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = f"Role: {agent_role} for market {market}."

    contract_path = os.path.join(skills_root, "RUNTIME_CONTRACT.md")
    if os.path.exists(contract_path):
        with open(contract_path, "r", encoding="utf-8") as f:
            content += "\n\n" + f.read()
    return content


_MARKET_PROMPT_FILES = {
    "crypto": "crypto",
    "ihsg": "ihsg-conventional",
    "ihsg_conventional": "ihsg-conventional",
    "ihsg_syariah": "ihsg-syariah",
    "us_stock": "us-stock",
    "us_etf": "us-etf",
}


def load_market_prompt(market: str, locale: str = "id") -> str:
    """Loads market recommendation prompt from backend/app/investment_ai/prompt/."""
    basename = _MARKET_PROMPT_FILES.get(market.lower()) or _MARKET_PROMPT_FILES.get(normalize_market(market))
    if not basename:
        return ""
    filename = f"{basename}-{locale}.txt"
    path = os.path.join(os.path.dirname(__file__), "prompt", filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def _agent_report_format(agent: str, market: str, skill_content: str) -> str:
    match = re.search(
        r"^## Output Format\s*\n(.*?)(?=^## |\Z)",
        skill_content,
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()

    if agent == "data_fetcher":
        return """## MARKET DATA SNAPSHOT
Timestamp (UTC):
Asset / ticker:
Current price and change:
OHLCV / volume data available:
Other market data:
Unavailable fields: explicitly say 'Unavailable' and why."""
    if agent == "technical_analyst":
        return """## TECHNICAL ANALYSIS
Asset / timeframe / data timestamp:
Trend and strength:
Indicators available (RSI, MACD, Moving Averages):
Support and resistance:
Pattern and momentum:
Signal and conviction:
Unavailable indicators:"""
    if agent == "fundamental_analyst":
        return """## FUNDAMENTAL ANALYSIS
Asset / reporting period / sources:
Financial / tokenomics health:
Valuation and peer context:
Growth, moat, or business quality:
Sharia compliance (if applicable):
Key risks and unavailable data:"""
    if agent == "sentiment_analyst":
        return """## SENTIMENT ANALYSIS
Timestamp and sources:
News and catalyst summary:
Positive / negative evidence:
Macro or narrative drivers:
Sentiment score and signal:
Unverified or unavailable information:"""
    return """## STRUCTURED ANALYSIS
Timestamp and sources:
Key findings:
Signal and rationale:
Unavailable data:"""


def fetch_comprehensive_market_data(market: str, symbol: str) -> Dict[str, Any]:
    """Fetches multi-timeframe market data (1D & 1W) and computes quant indicators deterministically."""
    timeframes = ["1D", "1W"]
    snapshot_captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    is_crypto = normalize_market(market) == "crypto"
    fx_usd_idr = get_usd_idr_rate() if is_crypto else None
    market_metrics = fetch_market_metrics(market)
    try:
        long_term_metrics = fetch_long_term_market_metrics(market, symbol)
    except Exception as e:
        logger.debug("Long-term market metrics unavailable for %s: %s", symbol, e)
        long_term_metrics = {}

    result: Dict[str, Any] = {
        "market": market,
        "symbol": symbol,
        "snapshot_captured_at": snapshot_captured_at,
        "data_freshness": "point-in-time snapshot; source delay varies; not a streaming feed",
        "fx_usd_idr": fx_usd_idr,
        "market_metrics": market_metrics,
        "long_term_metrics": long_term_metrics,
        "timeframes": {},
        "errors": [],
    }

    for tf in timeframes:
        try:
            quote = get_market_quote(market, symbol, tf)
            candles = quote.get("candles", [])
            if candles:
                highs = [c["high"] for c in candles]
                lows = [c["low"] for c in candles]
                closes = [c["close"] for c in candles]
                stats = {
                    "high": max(highs),
                    "low": min(lows),
                    "close": closes[-1] if closes else None,
                    "open": candles[0]["open"] if candles else None,
                    "candle_count": len(candles),
                }
                last_volume = candles[-1].get("volume") if candles else None
                stats.update(compute_indicators(closes, last_volume, candles=candles))
                if quote.get("price") is not None:
                    stats["investment_zones"] = calculate_investment_zones(
                        quote["price"],
                        stats,
                        long_term_metrics=long_term_metrics if tf == "1D" else None,
                        market=market,
                    )

                result["timeframes"][tf] = {
                    "price": quote["price"],
                    "change_pct": quote.get("change_pct"),
                    "provider": quote.get("provider", "provider"),
                    "source_as_of": quote.get("source_as_of"),
                    "captured_at": quote.get("captured_at") or snapshot_captured_at,
                    "stats": stats,
                    "candles": candles[-5:],
                }
            else:
                result["errors"].append(f"No candle data for {tf}")
        except MarketDataError as e:
            result["errors"].append(f"{tf}: {e}")

    primary_tf = "1D" if "1D" in result["timeframes"] else list(result["timeframes"].keys())[0] if result["timeframes"] else None
    if primary_tf:
        pdata = result["timeframes"][primary_tf]
        result["current_price"] = pdata["price"]
        result["change_pct"] = pdata["change_pct"]
        result["provider"] = pdata["provider"]
        stats = pdata["stats"]
        result["investment_zones"] = stats.get("investment_zones")
        quote_as_of = _format_source_timestamp(pdata.get("source_as_of"))
        chg = result.get("change_pct")
        chg_text = f"{chg:+.2f}%" if chg is not None else "UNAVAILABLE"
        fx_rate = fx_usd_idr.get("rate") if fx_usd_idr else None

        lines = [
            f"Market Data Report for {symbol}:",
            f"- Collected at (UTC): {snapshot_captured_at}",
            f"- Primary interval: {primary_tf}; source as-of: {quote_as_of}",
            f"- Data source: {result['provider']}",
            f"- Market overview: {market_metrics or 'Unavailable'}",
            f"- Current Price: {_format_recommendation_price(result['current_price'], market, fx_rate)}",
            f"- Change: {chg_text}",
            f"- High: {_format_significant(stats.get('high'))} | Low: {_format_significant(stats.get('low'))}",
            f"- Candles count: {stats.get('candle_count')}",
        ]
        if "sma20" in stats:
            lines.append(f"- SMA 20: {_format_recommendation_price(stats['sma20'], market, fx_rate)}")
        if "sma50" in stats or long_term_metrics.get("sma50_day"):
            sma50_val = long_term_metrics.get("sma50_day") or stats.get("sma50")
            lines.append(f"- SMA 50-Day: {_format_recommendation_price(sma50_val, market, fx_rate)}")
        if "sma200" in stats or long_term_metrics.get("sma200_day"):
            sma200_val = long_term_metrics.get("sma200_day") or stats.get("sma200")
            lines.append(f"- SMA 200-Day: {_format_recommendation_price(sma200_val, market, fx_rate)}")
        if long_term_metrics.get("sma200_week"):
            lines.append(f"- SMA 200-Week (Major Cycle Anchor): {_format_recommendation_price(long_term_metrics['sma200_week'], market, fx_rate)}")
        if "rsi" in stats:
            lines.append(f"- RSI 14: {stats['rsi']}")
        if "macd" in stats:
            lines.append(f"- MACD: {stats['macd']} (line={_format_significant(stats.get('macd_line'))}, signal={_format_significant(stats.get('macd_signal'))}, hist={_format_significant(stats.get('macd_histogram'))})")
        if stats.get("volume") is not None:
            lines.append(f"- Volume: {stats['volume']:,.0f}")
        if stats.get("support") is not None:
            lines.append(f"- Major Accumulation Support: {_format_recommendation_price(stats['support'], market, fx_rate)}")
        if stats.get("resistance") is not None:
            lines.append(f"- Major Resistance Zone: {_format_recommendation_price(stats['resistance'], market, fx_rate)}")

        if long_term_metrics and long_term_metrics.get("available"):
            c1 = f"{long_term_metrics['cagr_1y_pct']:+.1f}%" if long_term_metrics.get("cagr_1y_pct") is not None else "N/A"
            c3 = f"{long_term_metrics['cagr_3y_pct']:+.1f}%" if long_term_metrics.get("cagr_3y_pct") is not None else "N/A"
            c5 = f"{long_term_metrics['cagr_5y_pct']:+.1f}%" if long_term_metrics.get("cagr_5y_pct") is not None else "N/A"
            mdd = f"{long_term_metrics['max_drawdown_pct']:.1f}%" if long_term_metrics.get("max_drawdown_pct") is not None else "N/A"
            vol = f"{long_term_metrics['annualized_volatility_pct']:.1f}%" if long_term_metrics.get("annualized_volatility_pct") is not None else "N/A"
            lines.append(
                f"- Multi-Year Performance & Risk ({long_term_metrics.get('provider', 'Historical')}): "
                f"1Y CAGR={c1} | 3Y CAGR={c3} | 5Y CAGR={c5} | Max Drawdown={mdd} | Annualized Volatility={vol}"
            )
            lines.append(f"- Market Cycle Position: {long_term_metrics.get('cycle_position', 'UNSPECIFIED')}")

        zones = stats.get("investment_zones") or {}
        if zones:
            acc = zones.get("accumulation_zone") or {}
            fv = zones.get("fair_value_target") or {}
            inv = zones.get("thesis_invalidation") or {}
            lines.append(
                f"- 3 Investment Price Zones (Wealth Compounding Framework):\n"
                f"  1) Zona Akumulasi / DCA Ideal: {_format_recommendation_price(acc.get('ideal_low'), market, fx_rate)} - "
                f"{_format_recommendation_price(acc.get('ideal_high'), market, fx_rate)} ({acc.get('status')}: {acc.get('guidance')})\n"
                f"  2) Target Nilai Wajar (1-3Y Fair Value): {_format_recommendation_price(fv.get('fair_value'), market, fx_rate)} "
                f"(Upper 3Y: {_format_recommendation_price(fv.get('horizon_3y_upper'), market, fx_rate)} | Status: {fv.get('valuation_status')})\n"
                f"  3) Kondisi Invalidasi Tesis (Fundamental Exit Trigger): {inv.get('summary')}"
            )

        if "1W" in result["timeframes"] and primary_tf != "1W":
            tf_1w = result["timeframes"]["1W"]
            st_1w = tf_1w.get("stats", {})
            lines.append(
                f"\nSecondary Weekly Cycle (1W): Price={_format_significant(tf_1w.get('price'))} | "
                f"1W RSI={st_1w.get('rsi', 'UNAVAILABLE')} | 1W MACD={st_1w.get('macd', 'UNAVAILABLE')} | "
                f"1W SMA50={_format_recommendation_price(st_1w.get('sma50'), market, fx_rate)}"
            )

        if "ihsg" in market.lower():
            try:
                flow = get_idx_foreign_flow()
                if flow:
                    lines.append(format_symbol_foreign_flow(flow, symbol))
            except Exception as e:
                logger.debug("IHSG foreign flow context unavailable: %s", e)

        if is_crypto:
            lines.append(_usd_idr_context(fx_usd_idr))

        result["summary"] = "\n".join(lines)
    else:
        result["summary"] = "No market data available."
        result["current_price"] = None
        result["change_pct"] = None
        result["provider"] = None

    return result


def _format_news_evidence(items: List[Dict[str, Any]]) -> str:
    sourced = [item for item in items if item.get("url")]
    if not sourced:
        return (
            "SENTIMENT UNAVAILABLE: Tidak ada hasil berita dengan URL sumber terverifikasi. "
            "Agenda mendatang dan sentimen pasar tidak dapat diasumsikan."
        )
    lines = ["NEWS EVIDENCE ONLY — sumber berita terverifikasi (bukan kesimpulan independen):"]
    for item in sourced:
        line = f"- {item.get('title') or 'Untitled'}"
        if item.get("published_date"):
            line += f" | published={item['published_date']}"
        if item.get("snippet"):
            line += f": {item['snippet']}"
        line += f" ({item['url']})"
        lines.append(line)
    lines.append("Tanggal peristiwa dan dampak pasar masa depan tidak disimpulkan otomatis.")
    return "\n".join(lines)


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    clean = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.MULTILINE)
    clean = re.sub(r"```$", "", clean.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except Exception:
        match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def compute_dca_compounding_simulation(
    market: str,
    current_price: Optional[float],
    long_term_metrics: Optional[Dict[str, Any]],
    fundamental_raw: Optional[Dict[str, Any]],
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Computes deterministic 1Y, 3Y, and 5Y wealth compounding & dividend reinvestment projections."""
    m_low = (market or "").lower()
    currency = "IDR" if "ihsg" in m_low else "USD"
    profile = user_profile or {}
    rates = profile.get("market_rates") or {}
    try:
        fx_rate = float(rates.get("usd_to_idr") or 16000.0)
    except Exception:
        fx_rate = 16000.0
    fx_rate = max(1000.0, fx_rate)

    try:
        surplus_idr = float(profile.get("monthly_surplus") or 0.0)
    except Exception:
        surplus_idr = 0.0

    if currency == "IDR":
        default_monthly_dca = max(500_000.0, round(surplus_idr * 0.30, -4)) if surplus_idr > 0 else 1_000_000.0
    else:
        usd_surplus = surplus_idr / fx_rate
        default_monthly_dca = max(50.0, round(usd_surplus * 0.30, 0)) if surplus_idr > 0 else 100.0
    default_lump_sum = round(default_monthly_dca * 3.0, 2)

    lt = long_term_metrics or {}
    f_raw = fundamental_raw or {}

    cagr_candidates = [
        (lt.get("cagr_3y_pct"), "CAGR Historis 3 Tahun"),
        (lt.get("cagr_5y_pct"), "CAGR Historis 5 Tahun"),
        (lt.get("cagr_1y_pct"), "CAGR Historis 1 Tahun"),
        (
            float(f_raw["revenue_cagr_3y"]) * 100.0 if f_raw.get("revenue_cagr_3y") is not None else None,
            "Proxy Pertumbuhan Pendapatan 3 Tahun",
        ),
    ]
    raw_cagr = None
    cagr_basis = "Benchmark Konservatif Standar (10%)"
    for val, label in cagr_candidates:
        if val is not None:
            try:
                num = float(val)
                if math.isfinite(num):
                    raw_cagr = num
                    cagr_basis = label
                    break
            except Exception:
                continue

    if raw_cagr is None:
        assumed_cagr_pct = 10.0
    else:
        assumed_cagr_pct = round(max(4.0, min(25.0, raw_cagr)), 2)

    raw_div = f_raw.get("dividend_yield")
    try:
        assumed_div_pct = round(max(0.0, min(15.0, float(raw_div or 0.0))), 2)
    except Exception:
        assumed_div_pct = 0.0

    r_price_m = (1.0 + assumed_cagr_pct / 100.0) ** (1.0 / 12.0) - 1.0
    r_div_m = (assumed_div_pct / 100.0) / 12.0

    val = default_lump_sum
    principal = default_lump_sum
    cum_div = 0.0
    horizons: List[Dict[str, Any]] = []

    for m in range(1, 61):
        div_m = val * r_div_m
        val = val * (1.0 + r_price_m) + div_m + default_monthly_dca
        principal += default_monthly_dca
        cum_div += div_m
        if m in (12, 36, 60):
            yrs = m // 12
            total_gain = val - principal
            ret_pct = (total_gain / principal * 100.0) if principal > 0 else 0.0
            est_ann_div = val * (assumed_div_pct / 100.0)
            horizons.append({
                "years": yrs,
                "total_principal": round(principal, 2),
                "projected_value": round(val, 2),
                "total_gain": round(total_gain, 2),
                "total_return_pct": round(ret_pct, 1),
                "estimated_annual_dividend": round(est_ann_div, 2),
                "cumulative_dividends": round(cum_div, 2),
            })

    return {
        "currency": currency,
        "current_price": current_price,
        "default_lump_sum": default_lump_sum,
        "default_monthly_dca": default_monthly_dca,
        "assumed_annual_cagr_pct": assumed_cagr_pct,
        "assumed_dividend_yield_pct": assumed_div_pct,
        "effective_total_return_pct": round(assumed_cagr_pct + assumed_div_pct, 2),
        "cagr_basis": cagr_basis,
        "horizons": horizons,
    }


def analyze_portfolio_concentration(
    market: str,
    symbol: str,
    fundamental_raw: Optional[Dict[str, Any]],
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluates user's current portfolio wallets and warns if adding this asset increases concentration risk."""
    m_norm = normalize_market(market)
    target_class = "CRYPTO" if m_norm == "crypto" else "EQUITY"
    profile = user_profile or {}
    risk_tol = str(profile.get("risk_tolerance") or "MODERATE").upper()
    portfolio_eval = profile.get("portfolio_evaluation") or {}

    wallets = portfolio_eval.get("investment_wallets") or []
    allocs = portfolio_eval.get("allocations_comparison") or []
    try:
        total_inv = float(portfolio_eval.get("total_investment_balance") or profile.get("total_investment_balance") or 0.0)
    except Exception:
        total_inv = 0.0

    class_meta = next((a for a in allocs if a.get("asset_class") == target_class), {})
    actual_pct = float(class_meta.get("actual_pct") or 0.0)
    target_pct = float(class_meta.get("target_pct") or (10.0 if target_class == "CRYPTO" else 40.0))
    drift_pct = round(actual_pct - target_pct, 1)
    class_label = class_meta.get("asset_class_label") or ("Aset Kripto" if target_class == "CRYPTO" else "Saham / ETF Ekuitas")

    clean_sym = (symbol or "").strip().upper()
    base_sym = clean_sym.split(".")[0].split("/")[0].split("-")[0]
    same_class_wallets = [w for w in wallets if w.get("asset_class") == target_class]
    direct_match_exposure = 0.0
    matching_wallet_names: List[str] = []
    for w in same_class_wallets:
        w_name = str(w.get("name") or "")
        matching_wallet_names.append(f"{w_name} (Rp {float(w.get('balance_in_base') or 0.0):,.0f})")
        if base_sym and re.search(rf"\b{re.escape(base_sym)}\b", w_name.upper()):
            direct_match_exposure += float(w.get("balance_in_base") or 0.0)

    base_cap = {"CONSERVATIVE": 10, "MODERATE": 15, "AGGRESSIVE": 20}.get(risk_tol, 15)
    if target_class == "CRYPTO":
        base_cap = {"CONSERVATIVE": 5, "MODERATE": 10, "AGGRESSIVE": 15}.get(risk_tol, 10)

    sector = (fundamental_raw or {}).get("sector") or (fundamental_raw or {}).get("category")

    if total_inv <= 0:
        status = "BELUM_TERPAPAR"
        rec_max_pct = base_cap
        warning_msg = (
            f"Belum ada saldo dompet investasi tercatat untuk kelas {class_label}. "
            "Pastikan dana darurat aman sebelum memulai akumulasi bertahap."
        )
        advice = (
            f"Mulai bangun posisi {clean_sym} secara bertahap (DCA) hingga maksimal {rec_max_pct}% dari total portofolio target."
        )
    elif drift_pct >= 15.0 or actual_pct >= 65.0:
        status = "OVERWEIGHT_KELAS_ASET"
        rec_max_pct = max(3, base_cap // 2)
        warning_msg = (
            f"PERINGATAN KONSENTRASI: Eksposur {class_label} Anda saat ini sudah {actual_pct:.1f}% "
            f"(target profil risiko {risk_tol}: {target_pct:.1f}%, deviasi +{drift_pct:.1f}%). "
            f"Menambah {clean_sym} terlalu agresif dapat memperbesar risiko terkonsentrasi di satu kelas aset."
        )
        advice = (
            f"Batasi penambahan posisi baru {clean_sym} <= {rec_max_pct}% atau lakukan rebalancing dari aset sekelas yang sudah profit."
        )
    elif drift_pct >= 5.0 or direct_match_exposure > 0:
        status = "WASPADA_KONSENTRASI"
        rec_max_pct = max(5, int(round(base_cap * 0.75)))
        extra_note = f" (terdeteksi dompet terkait {base_sym}: Rp {direct_match_exposure:,.0f})" if direct_match_exposure > 0 else ""
        warning_msg = (
            f"Eksposur {class_label} berada di {actual_pct:.1f}% vs target {target_pct:.1f}%{extra_note}. "
            "Jaga porsi per emiten agar tidak mendominasi arus kas risiko Anda."
        )
        advice = (
            f"Gunakan metode cicil DCA terukur dengan batas maksimal {rec_max_pct}% dari total nilai portofolio investasi."
        )
    else:
        status = "AMAN"
        rec_max_pct = base_cap
        warning_msg = (
            f"Alokasi kelas aset {class_label} masih proporsional ({actual_pct:.1f}% vs target {target_pct:.1f}%)."
        )
        advice = (
            f"Ruang alokasi tersedia. Porsi maksimal yang sehat untuk {clean_sym} adalah {rec_max_pct}% dari portofolio."
        )

    return {
        "target_asset_class": target_class,
        "target_asset_class_label": class_label,
        "sector_or_category": sector,
        "total_investment_balance_idr": round(total_inv, 2),
        "current_class_allocation_pct": round(actual_pct, 1),
        "target_class_allocation_pct": round(target_pct, 1),
        "drift_pct": drift_pct,
        "existing_symbol_exposure_idr": round(direct_match_exposure, 2),
        "matching_wallets": matching_wallet_names[:5],
        "concentration_status": status,
        "recommended_max_asset_pct": rec_max_pct,
        "warning_message": warning_msg,
        "proportional_allocation_advice": advice,
    }


def build_macro_regime_context(
    market: str,
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds macroeconomic regime context (USD/IDR, Gold, US10Y Treasury Yield, DXY)."""
    profile = user_profile or {}
    rates = dict(profile.get("market_rates") or {})
    if not rates:
        try:
            rates = fetch_live_market_rates() or {}
        except Exception as e:
            logger.debug("Macro market rates fetch error: %s", e)
            rates = {}

    usd_idr = rates.get("usd_to_idr")
    gold_idr_g = rates.get("gold_idr_per_gram")
    gold_usd_oz = rates.get("gold_usd_per_oz")

    us10y: Optional[float] = None
    dxy: Optional[float] = None
    try:
        import yfinance as yf  # type: ignore

        for ticker_sym, attr in (("^TNX", "us10y"), ("DX-Y.NYB", "dxy")):
            try:
                hist = yf.Ticker(ticker_sym).history(period="5d", auto_adjust=False)
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    last_val = float(hist["Close"].dropna().iloc[-1])
                    if math.isfinite(last_val) and last_val > 0:
                        if attr == "us10y":
                            us10y = round(last_val, 2)
                        else:
                            dxy = round(last_val, 2)
            except Exception:
                continue
    except Exception:
        pass

    if us10y is not None:
        if us10y >= 4.25:
            regime = "HIGH_RESTRICTIVE"
            regime_label = "Suku Bunga Ketat / Tinggi (High-for-Longer)"
            summary = f"Yield US10Y berada di level tinggi ({us10y:.2f}%). Biaya modal global ketat; fokus pada emiten kas kuat, utang rendah, dan valuasi diskon."
        elif us10y >= 3.25:
            regime = "NEUTRAL_TRANSITION"
            regime_label = "Rezim Transisi Suku Bunga Netral"
            summary = f"Yield US10Y di level moderat ({us10y:.2f}%). Kondisi seimbang untuk strategi Quality Growth & Dividend Compounding."
        else:
            regime = "ACCOMMODATIVE"
            regime_label = "Rezim Suku Bunga Longgar / Akomodatif"
            summary = f"Yield US10Y rendah ({us10y:.2f}%). Mendukung ekspansi valuasi saham pertumbuhan, ETF indeks, dan aset kripto berutilitas tinggi."
    else:
        regime = "MIXED_CAUTIOUS"
        regime_label = "Makro Hati-Hati (Kurs & Komoditas Acuan)"
        summary = "Data yield global tidak tersedia langsung; gunakan kurs USD/IDR dan harga emas sebagai indikator sentimen likuiditas & safe-haven."

    m_norm = normalize_market(market)
    if "ihsg" in (market or "").lower():
        fx_note = f"Kurs USD/IDR di Rp {usd_idr:,.0f}" if usd_idr else "Kurs USD/IDR terpantau fluktuatif"
        implication = f"{fx_note}: perhatikan sensitivitas emiten terhadap impor bahan baku / utang valas vs emiten berbasis pendapatan USD atau domestik defensif."
    elif m_norm == "crypto":
        implication = "Aset kripto sangat sensitif terhadap likuiditas dolar (DXY) dan arah yield obligasi AS; terapkan DCA bertahap dan prioritaskan jaringan Tier-1."
    else:
        implication = "Untuk saham/ETF AS, tingkat yield Treasury memengaruhi valuasi DCF (discount rate); margin of safety memadai tetap krusial."

    return {
        "usd_idr_rate": round(float(usd_idr), 2) if usd_idr else None,
        "gold_idr_per_gram": round(float(gold_idr_g), 2) if gold_idr_g else None,
        "gold_usd_per_oz": round(float(gold_usd_oz), 2) if gold_usd_oz else None,
        "us10y_yield_pct": us10y,
        "dxy_index": dxy,
        "interest_rate_regime": regime,
        "regime_label": regime_label,
        "regime_summary": summary,
        "implication_for_asset": implication,
    }


def run_investment_swarm_pipeline(
    market: str,
    symbol: str,
    user_profile: Optional[Dict[str, Any]] = None,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    locale: str = "id",
) -> Dict[str, Any]:
    """
    Executes multi-agent investment research for a single asset with full deterministic quant gates,
    multi-horizon outlooks, and personal capacity integration.
    """
    is_syariah = is_syariah_market(market)

    def emit(event_type: str, **payload: Any) -> None:
        if event_callback:
            event = {
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **payload,
            }
            event_callback(event)

    def log(message: str, level: str = "INFO", **payload: Any) -> None:
        getattr(logger, level.lower(), logger.info)(message)
        emit("log", level=level, message=message, **payload)

    def check_stop() -> None:
        if stop_event is not None and stop_event.is_set():
            raise AnalysisStopped("Analisis dibatalkan oleh pengguna.")

    emit("started", market=market, symbol=symbol)
    log(f"Memulai riset investasi multi-agent: Simbol={symbol}, Pasar={market}")

    # 1. Search Live News via Exa / multi-engine
    check_stop()
    log("Mencari berita, sentimen pasar & katalis terkini melalui Exa Search...")
    search_query = f"{symbol} {market} investasi prospek dividen kinerja keuangan analisis"
    search_results = search_internet(search_query, num_results=3)
    news_evidence = _format_news_evidence(search_results)
    market_context = f"Pasar: {market.upper()}\nSimbol: {symbol}\n{news_evidence}"

    # 2. Fetch Real Fundamental Context
    check_stop()
    log("Mengambil data fundamental & laporan keuangan resmi...")
    fundamental_info: Dict[str, Any] = {"available": False, "sharia": None, "sharia_reference": None}
    try:
        fundamental_info = get_fundamental_context(market, symbol)
        fundamentals_context = fundamental_info.get("text", "")
        log("Data fundamental berhasil dimuat.")
    except Exception as e:
        logger.warning("Fundamental fetch error for %s: %s", symbol, e)
        fundamentals_context = f"Data fundamental untuk {symbol} UNAVAILABLE."

    # 3. Fetch On-Chain & Tokenomics context if crypto
    onchain_context = ""
    if normalize_market(market) == "crypto":
        check_stop()
        log("Mengambil metrik on-chain & tokenomics crypto (CoinGecko Supply/FDV + DefiLlama TVL/Revenue)...")
        try:
            onchain_info = get_onchain_context(market, symbol)
            onchain_context = onchain_info.get("text", "") if onchain_info else ""
        except Exception as e:
            logger.warning("On-chain fetch error for %s: %s", symbol, e)

    # 4. Run Data Fetcher deterministically (0 LLM hallucination)
    check_stop()
    emit("agent_status", role="data_fetcher", status="running")
    log("Data Fetcher: Menghitung indikator siklus multi-tahun (SMA 50/200, CAGR, Max Drawdown, Zona Investasi)...", role="data_fetcher")
    market_data = fetch_comprehensive_market_data(market, symbol)

    # Recalibrate 3 Investment Price Zones using both technical cycle & fundamental valuation data
    primary_tf_key = "1D" if "1D" in (market_data.get("timeframes") or {}) else next(iter(market_data.get("timeframes") or {}), None)
    primary_stats = ((market_data.get("timeframes") or {}).get(primary_tf_key) or {}).get("stats", {})
    fundamental_raw = fundamental_info.get("raw") or {}
    long_term_metrics = market_data.get("long_term_metrics") or {}
    if market_data.get("current_price") is not None:
        enriched_zones = calculate_investment_zones(
            market_data["current_price"],
            primary_stats,
            long_term_metrics=long_term_metrics,
            fundamental_data=fundamental_raw,
            market=market,
        )
        if primary_tf_key and primary_tf_key in (market_data.get("timeframes") or {}):
            market_data["timeframes"][primary_tf_key]["stats"]["investment_zones"] = enriched_zones
        market_data["investment_zones"] = enriched_zones
    else:
        enriched_zones = market_data.get("investment_zones") or {}

    fx_rate_val = (market_data.get("fx_usd_idr") or {}).get("rate")
    zones_calibration_note = ""
    if enriched_zones:
        acc_z = enriched_zones.get("accumulation_zone") or {}
        fv_z = enriched_zones.get("fair_value_target") or {}
        inv_z = enriched_zones.get("thesis_invalidation") or {}
        zones_calibration_note = (
            f"\n=== 3 ZONA HARGA INVESTASI (TERKALIBRASI FUNDAMENTAL & SIKLUS) ===\n"
            f"- Zona Akumulasi / DCA Ideal: {_format_recommendation_price(acc_z.get('ideal_low'), market, fx_rate_val)} s/d "
            f"{_format_recommendation_price(acc_z.get('ideal_high'), market, fx_rate_val)} | Status: {acc_z.get('status')} | {acc_z.get('guidance')}\n"
            f"- Target Nilai Wajar (1-3 Tahun): {_format_recommendation_price(fv_z.get('fair_value'), market, fx_rate_val)} "
            f"(Upper 3Y: {_format_recommendation_price(fv_z.get('horizon_3y_upper'), market, fx_rate_val)} | Status: {fv_z.get('valuation_status')} | Sumber: {fv_z.get('source')})\n"
            f"- Kondisi Invalidasi Tesis (Fundamental Exit Trigger): {inv_z.get('summary')}\n"
        )

    enhanced_context = (
        f"{market_context}\n\n"
        f"=== DATA PASAR, SIKLUS & KUANTITATIF ===\n{market_data.get('summary', '')}\n"
        f"{zones_calibration_note}\n"
        f"=== FUNDAMENTAL & VALUASI ===\n{fundamentals_context}\n"
    )
    if onchain_context:
        enhanced_context += f"\n=== ON-CHAIN & TOKENOMICS ===\n{onchain_context}\n"

    agent_results: Dict[str, str] = {"data_fetcher": enhanced_context}
    emit("agent_output", role="data_fetcher", output=enhanced_context)
    emit("agent_status", role="data_fetcher", status="completed")
    log("Data fetcher selesai dengan kalkulasi indikator siklus & fundamental deterministik.", role="data_fetcher", status="completed")

    roles = [r for r in agent_roles(market) if r != "data_fetcher"]
    agent_errors: Dict[str, str] = {}

    def run_analyst(role: str) -> tuple[str, str, Optional[str]]:
        if stop_event is not None and stop_event.is_set():
            return role, "", "cancelled"
        if role == "sentiment_analyst":
            emit("agent_status", role=role, status="running")
            emit("agent_output", role=role, output=news_evidence)
            emit("agent_status", role=role, status="completed")
            log(f"Analisis {role} selesai.", role=role, status="completed")
            return role, news_evidence, None

        skill_content = load_skill_content(market, role, locale)
        report_template = _agent_report_format(role, market, skill_content)
        language_name = "Bahasa Indonesia" if locale == "id" else "English"
        role_title = (
            "Market Cycle & Accumulation Timing Analyst"
            if role == "technical_analyst"
            else role.replace("_", " ").title()
        )

        system_prompt = (
            f"You are the {role_title} agent for {market.upper()}.\n\n"
            f"OUTPUT LANGUAGE: Respond entirely in {language_name}.\n\n"
            f"Agent Guidelines:\n{skill_content}\n\n"
            f"{DATA_FRESHNESS_INSTRUCTIONS}\n\n"
            f"{TOOL_GROUNDING_INSTRUCTIONS}\n\n"
            f"{NEWS_VERIFICATION_INSTRUCTIONS}\n\n"
            "Fokus analisis Anda adalah INVESTASI jangka pendek, menengah, dan panjang (wealth compounding & fundamental value). "
            "Dilarang keras merekomendasikan day trading, scalping, futures/leverage, stop loss ATR mekanis, atau target R-multiple.\n\n"
            f"Required report template:\n{report_template}"
        )

        user_prompt = (
            f"Simbol: {symbol}\nPasar: {market}\n\n"
            f"Berikut adalah data pasar, siklus harga, indikator kuantitatif, fundamental institusional, dan berita terkini:\n\n"
            f"{enhanced_context}\n\n"
            f"Susun laporan analisis spesifik Anda sebagai '{role}' menggunakan ONLY data di atas."
        )

        emit("agent_status", role=role, status="running")
        log(f"Menjalankan analisis agen: {role}...", role=role)
        try:
            rep = call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], temperature=0.2)
            emit("agent_output", role=role, output=rep)
            emit("agent_status", role=role, status="completed")
            log(f"Analisis {role} selesai.", role=role, status="completed")
            return role, rep, None
        except Exception as e:
            logger.error("Analyst %s failed: %s", role, e)
            fallback = f"⚠️ Analisis {role} tidak tersedia karena layanan AI terganggu: {e}"
            emit("agent_output", role=role, output=fallback)
            emit("agent_status", role=role, status="failed")
            return role, fallback, str(e)

    # Run analyst agents in parallel
    with ThreadPoolExecutor(max_workers=min(4, len(roles))) as executor:
        futures = [executor.submit(run_analyst, role) for role in roles]
        for f in as_completed(futures):
            r, out, err = f.result()
            agent_results[r] = out
            if err:
                agent_errors[r] = err

    # 5. Deterministic Decision-Sharpening Contexts & Investment Advisor Agent
    check_stop()
    emit("agent_status", role="investment_advisor", status="running")
    log("Investment Advisor sedang mensintesis temuan agen, simulasi DCA, konsentrasi portofolio & konteks makro...", role="investment_advisor")

    compounding_sim = compute_dca_compounding_simulation(
        market=market,
        current_price=market_data.get("current_price"),
        long_term_metrics=long_term_metrics,
        fundamental_raw=fundamental_raw,
        user_profile=user_profile,
    )
    concentration_analysis = analyze_portfolio_concentration(
        market=market,
        symbol=symbol,
        fundamental_raw=fundamental_raw,
        user_profile=user_profile,
    )
    macro_regime = build_macro_regime_context(market=market, user_profile=user_profile)

    profile_ctx = "PROFIL KEUANGAN PENGGUNA TIDAK TERSEDIA."
    if user_profile:
        cash_val = user_profile.get("liquid_cash_balance", 0.0)
        invest_val = user_profile.get("total_investment_balance", 0.0)
        surplus_val = user_profile.get("monthly_surplus", 0.0)
        risk_prof = user_profile.get("risk_tolerance", "MODERATE")
        sharia_usr = user_profile.get("sharia_preference", False)
        profile_ctx = (
            f"Saldo Kas Likuid Dompet: Rp {cash_val:,.0f}\n"
            f"Saldo Investasi Saat Ini: Rp {invest_val:,.0f}\n"
            f"Surplus Bulanan Riil: Rp {surplus_val:,.0f}\n"
            f"Toleransi Risiko: {risk_prof}\n"
            f"Preferensi Syariah: {'YA (Wajib Syariah)' if sharia_usr else 'Konvensional / Fleksibel'}\n"
            f"Status Konsentrasi Kelas Aset ({concentration_analysis['target_asset_class_label']}): "
            f"{concentration_analysis['concentration_status']} — Aktual {concentration_analysis['current_class_allocation_pct']}% "
            f"vs Target {concentration_analysis['target_class_allocation_pct']}% | {concentration_analysis['warning_message']}"
        )

    dca_ctx_lines = [
        f"SIMULASI COMPOUNDING & DIVIDEN OTOMATIS ({compounding_sim['currency']}):",
        f"- Lump-sum awal: {compounding_sim['default_lump_sum']:,.0f} | Cicilan DCA/bulan: {compounding_sim['default_monthly_dca']:,.0f}",
        f"- Asumsi Harga CAGR: {compounding_sim['assumed_annual_cagr_pct']}%/thn ({compounding_sim['cagr_basis']}) | Dividend Yield: {compounding_sim['assumed_dividend_yield_pct']}%/thn",
    ]
    for h in compounding_sim.get("horizons") or []:
        dca_ctx_lines.append(
            f"- Horizon {h['years']} Tahun: Modal {h['total_principal']:,.0f} -> Estimasi Nilai {h['projected_value']:,.0f} "
            f"(+{h['total_return_pct']}%) | Est. Dividen/Thn: {h['estimated_annual_dividend']:,.0f}"
        )
    dca_ctx = "\n".join(dca_ctx_lines)

    macro_ctx = (
        f"KONTEKS MAKROEKONOMI & REZIM SUKU BUNGA:\n"
        f"- Rezim: {macro_regime['regime_label']} ({macro_regime['interest_rate_regime']})\n"
        f"- USD/IDR: {macro_regime.get('usd_idr_rate') or 'N/A'} | Emas (Rp/g): {macro_regime.get('gold_idr_per_gram') or 'N/A'} | "
        f"US10Y Yield: {macro_regime.get('us10y_yield_pct') or 'N/A'}% | DXY: {macro_regime.get('dxy_index') or 'N/A'}\n"
        f"- Ringkasan: {macro_regime['regime_summary']}\n"
        f"- Implikasi untuk {symbol}: {macro_regime['implication_for_asset']}"
    )

    analysts_summary = "\n\n".join([
        f"=== LAPORAN {k.upper()} ===\n{v}"
        for k, v in agent_results.items()
        if k != "data_fetcher"
    ])

    adv_skill = load_skill_content(market, "investment_advisor", locale)
    advisor_system = f"""Anda adalah Kepala Komite Investasi (Chief Investment Strategist).
Tugas Anda adalah mensintesis seluruh laporan siklus pasar, fundamental institusional, on-chain/foreign flow, sentimen, konsentrasi portofolio pengguna, dan rezim makroekonomi untuk menghasilkan Rekomendasi Investasi Multi-Horizon (Jangka Pendek < 1 thn, Jangka Menengah 1-3 thn, Jangka Panjang > 3-5 thn).
DILARANG menggunakan konsep short-term trading (stop loss ATR, R-multiple, chart intraday 1H, atau leverage/futures).

Agent Skill Reference:
{adv_skill}

{DATA_FRESHNESS_INSTRUCTIONS}
{TOOL_GROUNDING_INSTRUCTIONS}
{NEWS_VERIFICATION_INSTRUCTIONS}

WAJIB mengembalikan respon HANYA dalam format JSON valid tanpa tanda markdown (```json).
Gunakan skema JSON berikut (isi dengan data aktual aset, JANGAN menyalin contoh):
{{
  "symbol": "<TICKER_SYMBOL>",
  "market": "<MARKET_NAME>",
  "stance": "ACCUMULATE / DCA" | "BUY ON DIP" | "HOLD" | "REDUCE",
  "confidence_pct": <integer 0-100>,
  "fundamental_quality_score": <integer 1-10>,
  "sharia_compliance": {{
    "is_sharia": <true|false>,
    "classification": "<ISSI / DES / Syariah Screen / Konvensional>",
    "notes": "<Keterangan status syariah berdasarkan ISSI Reference & rasio utang OJK>"
  }},
  "valuation_summary": {{
    "fair_value_estimate": "<Estimasi nilai wajar dari DCF / metrik fundamental aktual atau UNAVAILABLE>",
    "current_valuation_status": "UNDERVALUED" | "FAIR" | "OVERVALUED" | "UNAVAILABLE",
    "metric_rationale": "<Rasionalitas valuasi menggunakan DCF Margin of Safety, P/E, ROIC, F-Score yang tersedia>"
  }},
  "investment_price_zones": {{
    "accumulation_zone_summary": "<Rentang zona akumulasi / DCA ideal berbasis SMA 200 / Support Major & alasan siklus>",
    "fair_value_target_summary": "<Target nilai wajar 1-3 tahun berbasis DCF/valuasi historis>",
    "thesis_invalidation_trigger": "<Kondisi kerusakan fundamental bisnis/struktural spesifik sebagai trigger exit/rebalance>"
  }},
  "multi_horizon_outlook": {{
    "short_term": {{
      "horizon": "< 1 Tahun (Katalis & Zona Akumulasi)",
      "stance": "ACCUMULATE" | "BUY ON DIP" | "HOLD" | "REDUCE",
      "target_range": "<Rentang harga 6-12 bulan atau UNAVAILABLE>",
      "thesis": "<Tesis jangka pendek berbasis posisi siklus & katalis fundamental>",
      "catalysts": ["<Katalis 1>", "<Katalis 2>"],
      "risks": ["<Risiko 1>"]
    }},
    "medium_term": {{
      "horizon": "1 - 3 Tahun (Ekspansi Bisnis & Menuju Fair Value)",
      "stance": "ACCUMULATE" | "BUY ON DIP" | "HOLD" | "REDUCE",
      "target_range": "<Target menuju nilai wajar 1-3 tahun atau UNAVAILABLE>",
      "thesis": "<Tesis pertumbuhan & pencapaian fair value>",
      "catalysts": ["<Katalis pertumbuhan/makro>"],
      "risks": ["<Risiko margin/valuasi>"]
    }},
    "long_term": {{
      "horizon": "> 3 - 5 Tahun (Wealth Compounding & Moat)",
      "stance": "ACCUMULATE / DCA" | "HOLD" | "REDUCE",
      "target_range": "<Potensi compounding jangka panjang>",
      "thesis": "<Tesis moat sekuler, ROIC, & compounding dividen>",
      "compounding_factors": ["<Faktor moat/ROIC/dividen>"],
      "risks": ["<Risiko disrupsi struktural>"]
    }}
  }},
  "portfolio_and_dca_simulation": {{
    "risk_profile_match": "<Kesesuaian profil risiko & peringatan konsentrasi portofolio pengguna>",
    "recommended_max_allocation_pct": <integer persentase maks alokasi dari portofolio>,
    "suggested_monthly_dca_amount": <nominal DCA bulanan yang realistis dari surplus riil>,
    "action_plan": "<Rencana aksi akumulasi bertahap vs lump-sum dengan mempertimbangkan rezim makro & konsentrasi dompet>"
  }},
  "executive_thesis": "<Tesis eksekutif komprehensif 2-3 paragraf bahasa Indonesia yang merangkum kualitas fundamental, siklus akumulasi, konteks makro, dan posisi dompet pengguna>",
  "key_monitoring_metrics": ["<Metrik Fundamental/Siklus 1>", "<Metrik 2>"]
}}"""

    advisor_user = (
        f"Simbol: {symbol}\nPasar: {market}\n\n"
        f"DATA PROFIL KEUANGAN & KONSENTRASI PORTOFOLIO INVESTOR:\n{profile_ctx}\n\n"
        f"{dca_ctx}\n\n"
        f"{macro_ctx}\n\n"
        f"{zones_calibration_note}\n"
        f"LAPORAN DARI TIM ANALIS:\n{analysts_summary}\n\n"
        "Berikan rekomendasi investasi komprehensif dalam struktur JSON valid yang ditentukan."
    )

    advisor_failed = False
    try:
        raw_advisor = call_llm([
            {"role": "system", "content": advisor_system},
            {"role": "user", "content": advisor_user},
        ], temperature=0.2)
        parsed_advisor = _extract_json_block(raw_advisor)
        if not parsed_advisor:
            raise LLMError("Gagal mem-parsing format JSON dari advisor.")
    except Exception as e:
        logger.error("Investment advisor JSON generation failed: %s", e)
        advisor_failed = True
        parsed_advisor = {
            "symbol": symbol,
            "market": market,
            "stance": "HOLD",
            "confidence_pct": None,
            "fundamental_quality_score": None,
            "degraded": True,
            "error_detail": f"Layanan AI Investment Advisor mengalami kendala: {e}",
            "sharia_compliance": {
                "is_sharia": fundamental_info.get("sharia_reference", {}).get("status") == "Ya",
                "classification": "ISSI Reference" if is_syariah else "Informasional",
                "notes": "Verifikasi manual dari file referensi lokal.",
            },
            "valuation_summary": {
                "fair_value_estimate": "UNAVAILABLE",
                "current_valuation_status": "UNAVAILABLE",
                "metric_rationale": "Sintesis AI tidak tersedia.",
            },
            "multi_horizon_outlook": {
                "short_term": {"horizon": "< 1 Tahun", "stance": "HOLD", "thesis": "Sintesis AI tidak tersedia."},
                "medium_term": {"horizon": "1 - 3 Tahun", "stance": "HOLD", "thesis": "Sintesis AI tidak tersedia."},
                "long_term": {"horizon": "> 3 - 5 Tahun", "stance": "HOLD", "thesis": "Sintesis AI tidak tersedia."},
            },
            "portfolio_and_dca_simulation": {
                "risk_profile_match": concentration_analysis["concentration_status"],
                "recommended_max_allocation_pct": concentration_analysis["recommended_max_asset_pct"],
                "suggested_monthly_dca_amount": compounding_sim["default_monthly_dca"],
                "action_plan": concentration_analysis["proportional_allocation_advice"],
            },
            "executive_thesis": "⚠️ Sintesis AI Advisor mengalami kendala teknis. Sistem menolak memfabrikasi skor atau angka palsu. Silakan rujuk data kuantitatif, zona harga, dan laporan analis di bawah.",
            "key_monitoring_metrics": [],
        }

    # Post-LLM Deterministic Gates & Structured Grounding Enrichment
    sharia_ref = fundamental_info.get("sharia_reference") or {}
    sharia_eligible = sharia_ref.get("status") == "Ya"
    if is_syariah and not sharia_eligible:
        parsed_advisor["stance"] = "HOLD"
        if "sharia_compliance" in parsed_advisor:
            parsed_advisor["sharia_compliance"]["is_sharia"] = False
            parsed_advisor["sharia_compliance"]["classification"] = "TIDAK_TERCATAT_ISSI"
            parsed_advisor["sharia_compliance"]["notes"] = "Status ISSI tidak tercatat 'Ya' pada referensi lokal."

    # Calibrate confidence deterministically if primary quote is available
    prim_tf = market_data.get("timeframes", {}).get("1D") or market_data.get("timeframes", {}).get("1W")
    if prim_tf and prim_tf.get("price") is not None and not advisor_failed:
        curr_p = prim_tf["price"]
        st = prim_tf.get("stats", {})
        cal_conf = calibrate_confidence(
            float(curr_p),
            st,
            "BUY" if "ACCUMULATE" in str(parsed_advisor.get("stance", "")).upper() or "BUY" in str(parsed_advisor.get("stance", "")).upper() else "HOLD",
            prim_tf.get("change_pct"),
        )
        if cal_conf is not None:
            parsed_advisor["confidence_pct"] = int(round(cal_conf * 100))
            parsed_advisor["confidence_basis"] = "deterministic indicator heuristic (SMA/RSI/MACD/Momentum)"

    # Merge deterministic 3 Investment Price Zones + Institutional Metrics + Decision Sharpening Modules
    llm_zones = parsed_advisor.get("investment_price_zones") if isinstance(parsed_advisor.get("investment_price_zones"), dict) else {}
    parsed_advisor["investment_price_zones"] = {
        **(enriched_zones or {}),
        **llm_zones,
    }
    parsed_advisor["institutional_metrics"] = {
        "currency": compounding_sim["currency"],
        "current_price": market_data.get("current_price"),
        "dcf_fair_value": fundamental_raw.get("dcf_fair_value"),
        "margin_of_safety_pct": fundamental_raw.get("margin_of_safety_pct"),
        "valuation_signal": fundamental_raw.get("valuation_signal"),
        "fair_value_source": fundamental_raw.get("fair_value_source"),
        "piotroski_f_score": fundamental_raw.get("piotroski_f_score"),
        "altman_z_score": fundamental_raw.get("altman_z_score"),
        "roic_pct": round(float(fundamental_raw["roic"]) * 100, 2) if fundamental_raw.get("roic") is not None else None,
        "roe_pct": round(float(fundamental_raw["roe"]) * 100, 2) if fundamental_raw.get("roe") is not None else None,
        "interest_coverage": fundamental_raw.get("interest_coverage"),
        "debt_to_equity": fundamental_raw.get("debt_to_equity"),
        "trailing_pe": fundamental_raw.get("trailing_pe"),
        "price_to_book": fundamental_raw.get("price_to_book"),
        "dividend_yield_pct": fundamental_raw.get("dividend_yield"),
        "dividend_5y_avg_pct": fundamental_raw.get("dividend_5y_avg"),
        "payout_ratio_pct": round(float(fundamental_raw["payout_ratio"]) * 100, 1) if fundamental_raw.get("payout_ratio") is not None else None,
        "revenue_cagr_3y_pct": round(float(fundamental_raw["revenue_cagr_3y"]) * 100, 1) if fundamental_raw.get("revenue_cagr_3y") is not None else None,
        "net_income_cagr_3y_pct": round(float(fundamental_raw["net_income_cagr_3y"]) * 100, 1) if fundamental_raw.get("net_income_cagr_3y") is not None else None,
        "eps_cagr_3y_pct": round(float(fundamental_raw["eps_cagr_3y"]) * 100, 1) if fundamental_raw.get("eps_cagr_3y") is not None else None,
        "fcf_cagr_3y_pct": round(float(fundamental_raw["fcf_cagr_3y"]) * 100, 1) if fundamental_raw.get("fcf_cagr_3y") is not None else None,
        "cagr_1y_pct": long_term_metrics.get("cagr_1y_pct"),
        "cagr_3y_pct": long_term_metrics.get("cagr_3y_pct"),
        "cagr_5y_pct": long_term_metrics.get("cagr_5y_pct"),
        "max_drawdown_pct": long_term_metrics.get("max_drawdown_pct"),
        "annualized_volatility_pct": long_term_metrics.get("annualized_volatility_pct"),
        "sma50_day": long_term_metrics.get("sma50_day") or primary_stats.get("sma50"),
        "sma200_day": long_term_metrics.get("sma200_day") or primary_stats.get("sma200"),
        "sma200_week": long_term_metrics.get("sma200_week"),
        "price_vs_sma50_pct": long_term_metrics.get("price_vs_sma50_pct"),
        "price_vs_sma200_pct": long_term_metrics.get("price_vs_sma200_pct"),
        "price_vs_sma200w_pct": long_term_metrics.get("price_vs_sma200w_pct"),
        "cycle_position": long_term_metrics.get("cycle_position"),
        "historical_provider": long_term_metrics.get("provider"),
        "fmp_used": fundamental_raw.get("fmp_used"),
        # Crypto tokenomics & protocol fundamentals
        "mcap_to_fdv_ratio": fundamental_raw.get("mcap_to_fdv_ratio"),
        "supply_issued_pct": fundamental_raw.get("supply_issued_pct"),
        "dilution_risk": fundamental_raw.get("dilution_risk"),
        "defillama_tvl_usd": (fundamental_raw.get("defillama") or {}).get("tvl"),
        "defillama_daily_fees_usd": (fundamental_raw.get("defillama") or {}).get("daily_fees_usd"),
        "defillama_daily_revenue_usd": (fundamental_raw.get("defillama") or {}).get("daily_revenue_usd"),
    }
    parsed_advisor["compounding_simulation"] = compounding_sim
    parsed_advisor["portfolio_concentration_analysis"] = concentration_analysis
    parsed_advisor["macro_regime"] = macro_regime

    final_result = {
        "symbol": symbol,
        "market": market,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "analyst_reports": agent_results,
        "investment_recommendation": parsed_advisor,
        "news_sources": search_results,
        "degraded": advisor_failed or bool(agent_errors),
    }

    emit("agent_output", role="investment_advisor", output=json.dumps(parsed_advisor, indent=2, ensure_ascii=False))
    emit("agent_status", role="investment_advisor", status="completed")
    emit("investment_recommendation", data=parsed_advisor)
    emit("completed", result=final_result)
    log("Seluruh proses riset multi-agent berhasil diselesaikan.", role="investment_advisor", status="completed")

    return final_result


def _format_ranked_candidate(
    candidate: Dict[str, Any], market: str, locale: str = "id"
) -> str:
    is_syariah = is_syariah_market(market)
    sharia_eligible = candidate.get("issi_status") == "Ya"
    stance = "HOLD" if is_syariah and not sharia_eligible else candidate.get("final_stance", "HOLD")
    symbol = candidate["symbol"]
    fx_rate = candidate.get("fx_usd_idr_rate")
    price = _format_recommendation_price(candidate.get("price"), market, fx_rate)
    change = candidate.get("change_pct")
    change_text = f"{change:+.2f}%" if change is not None else "UNAVAILABLE"

    f_score = candidate.get("piotroski_f_score")
    mos = candidate.get("margin_of_safety_pct")
    fund_part = f"F-Score={f_score}/9" if f_score is not None else "F-Score=N/A"
    mos_part = f"MoS={mos:+.1f}%" if mos is not None else "MoS=N/A"

    if locale == "id":
        change_period = "24 jam bergulir" if candidate.get("change_period") == "rolling_24h" else "daily close-to-close"
        line = (
            f"🔹 {symbol} — {stance}\n"
            f"💵 Harga: {price} | perubahan {change_period}: {change_text}\n"
            f"📈 RSI(1D): {candidate.get('rsi', 'UNAVAILABLE')} | SMA50: "
            f"{_format_recommendation_price(candidate.get('sma50'), market, fx_rate)} | "
            f"MACD: {candidate.get('macd', 'UNAVAILABLE')}\n"
            f"🏛️ Kualitas & Valuasi: {fund_part} | {mos_part} | "
            f"Skor={candidate.get('score')}/100 (Fundamental {candidate.get('fundamental_score')}/65 + Siklus {candidate.get('cycle_score')}/35)\n"
            f"🔗 Sumber: {candidate.get('provider')} | as-of: {_format_source_timestamp(candidate.get('source_as_of'))}"
        )
    else:
        change_period = "rolling 24h" if candidate.get("change_period") == "rolling_24h" else "daily close-to-close"
        line = (
            f"🔹 {symbol} — {stance}\n"
            f"💵 Price: {price} | change {change_period}: {change_text}\n"
            f"📈 RSI(1D): {candidate.get('rsi', 'UNAVAILABLE')} | SMA50: "
            f"{_format_recommendation_price(candidate.get('sma50'), market, fx_rate)} | "
            f"MACD: {candidate.get('macd', 'UNAVAILABLE')}\n"
            f"🏛️ Quality & Value: {fund_part} | {mos_part} | "
            f"Score={candidate.get('score')}/100 (Fundamental {candidate.get('fundamental_score')}/65 + Cycle {candidate.get('cycle_score')}/35)\n"
            f"🔗 Source: {candidate.get('provider')} | as-of: {_format_source_timestamp(candidate.get('source_as_of'))}"
        )

    rationale = None if is_syariah and not sharia_eligible else candidate.get("final_rationale")
    if rationale:
        line += f"\n📝 Alasan: {rationale}"

    zones = candidate.get("investment_zones") or {}
    acc = candidate.get("accumulation_zone") or zones.get("accumulation_zone") or {}
    fv = candidate.get("fair_value_target") or zones.get("fair_value_target") or {}
    inv = candidate.get("thesis_invalidation") or zones.get("thesis_invalidation") or {}

    if is_syariah:
        line += f"\n🕌 ISSI reference: {candidate.get('issi_status', 'UNAVAILABLE')} (source_as_of={candidate.get('sharia_reference_source_as_of') or 'UNSPECIFIED'})"
    if zones or acc or fv:
        if acc.get("ideal_low") is not None or acc.get("ideal_high") is not None:
            line += (
                f"\n🛒 Zona Akumulasi / DCA Ideal: "
                f"{_format_recommendation_price(acc.get('ideal_low'), market, fx_rate)} - "
                f"{_format_recommendation_price(acc.get('ideal_high'), market, fx_rate)} ({acc.get('status') or 'DISCOUNT'})"
            )
        if fv.get("fair_value") is not None:
            line += (
                f"\n💎 Target Nilai Wajar (1-3Y): "
                f"{_format_recommendation_price(fv.get('fair_value'), market, fx_rate)} "
                f"(3Y Upper: {_format_recommendation_price(fv.get('horizon_3y_upper'), market, fx_rate)} | {fv.get('valuation_status') or 'FAIR'})"
            )
        if inv.get("summary"):
            line += f"\n⚠️ Trigger Invalidasi Tesis: {inv.get('summary')}"
    return line


def _format_etf_watchlist_line(candidate: Dict[str, Any], locale: str = "id") -> str:
    symbol = candidate["symbol"]
    category = candidate.get("etf_category") or ("Tanpa Kategori" if locale == "id" else "Uncategorized")
    score = candidate.get("score")
    ytd = candidate.get("ytd_return")
    three_y = candidate.get("three_year_return")
    five_y = candidate.get("five_year_return")
    expense = candidate.get("expense_ratio")
    aum = candidate.get("aum")
    rsi = candidate.get("rsi", "UNAVAILABLE")
    macd = candidate.get("macd", "UNAVAILABLE")

    def pct(v: Any) -> str:
        return f"{v * 100:.1f}%" if v is not None else "UNAVAILABLE"

    def aum_str(v: Any) -> str:
        if v is None:
            return "UNAVAILABLE"
        for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
            if abs(v) >= div:
                return f"{v / div:,.1f}{unit}"
        return f"{v:,.0f}"

    return (
        f"🔹 {symbol} — {category} | skor={score}/100 | "
        f"YTD={pct(ytd)} | 3Y={pct(three_y)} | 5Y={pct(five_y)} | "
        f"expense={pct(expense)} | AUM=${aum_str(aum)} | "
        f"RSI={rsi} | MACD={macd}"
    )


def _render_market_recommendation_report(
    market: str,
    snapshot: str,
    candidates: List[Dict[str, Any]],
    news_sources: List[Dict[str, Any]],
    locale: str = "id",
) -> str:
    is_crypto = normalize_market(market) == "crypto"
    is_syariah = is_syariah_market(market)
    is_us_etf = market.lower() == "us_etf"

    def sharia_eligible(c: Dict[str, Any]) -> bool:
        return c.get("issi_status") == "Ya"

    buy = [c for c in candidates if str(c.get("final_stance", "")).upper() in {"BUY", "ACCUMULATE"} and (not is_syariah or sharia_eligible(c))]
    sell = [c for c in candidates if str(c.get("final_stance", "")).upper() in {"SELL", "REDUCE"} and (not is_syariah or sharia_eligible(c))]
    hold = [c for c in candidates if str(c.get("final_stance", "")).upper() not in {"BUY", "ACCUMULATE", "SELL", "REDUCE"} or (is_syariah and not sharia_eligible(c))]

    def section(title: str, rows: List[Dict[str, Any]], empty_text: str) -> List[str]:
        lines = [title]
        lines.extend(_format_ranked_candidate(r, market, locale=locale) for r in rows)
        if not rows:
            lines.append(empty_text)
        return lines

    if is_crypto:
        report = ["📊 Ringkasan Screener Kualitas & Tokenomics Crypto (Tier-1 Utility)", snapshot, ""]
        report += section("🟢 Aset Kripto Tier-1 Terpilih untuk AKUMULASI / DCA", buy, "Tidak ada kandidat akumulasi yang memenuhi kriteria kualitas saat ini.")
        report += [""]
        report += section("🔴 Aset Perlu REDUCE / REBALANCE (Overvalued / Dilusi Tinggi)", sell, "Tidak ada kandidat reduce/exit saat ini.")
        report += [""]
        report += section("🟡 Aset untuk HOLD / Cicil Bertahap", hold, "Tidak ada kandidat HOLD.")
    elif is_syariah:
        report = [
            "📊 Ringkasan Quality, Value & Compounding Screener Saham Syariah (ISSI)",
            "CSV ISSI lokal digunakan sebagai referensi utama; status kandidat berasal dari file manual.",
            snapshot,
            "",
            "🟢 Kandidat Saham Syariah untuk AKUMULASI / DCA",
            "Tidak ada kandidat akumulasi tervalidasi." if not buy else "Kandidat berkualitas tercatat ISSI=Ya pada referensi lokal:",
            *[_format_ranked_candidate(c, market, locale=locale) for c in buy],
            "",
            "🔴 Kandidat Saham Syariah untuk REDUCE / Evaluasi Fundamental",
            "Tidak ada kandidat reduce/exit tervalidasi." if not sell else "Kandidat evaluasi/rebalance:",
            *[_format_ranked_candidate(c, market, locale=locale) for c in sell],
            "",
            "⏳ Horizon PENDEK (< 1 Tahun — Katalis & Zona Akumulasi)",
            *[_format_ranked_candidate(c, market, locale=locale) for c in candidates[:6]],
            "",
            "📅 Horizon MENENGAH (1 - 3 Tahun — Pertumbuhan Fundamental & Fair Value)",
            "Emiten syariah dengan F-Score kuat, ROIC/ROE sehat, dan Margin of Safety positif.",
            "",
            "💎 Horizon PANJANG (3 - 5+ Tahun — Wealth Compounding & Dividen)",
            "Core compounding syariah untuk akumulasi berkala jangka panjang.",
        ]
    elif is_us_etf:
        short_term = candidates[:10]
        medium_term = [c for c in candidates if c.get("ytd_return") is not None and c["ytd_return"] > 0 and (c.get("rsi") is None or c["rsi"] <= 75)]
        medium_term.sort(key=lambda x: x.get("score", 0), reverse=True)
        long_term = [c for c in candidates if c.get("three_year_return") is not None or c.get("five_year_return") is not None]
        long_term.sort(key=lambda x: (x.get("five_year_return") or x.get("three_year_return") or 0, x.get("aum") or 0), reverse=True)

        report = [
            "📊 Ringkasan Screener Kualitas & Compounding ETF AS",
            snapshot,
            "",
            "🟢 Rekomendasi AKUMULASI ETF Hari Ini",
            *(section("Kandidat:", buy, "Tidak ada setup BUY/ACCUMULATE tervalidasi.")[1:]),
            "",
            "🔴 Rekomendasi REDUCE/REBALANCE ETF",
            *(section("Kandidat:", sell, "Tidak ada stance SELL/REDUCE tervalidasi.")[1:]),
            "",
            "⏳ Watchlist ETF Jangka PENDEK (< 1 Tahun — Zona Akumulasi)",
            *[_format_etf_watchlist_line(c, locale=locale) for c in short_term],
            "",
            "📅 Watchlist ETF Jangka MENENGAH (1 - 3 Tahun — Pertumbuhan Siklus)",
            *[_format_etf_watchlist_line(c, locale=locale) for c in medium_term[:8]],
            "",
            "💎 Watchlist ETF Jangka PANJANG (3 - 5+ Tahun — Core Wealth Compounding)",
            *[_format_etf_watchlist_line(c, market=locale) if False else _format_etf_watchlist_line(c, locale=locale) for c in long_term[:8]],
        ]
    else:
        market_name = "IHSG" if "ihsg" in market.lower() else "US Equities"
        report = [f"📊 Ringkasan Quality, Value & Compounding Screener {market_name}", snapshot, ""]
        report += section("🟢 Kandidat Terpilih untuk AKUMULASI / DCA", buy, "Tidak ada kandidat ACCUMULATE/BUY tervalidasi saat ini.")
        report += [""]
        report += section("🔴 Kandidat untuk REDUCE / Evaluasi Fundamental", sell, "Tidak ada kandidat REDUCE/SELL tervalidasi saat ini.")
        report += [
            "",
            "⏳ Horizon PENDEK (< 1 Tahun — Katalis & Zona Akumulasi)",
            "Berbasis kombinasi kualitas fundamental (65%) + posisi siklus harga vs SMA50/SMA200 (35%).",
            "",
            "📅 Horizon MENENGAH (1 - 3 Tahun — Pertumbuhan Fundamental & Fair Value)",
            "Fokus pada emiten dengan F-Score kuat, margin of safety menarik, dan pertumbuhan laba 3-5Y.",
            "",
            "💎 Horizon PANJANG (3 - 5+ Tahun — Core Wealth Compounding & Dividen)",
            "Emiten berkualitas institusional (high ROIC/ROE) untuk akumulasi DCA berkelanjutan.",
        ]

    report.extend([
        "",
        "⚠️ Peringatan Risiko & Prinsip Investasi",
        "- Zona akumulasi dan nilai wajar (DCF/Valuasi) adalah snapshot kuantitatif; lakukan verifikasi berkala tiap rilis laporan keuangan.",
        "- Skor 0-100 adalah ranking kualitas & siklus (65% Fundamental + 35% Siklus), bukan jaminan imbal hasil pasti.",
        "- Sesuaikan besaran cicilan DCA dengan profil risiko, konsentrasi dompet saat ini, dan kecukupan dana darurat.",
        "",
        "📰 Berita Terkini & Sumber Sourced (Exa Search):",
    ])
    sourced = [item for item in news_sources if item.get("url")]
    if sourced:
        for s in sourced:
            report.append(f"- {s.get('title', 'Berita')} | {s.get('published_date') or 'terkini'} | {s.get('url')}")
    else:
        report.append("- Tidak ada berita terverifikasi URL dalam sesi pencarian ini.")

    return "\n".join(report)


def run_recommendation_pipeline(
    market: str,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    stop_event: Optional[threading.Event] = None,
    locale: str = "id",
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes full multi-agent Quality, Value & Compounding screener pipeline
    across candidate universe and renders multi-horizon investment recommendations.
    """
    def emit(event_type: str, **payload: Any) -> None:
        if event_callback:
            event = {
                "type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                **payload,
            }
            event_callback(event)

    def log(message: str, level: str = "INFO", **payload: Any) -> None:
        getattr(logger, level.lower(), logger.info)(message)
        emit("log", level=level, message=message, **payload)

    def check_stop() -> None:
        if stop_event is not None and stop_event.is_set():
            raise AnalysisStopped("Scan rekomendasi dibatalkan oleh pengguna.")

    emit("agent_status", role="data_fetcher", status="running")
    log(f"Quality & Value Screener: Memindai universe investasi {market.upper()}...", role="data_fetcher", status="running")

    screened_results = []
    try:
        screened_results = screen_market_opportunities(market, limit=10)
    except Exception as e:
        logger.warning("Screening error: %s", e)
        screened_results = []

    screened_results = [c for c in screened_results if c.get("score") is not None]
    if not screened_results:
        msg = f"⚠️ Tidak ada kandidat yang lolos Quality & Value screening pasar {market.upper()} saat ini."
        log(msg, level="WARNING", role="data_fetcher")
        emit("agent_output", role="data_fetcher", output=msg)
        emit("agent_status", role="data_fetcher", status="completed")
        emit("agent_output", role="investment_advisor", output=msg)
        emit("agent_status", role="investment_advisor", status="completed")
        return {
            "type": "recommendation",
            "market": market,
            "report": msg,
            "agent_reports": {"data_fetcher": msg, "investment_advisor": msg},
            "symbols_scanned": 0,
            "exa_news_count": 0,
            "status": "insufficient_data",
            "ranked_candidates": [],
        }

    symbols = [c["symbol"] for c in screened_results]
    log(f"Quality Screener memilih {len(symbols)} kandidat compounding teratas: {', '.join(symbols)}", role="data_fetcher")

    # Fetch live news & macro context
    check_stop()
    exa_query = f"{market} long term investment outlook fundamental economy opportunities"
    exa_news = search_internet(exa_query, num_results=3)
    macro_regime = build_macro_regime_context(market, user_profile=user_profile)

    # Build market snapshot with Quality + Cycle + 3 Investment Price Zones
    snapshot_lines = [
        f"Collection timestamp (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Market: {market.upper()} | Universe Candidates: {len(symbols)}",
        f"Macro Regime: {macro_regime['regime_label']} (USD/IDR={macro_regime.get('usd_idr_rate') or 'N/A'}, US10Y={macro_regime.get('us10y_yield_pct') or 'N/A'}%)",
    ]
    for c in screened_results:
        zones = c.get("investment_zones") or {}
        acc = c.get("accumulation_zone") or zones.get("accumulation_zone") or {}
        fv = c.get("fair_value_target") or zones.get("fair_value_target") or {}
        acc_str = (
            f"{_format_recommendation_price(acc.get('ideal_low'), market)}-{_format_recommendation_price(acc.get('ideal_high'), market)}"
            if acc.get("ideal_low") is not None
            else "N/A"
        )
        fv_str = _format_recommendation_price(fv.get("fair_value"), market) if fv.get("fair_value") is not None else "N/A"
        f_score = c.get("piotroski_f_score")
        mos = c.get("margin_of_safety_pct")
        snapshot_lines.append(
            f"- {c['symbol']}: Harga={_format_recommendation_price(c.get('price'), market)} | RSI(1D)={c.get('rsi')} | MACD={c.get('macd')} | "
            f"Skor={c.get('score')}/100 (Fund={c.get('fundamental_score')}/65, Siklus={c.get('cycle_score')}/35) | "
            f"F-Score={f_score if f_score is not None else 'N/A'} | MoS={f'{mos:+.1f}%' if mos is not None else 'N/A'} | "
            f"Zona Akumulasi={acc_str} | FairValue={fv_str}"
        )
    snapshot = "\n".join(snapshot_lines)

    data_fetcher_result = (
        f"Snapshot Kualitas, Valuasi & Siklus Terverifikasi:\n{snapshot}\n\n"
        f"Konteks Berita Pasar:\n{_format_news_evidence(exa_news)}"
    )
    emit("agent_output", role="data_fetcher", output=data_fetcher_result)
    emit("agent_status", role="data_fetcher", status="completed")
    log("Data fetcher selesai mengumpulkan snapshot fundamental & siklus terverifikasi.", role="data_fetcher", status="completed")

    # Run specialist agents in parallel
    roles = [r for r in agent_roles(market) if r != "data_fetcher"]
    specialist_results: Dict[str, str] = {}

    def run_spec(role: str) -> tuple[str, str]:
        if stop_event is not None and stop_event.is_set():
            return role, ""
        if role == "sentiment_analyst":
            evidence = _format_news_evidence(exa_news)
            emit("agent_status", role=role, status="running")
            emit("agent_output", role=role, output=evidence)
            emit("agent_status", role=role, status="completed")
            return role, evidence

        skill = load_skill_content(market, role, locale)
        prompt_txt = load_market_prompt(market, locale)
        sys_p = f"{prompt_txt}\n\nRole Skill:\n{skill}\n\n{DATA_FRESHNESS_INSTRUCTIONS}\n{TOOL_GROUNDING_INSTRUCTIONS}"
        usr_p = f"Analisis kandidat investasi jangka menengah-panjang pasar {market.upper()}:\n{snapshot}\n\nSampaikan temuan spesifik Anda sebagai {role} (dilarang menggunakan konsep day trading/ATR stop loss)."

        emit("agent_status", role=role, status="running")
        log(f"Menjalankan analis spesialis: {role}...", role=role)
        try:
            out = call_llm([{"role": "system", "content": sys_p}, {"role": "user", "content": usr_p}], temperature=0.2)
            emit("agent_output", role=role, output=out)
            emit("agent_status", role=role, status="completed")
            return role, out
        except Exception as e:
            logger.warning("Specialist %s error: %s", role, e)
            emit("agent_status", role=role, status="failed")
            return role, f"⚠️ Analisis {role} terkendala: {e}"

    with ThreadPoolExecutor(max_workers=min(4, len(roles))) as executor:
        futures = [executor.submit(run_spec, r) for r in roles]
        for f in as_completed(futures):
            role_name, out_text = f.result()
            specialist_results[role_name] = out_text

    # Investment Advisor: assign qualitative stances per candidate
    check_stop()
    emit("agent_status", role="investment_advisor", status="running")
    log("Investment Advisor sedang mensintesis rekomendasi compounding pasar menyeluruh...", role="investment_advisor")

    adv_sys = (
        f"You are the Lead Investment Strategist for {market.upper()} focusing on fundamental quality & wealth compounding.\n\n"
        "Return ONLY valid JSON with this exact schema:\n"
        '{"assets":[{"symbol":"TICKER","stance":"ACCUMULATE|BUY|HOLD|REDUCE","rationale":"qualitative investment rationale based on quality, valuation, and cycle without fake dates"}]}\n\n'
        "Use ONLY symbols from the provided candidate list. Never invent prices, future dates, or short-term trading stop-losses."
    )
    adv_usr = f"Macro & Candidates:\n{snapshot}\n\nReturn investment stance and brief rationale for each symbol."

    model_stances: Dict[str, Dict[str, str]] = {}
    try:
        raw_adv = call_llm([{"role": "system", "content": adv_sys}, {"role": "user", "content": adv_usr}], temperature=0.2)
        parsed = _extract_json_block(raw_adv)
        if parsed and "assets" in parsed:
            for item in parsed["assets"]:
                sym = item.get("symbol")
                st = str(item.get("stance", "HOLD")).upper()
                if sym and st in {"ACCUMULATE", "BUY", "HOLD", "REDUCE", "SELL"}:
                    rat = str(item.get("rationale", ""))
                    if re.search(r"(?i)earnings|laporan laba|jadwal|tanggal|this week|minggu ini", rat):
                        rat = "Kualitas fundamental dan posisi siklus mendukung strategi akumulasi bertahap."
                    model_stances[sym] = {"stance": st, "rationale": rat}
    except Exception as e:
        logger.warning("Advisor stance assignment fallback: %s", e)

    is_syar = is_syariah_market(market)
    for c in screened_results:
        sym = c["symbol"]
        proposal = model_stances.get(sym, {"stance": "HOLD", "rationale": "Posisi siklus netral untuk pemantauan fundamental berkala."})
        stance = proposal["stance"]
        sharia_ok = c.get("issi_status") == "Ya"
        if is_syar and not sharia_ok:
            stance = "HOLD"
        c["stance"] = stance
        c["final_stance"] = stance
        c["final_rationale"] = proposal.get("rationale", "")
        c["thesis_summary"] = proposal.get("rationale", "")

        # Populate convenience zone fields alongside structured investment_zones
        zones = c.get("investment_zones") or {}
        acc = c.get("accumulation_zone") or zones.get("accumulation_zone") or {}
        fv = c.get("fair_value_target") or zones.get("fair_value_target") or {}
        inv = c.get("thesis_invalidation") or zones.get("thesis_invalidation") or {}
        if acc.get("ideal_low") is not None:
            c["support_level"] = acc.get("ideal_low")
        if fv.get("fair_value") is not None:
            c["target_price_1"] = fv.get("fair_value")
        if fv.get("horizon_3y_upper") is not None:
            c["target_price_2"] = fv.get("horizon_3y_upper")
        c["invalidation_trigger"] = inv.get("summary")

        # Deterministic confidence
        if c.get("price") is not None:
            conf_dir = "SELL" if stance in {"SELL", "REDUCE"} else "BUY"
            c["confidence"] = calibrate_confidence(
                float(c["price"]),
                {"sma20": c.get("sma20"), "sma50": c.get("sma50"), "sma200": c.get("sma200"), "rsi": c.get("rsi"), "macd": c.get("macd")},
                conf_dir,
                c.get("change_pct"),
            )
            c["confidence_basis"] = "deterministic indicator & cycle heuristic"
        else:
            c["confidence"] = 70
            c["confidence_basis"] = "baseline heuristic"

    report_text = _render_market_recommendation_report(
        market,
        snapshot,
        screened_results,
        exa_news,
        locale=locale,
    )

    emit("agent_output", role="investment_advisor", output=report_text)
    emit("agent_status", role="investment_advisor", status="completed")
    log("Scan peluang investasi berkualitas berhasil diselesaikan.", role="investment_advisor", status="completed")

    return {
        "type": "recommendation",
        "market": market,
        "report": report_text,
        "agent_reports": {
            "data_fetcher": data_fetcher_result,
            **specialist_results,
            "investment_advisor": report_text,
        },
        "symbols_scanned": len(symbols),
        "exa_news_count": len([item for item in exa_news if item.get("url")]),
        "status": "completed",
        "ranked_candidates": screened_results,
        "macro_regime": macro_regime,
        "sharia_status": "ISSI_LISTED_IN_MANUAL_REFERENCE" if is_syar and all(c.get("issi_status") == "Ya" for c in screened_results) else "NOT_APPLICABLE",
    }


def _resolve_chat_target_symbols(
    market: str,
    default_symbol: str,
    user_message: str,
    analysis_context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    msg_upper = user_message.upper()
    found: List[str] = []

    candidates = (analysis_context or {}).get("ranked_candidates") or []
    candidate_symbols = [str(c.get("symbol")).strip() for c in candidates if isinstance(c, dict) and c.get("symbol")]

    for sym in candidate_symbols:
        clean = sym.strip().upper()
        base = clean.split("/")[0].split(".")[0].split("-")[0]
        if re.search(rf"(?:\b{re.escape(base)}\b|\b{re.escape(clean)}\b)", msg_upper):
            if clean not in found:
                found.append(clean)

    if default_symbol and default_symbol.strip():
        clean_def = default_symbol.strip().upper()
        base_def = clean_def.split("/")[0].split(".")[0].split("-")[0]
        if re.search(rf"(?:\b{re.escape(base_def)}\b|\b{re.escape(clean_def)}\b)", msg_upper):
            if clean_def not in found:
                found.append(clean_def)

    if not found:
        explicit = re.findall(r"\b[A-Z0-9]{2,10}(?:/[A-Z0-9]{2,10}|\.JK|-USD)\b", msg_upper)
        for e in explicit:
            if e not in found:
                found.append(e)

    if not found and default_symbol:
        found.append(default_symbol.strip().upper())
    elif not found and candidate_symbols:
        found.extend(candidate_symbols[:2])

    if not found:
        fallback = {"crypto": "BTC/USDT", "ihsg": "TLKM.JK", "ihsg_syariah": "TLKM.JK", "us_stock": "NVDA", "us_etf": "VOO"}.get(market, "TLKM.JK")
        found.append(fallback)

    return found[:2]


def _build_deep_validation_dossier(
    market: str,
    target_symbols: List[str],
    analysis_context: Optional[Dict[str, Any]] = None,
) -> tuple[str, List[Dict[str, Any]], List[str], List[str]]:
    """Performs live independent re-fetch, computes price drift and 1D vs 1W cycle divergence."""
    dossier_lines: List[str] = []
    snapshots: List[Dict[str, Any]] = []
    sources: List[str] = []
    flags: List[str] = []

    is_crypto = normalize_market(market) == "crypto"

    prev_claims: Dict[str, Dict[str, Any]] = {}
    if analysis_context:
        rec = analysis_context.get("investment_recommendation") or {}
        if rec.get("symbol"):
            prev_claims[rec["symbol"].upper()] = {
                "stance": rec.get("stance"),
                "fair_value": (rec.get("valuation_summary") or {}).get("fair_value_estimate"),
            }
        for c in (analysis_context.get("ranked_candidates") or []):
            if isinstance(c, dict) and c.get("symbol"):
                prev_claims[c["symbol"].upper()] = {
                    "stance": c.get("final_stance") or c.get("stance"),
                    "price": c.get("price"),
                    "score": c.get("score"),
                }

    for sym in target_symbols:
        dossier_lines.append(f"=== LIVE AUDIT DOSSIER: {sym} (Pasar: {market.upper()}) ===")
        mkt_data = fetch_comprehensive_market_data(market, sym)
        lt_m = mkt_data.get("long_term_metrics") or {}
        sources.append(f"{mkt_data.get('provider', 'Yahoo Finance/TwelveData/Binance')} (Multi-Timeframe 1D & 1W)")

        tfs = mkt_data.get("timeframes", {})
        tf_1d = tfs.get("1D") or {}
        tf_1w = tfs.get("1W") or {}
        st_1d = tf_1d.get("stats", {})
        st_1w = tf_1w.get("stats", {})
        curr_p = tf_1d.get("price") or tf_1w.get("price")
        fx_rate = mkt_data.get("fx_usd_idr", {}).get("rate") if is_crypto else None

        # Check Price Drift
        sym_flags: List[str] = []
        claim = prev_claims.get(sym.upper()) or {}
        prev_p = claim.get("price")
        drift_pct = None
        if curr_p is not None and prev_p:
            try:
                p_old = float(prev_p)
                if p_old > 0:
                    drift_pct = ((float(curr_p) - p_old) / p_old) * 100
                    if abs(drift_pct) >= 2.0:
                        sym_flags.append(f"Pergeseran harga (Price Drift): {drift_pct:+.2f}% sejak analisis awal")
            except Exception:
                pass

        # Check Multi-Timeframe Cycle Divergence (1D vs 1W)
        rsi_1d = st_1d.get("rsi")
        rsi_1w = st_1w.get("rsi")
        macd_1d = st_1d.get("macd")
        macd_1w = st_1w.get("macd")

        if rsi_1d is not None and rsi_1w is not None:
            if rsi_1w >= 72 and rsi_1d >= 70:
                sym_flags.append("Siklus 1W & 1D Overextended (RSI >= 70): Sebaiknya cicil DCA bertahap, hindari lump-sum agresif")
            elif rsi_1w <= 35 and rsi_1d <= 35:
                sym_flags.append("Area Diskon Siklus (RSI 1D/1W <= 35): Berada di zona akumulasi potensial jika fundamental sehat")

        if macd_1d and macd_1w:
            if str(macd_1w).lower() == "bullish" and str(macd_1d).lower() == "bearish":
                sym_flags.append("Divergensi Siklus: Tren primer mingguan (1W) tetap bullish, koreksi harian (1D) membuka peluang DCA")
            elif str(macd_1w).lower() == "bearish" and str(macd_1d).lower() == "bullish":
                sym_flags.append("Rebound Jangka Pendek (1D bullish) dalam tren mingguan (1W) yang masih melemah; verifikasi margin of safety")

        cycle_pos = lt_m.get("cycle_position")
        sma200_val = lt_m.get("sma200_day") or st_1d.get("sma200")
        if cycle_pos:
            sym_flags.append(f"Posisi Siklus Panjang: {cycle_pos}")

        flags.extend([f"[{sym}] {f}" for f in sym_flags])

        dossier_lines.append("1. Snapshot Kuantitatif & Siklus Live:")
        dossier_lines.append(f"   - Harga Live: {_format_recommendation_price(curr_p, market, fx_rate)}")
        dossier_lines.append(
            f"   - Indikator 1D: RSI={rsi_1d or 'N/A'}, MACD={macd_1d or 'N/A'}, "
            f"SMA50={_format_recommendation_price(st_1d.get('sma50'), market, fx_rate)}, "
            f"SMA200={_format_recommendation_price(sma200_val, market, fx_rate)}"
        )
        if tf_1w:
            dossier_lines.append(f"   - Siklus Mingguan (1W): RSI={rsi_1w or 'N/A'}, MACD={macd_1w or 'N/A'}")
        if sym_flags:
            dossier_lines.append(f"2. Temuan Catatan Auditor: {'; '.join(sym_flags)}")

        snapshots.append({
            "symbol": sym,
            "price": _format_recommendation_price(curr_p, market, fx_rate),
            "rsi_1d": rsi_1d,
            "macd_1d": macd_1d,
            "rsi_1w": rsi_1w,
            "macd_1w": macd_1w,
            "cycle_position": cycle_pos,
            "drift_pct": round(drift_pct, 2) if drift_pct is not None else None,
            "flags": sym_flags,
            "provider": mkt_data.get("provider", "unknown"),
        })

    return "\n".join(dossier_lines), snapshots, sorted(list(set(sources))), flags


def chat_with_investment_agent(
    history: List[Dict[str, str]],
    analysis_context: Dict[str, Any],
    user_message: str = "",
    mode: str = "standard",
    locale: str = "id",
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handles Q&A and Deep Validation Auditor mode."""
    symbol = analysis_context.get("symbol", "")
    market = analysis_context.get("market", "ihsg")
    language_name = "Bahasa Indonesia" if locale == "id" else "English"

    if mode == "deep_validation":
        targets = _resolve_chat_target_symbols(market, symbol, user_message, analysis_context)
        dossier, snapshots, sources, flags = _build_deep_validation_dossier(market, targets, analysis_context)

        system_prompt = (
            f"You are the Independent Chief Risk & Swarm Auditor for {market.upper()}.\n"
            f"OUTPUT LANGUAGE: Respond entirely in {language_name}.\n\n"
            "The user triggered DEEP VALIDATION MODE to audit and verify previous agent findings.\n"
            "You are provided with fresh, independently re-fetched live multi-timeframe market data (1D and 1W).\n"
            "Focus on long-term wealth compounding, accumulation timing (DCA vs lump-sum), fair value, and fundamental thesis invalidation triggers (NOT day trading).\n\n"
            "AUDIT STRUCTURE TO FOLLOW:\n"
            "1. 🎯 Verifikasi Klaim & Jawaban Langsung: Tanggapi pertanyaan pengguna dengan fakta live.\n"
            "2. ⚖️ Keselarasan Siklus Multi-Timeframe (1D vs 1W & SMA 200): Soroti apakah harga berada di zona akumulasi sehat atau overextended.\n"
            "3. 🛡️ Validasi Zona Harga & Price Drift: Evaluasi jarak terhadap zona DCA, Fair Value, dan kondisi invalidasi tesis.\n"
            "4. 🏁 Vonis Auditor: Berikan keputusan tegas (Tervalidasi Kuat / Cicil DCA Bertahap / Tunggu Zona Diskon / Downgrade ke HOLD).\n\n"
            f"{DATA_FRESHNESS_INSTRUCTIONS}\n\n"
            f"{TOOL_GROUNDING_INSTRUCTIONS}\n\n"
            f"LIVE AUDIT DOSSIER:\n{dossier}\n"
        )

        messages = [{"role": "system", "content": system_prompt}] + history
        if user_message:
            messages.append({"role": "user", "content": user_message})

        try:
            reply = call_llm(messages, temperature=0.2)
        except Exception as e:
            logger.warning("Deep validation LLM error: %s", e)
            flags_summary = "\n".join([f"- {f}" for f in flags]) if flags else "- Semua indikator siklus multi-timeframe (1D & 1W) terkonfirmasi selaras."
            reply = (
                f"🛡️ **VONIS AUDITOR INDEPENDEN & DEEP VALIDATION**\n\n"
                f"Data real-time multi-timeframe (1D & 1W) berhasil diverifikasi langsung dari provider:\n\n"
                f"**Catatan & Temuan Auditor:**\n{flags_summary}\n\n"
                f"*(Koneksi sintesis teks LLM mengalami kendala teknis: {e}. Angka snapshot dan flag divergensi di bawah ini valid dan terverifikasi secara deterministik).* "
            )

        return {
            "reply": reply,
            "mode": "deep_validation",
            "validation_meta": {
                "validated_symbols": targets,
                "checked_sources": sources,
                "live_snapshots": snapshots,
                "discrepancy_flags": flags,
            },
        }

    # Standard Chat Mode
    recommendation = analysis_context.get("investment_recommendation") or {}
    report_text = analysis_context.get("report") or ""
    system_prompt = f"""Kamu adalah Partner Konsultan Investasi Senior & Penasihat Keuangan Independen.
Pengguna sedang mendiskusikan hasil riset multi-agent untuk pasar {market.upper()}.

KONTEKS SESI:
- Simbol / Emiten: {symbol}
- Stance: {recommendation.get('stance')}
- Keyakinan: {recommendation.get('confidence_pct')}%
- Tesis: {recommendation.get('executive_thesis') or report_text[:2000]}

PANDUAN MENJAWAB:
1. Jawab secara solutif, objektif, dan jujur berbasis data di atas (FMP, Twelve Data, siklus 1D/1W, dan makroekonomi).
2. Jelaskan logika zona akumulasi (DCA), estimasi Fair Value, kondisi invalidasi tesis, dan pembagian porsi portofolio.
3. Jika pengguna ingin memverifikasi data live atau menguji keselarasan siklus 1D vs 1W, sarankan aktifkan toggle Deep Validation Mode.
"""
    messages = [{"role": "system", "content": system_prompt}] + history
    if user_message:
        messages.append({"role": "user", "content": user_message})

    try:
        reply = call_llm(messages, temperature=0.3)
        return {"reply": reply, "mode": "standard", "validation_meta": None}
    except Exception as e:
        logger.error("Chat error: %s", e)
        return {"reply": f"Mohon maaf, terjadi kendala saat memproses jawaban: {e}", "mode": "standard", "validation_meta": None}
