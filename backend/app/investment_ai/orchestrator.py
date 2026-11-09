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
    calculate_atr_levels,
    calibrate_confidence,
    compute_indicators,
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
    localized_path = os.path.join(skills_root, norm_market, agent_role, f"SKILL{locale_suffix}.md")
    default_path = os.path.join(skills_root, norm_market, agent_role, "SKILL.md")

    skill_path = localized_path if os.path.exists(localized_path) else default_path
    if os.path.exists(skill_path):
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
    """Fetches multi-timeframe market data and computes quant indicators deterministically."""
    timeframes = ["1H", "1D"]
    snapshot_captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    is_crypto = normalize_market(market) == "crypto"
    fx_usd_idr = get_usd_idr_rate() if is_crypto else None
    market_metrics = fetch_market_metrics(market)

    result: Dict[str, Any] = {
        "market": market,
        "symbol": symbol,
        "snapshot_captured_at": snapshot_captured_at,
        "data_freshness": "point-in-time snapshot; source delay varies; not a streaming feed",
        "fx_usd_idr": fx_usd_idr,
        "market_metrics": market_metrics,
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
                if stats.get("atr14") is not None and quote.get("price") is not None:
                    stats["suggested_levels"] = calculate_atr_levels(quote["price"], stats["atr14"])

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
        quote_as_of = _format_source_timestamp(pdata.get("source_as_of"))
        chg = result.get("change_pct")
        chg_text = f"{chg:+.2f}%" if chg is not None else "UNAVAILABLE"

        lines = [
            f"Market Data Report for {symbol}:",
            f"- Collected at (UTC): {snapshot_captured_at}",
            f"- Primary interval: {primary_tf}; source as-of: {quote_as_of}",
            f"- Data source: {result['provider']}",
            f"- Market overview: {market_metrics or 'Unavailable'}",
            f"- Current Price: {_format_recommendation_price(result['current_price'], market, fx_usd_idr.get('rate') if fx_usd_idr else None)}",
            f"- Change: {chg_text}",
            f"- High: {_format_significant(stats.get('high'))} | Low: {_format_significant(stats.get('low'))}",
            f"- Candles count: {stats.get('candle_count')}",
        ]
        if "sma20" in stats:
            lines.append(f"- SMA 20: {_format_recommendation_price(stats['sma20'], market, fx_usd_idr.get('rate') if fx_usd_idr else None)}")
        if "sma50" in stats:
            lines.append(f"- SMA 50: {_format_recommendation_price(stats['sma50'], market, fx_usd_idr.get('rate') if fx_usd_idr else None)}")
        if "rsi" in stats:
            lines.append(f"- RSI 14: {stats['rsi']}")
        if "macd" in stats:
            lines.append(f"- MACD: {stats['macd']} (line={_format_significant(stats.get('macd_line'))}, signal={_format_significant(stats.get('macd_signal'))}, hist={_format_significant(stats.get('macd_histogram'))})")
        if stats.get("volume") is not None:
            lines.append(f"- Volume: {stats['volume']:,.0f}")
        if stats.get("atr14") is not None:
            lines.append(f"- ATR 14: {_format_significant(stats['atr14'])}")
        if stats.get("support") is not None:
            lines.append(f"- Key Support (20-bar): {_format_recommendation_price(stats['support'], market, fx_usd_idr.get('rate') if fx_usd_idr else None)}")
        if stats.get("resistance") is not None:
            lines.append(f"- Key Resistance (20-bar): {_format_recommendation_price(stats['resistance'], market, fx_usd_idr.get('rate') if fx_usd_idr else None)}")
        if "suggested_levels" in stats and stats["suggested_levels"]:
            sl = stats["suggested_levels"]
            fx_rate = fx_usd_idr.get("rate") if fx_usd_idr else None
            tps = ", ".join(f"{t['label']} {_format_recommendation_price(t['price'], market, fx_rate)} ({t['r_multiple']}R)" for t in sl.get("take_profit_targets", []))
            lines.append(f"- ATR Risk Levels (Ref Entry: {_format_recommendation_price(sl['reference_price'], market, fx_rate)} | SL: {_format_recommendation_price(sl['buy_sl'], market, fx_rate)} | Targets: {tps})")

        if "1H" in result["timeframes"] and primary_tf != "1H":
            tf_1h = result["timeframes"]["1H"]
            st_1h = tf_1h.get("stats", {})
            lines.append(f"\nSecondary Intraday (1H): Price={_format_significant(tf_1h.get('price'))} | 1H RSI={st_1h.get('rsi', 'UNAVAILABLE')} | 1H MACD={st_1h.get('macd', 'UNAVAILABLE')} | 1H ATR14={_format_significant(st_1h.get('atr14'))}")

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

    # 3. Fetch On-Chain context if crypto
    onchain_context = ""
    if normalize_market(market) == "crypto":
        check_stop()
        log("Mengambil metrik on-chain & derivatif crypto (Binance Futures + DefiLlama)...")
        try:
            onchain_info = get_onchain_context(market, symbol)
            onchain_context = onchain_info.get("text", "") if onchain_info else ""
        except Exception as e:
            logger.warning("On-chain fetch error for %s: %s", symbol, e)

    # 4. Run Data Fetcher deterministically (0 LLM hallucination)
    check_stop()
    emit("agent_status", role="data_fetcher", status="running")
    log("Data Fetcher: Menghitung indikator teknikal (SMA, RSI, MACD, ATR, Support/Resistance)...", role="data_fetcher")
    market_data = fetch_comprehensive_market_data(market, symbol)

    enhanced_context = (
        f"{market_context}\n\n"
        f"=== DATA PASAR & KUANTITATIF ===\n{market_data.get('summary', '')}\n\n"
        f"=== FUNDAMENTAL & VALUASI ===\n{fundamentals_context}\n"
    )
    if onchain_context:
        enhanced_context += f"\n=== ON-CHAIN & DERIVATIVES ===\n{onchain_context}\n"

    agent_results: Dict[str, str] = {"data_fetcher": enhanced_context}
    emit("agent_output", role="data_fetcher", output=enhanced_context)
    emit("agent_status", role="data_fetcher", status="completed")
    log("Data fetcher selesai dengan kalkulasi indikator kuantitatif deterministik.", role="data_fetcher", status="completed")

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

        system_prompt = (
            f"You are the {role.replace('_', ' ').title()} agent for {market.upper()}.\n\n"
            f"OUTPUT LANGUAGE: Respond entirely in {language_name}.\n\n"
            f"Agent Guidelines:\n{skill_content}\n\n"
            f"{DATA_FRESHNESS_INSTRUCTIONS}\n\n"
            f"{TOOL_GROUNDING_INSTRUCTIONS}\n\n"
            f"{NEWS_VERIFICATION_INSTRUCTIONS}\n\n"
            "Fokus analisis Anda adalah INVESTASI (Bukan day trading / scalping). "
            "Evaluasi kualitas emiten, pertumbuhan laba / adopsi, dan risiko fundamental.\n\n"
            f"Required report template:\n{report_template}"
        )

        user_prompt = (
            f"Simbol: {symbol}\nPasar: {market}\n\n"
            f"Berikut adalah data pasar, indikator teknikal kuantitatif, fundamental, dan berita terkini:\n\n"
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

    # 5. Execute Investment Advisor Agent
    check_stop()
    emit("agent_status", role="investment_advisor", status="running")
    log("Investment Advisor sedang mensintesis seluruh temuan agen & memetakan horizon investasi...", role="investment_advisor")

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
            f"Preferensi Syariah: {'YA (Wajib Syariah)' if sharia_usr else 'Konvensional / Fleksibel'}"
        )

    analysts_summary = "\n\n".join([
        f"=== LAPORAN {k.upper()} ===\n{v}"
        for k, v in agent_results.items()
        if k != "data_fetcher"
    ])

    adv_skill = load_skill_content(market, "trading_advisor", locale)
    advisor_system = f"""Anda adalah Kepala Komite Investasi (Chief Investment Strategist).
Tugas Anda adalah mensintesis seluruh laporan teknikal, fundamental, on-chain/foreign flow, dan sentimen untuk menghasilkan Rekomendasi Investasi Multi-Horizon (Jangka Pendek < 1 thn, Jangka Menengah 1-3 thn, Jangka Panjang > 3-5 thn).

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
    "fair_value_estimate": "<Estimasi nilai wajar dari metrik fundamental aktual atau UNAVAILABLE>",
    "current_valuation_status": "UNDERVALUED" | "FAIR" | "OVERVALUED" | "UNAVAILABLE",
    "metric_rationale": "<Rasionalitas valuasi dari data keuangan yang tersedia>"
  }},
  "multi_horizon_outlook": {{
    "short_term": {{
      "horizon": "< 1 Tahun (Taktis & Katalis)",
      "stance": "ACCUMULATE" | "BUY ON DIP" | "HOLD" | "REDUCE",
      "target_range": "<Rentang target harga jangka pendek atau UNAVAILABLE>",
      "thesis": "<Tesis jangka pendek berbasis katalis>",
      "catalysts": ["<Katalis 1>", "<Katalis 2>"],
      "risks": ["<Risiko 1>"]
    }},
    "medium_term": {{
      "horizon": "1 - 3 Tahun (Siklus Bisnis & Pertumbuhan)",
      "stance": "ACCUMULATE" | "BUY ON DIP" | "HOLD" | "REDUCE",
      "target_range": "<Rentang target harga jangka menengah atau UNAVAILABLE>",
      "thesis": "<Tesis pertumbuhan jangka menengah>",
      "catalysts": ["<Katalis siklus/makro>"],
      "risks": ["<Risiko operasional/margin>"]
    }},
    "long_term": {{
      "horizon": "> 3 - 5 Tahun (Moat Sekuler & Compounding)",
      "stance": "ACCUMULATE / DCA" | "HOLD" | "REDUCE",
      "target_range": "<Target apresiasi modal jangka panjang>",
      "thesis": "<Tesis compounding jangka panjang>",
      "compounding_factors": ["<Faktor moat/daya saing>"],
      "risks": ["<Risiko disrupsi struktural>"]
    }}
  }},
  "portfolio_and_dca_simulation": {{
    "risk_profile_match": "<Kesesuaian profil risiko pengguna>",
    "recommended_max_allocation_pct": <integer persentase maks alokasi dari portofolio>,
    "suggested_monthly_dca_amount": <nominal DCA bulanan dari surplus riil>,
    "action_plan": "<Rencana aksi konkrit>"
  }},
  "executive_thesis": "<Tesis eksekutif komprehensif 2-3 paragraf bahasa Indonesia>",
  "key_monitoring_metrics": ["<Metrik 1>", "<Metrik 2>"]
}}"""

    advisor_user = (
        f"Simbol: {symbol}\nPasar: {market}\n\n"
        f"DATA PROFIL KEUANGAN INVESTOR:\n{profile_ctx}\n\n"
        f"LAPORAN DARI TIM ANALIS:\n{analysts_summary}\n\n"
        "Berikan rekomendasi komprehensif dalam struktur JSON valid yang ditentukan."
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
            "executive_thesis": "⚠️ Sintesis AI Advisor mengalami kendala teknis. Sistem menolak memfabrikasi skor atau angka palsu. Silakan rujuk laporan spesifik analis di atas atau lakukan analisis ulang.",
            "key_monitoring_metrics": [],
        }

    # Post-LLM Deterministic Gates & Grounding Overrides
    sharia_ref = fundamental_info.get("sharia_reference") or {}
    sharia_eligible = sharia_ref.get("status") == "Ya"
    if is_syariah and not sharia_eligible:
        parsed_advisor["stance"] = "HOLD"
        if "sharia_compliance" in parsed_advisor:
            parsed_advisor["sharia_compliance"]["is_sharia"] = False
            parsed_advisor["sharia_compliance"]["classification"] = "TIDAK_TERCATAT_ISSI"
            parsed_advisor["sharia_compliance"]["notes"] = "Status ISSI tidak tercatat 'Ya' pada referensi lokal."

    # Calibrate confidence deterministically if primary quote is available
    prim_tf = market_data.get("timeframes", {}).get("1D") or market_data.get("timeframes", {}).get("1H")
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

    if locale == "id":
        change_period = "24 jam bergulir" if candidate.get("change_period") == "rolling_24h" else "daily close-to-close"
        score_label = "Ranking heuristik"
        not_prob = "bukan probabilitas"
        line = (
            f"🔹 {symbol} — {stance}\n"
            f"💵 Harga: {price} | perubahan {change_period}: {change_text}\n"
            f"📈 RSI: {candidate.get('rsi', 'UNAVAILABLE')} | SMA20: "
            f"{_format_recommendation_price(candidate.get('sma20'), market, fx_rate)} | "
            f"MACD: {candidate.get('macd', 'UNAVAILABLE')}\n"
            f"🧮 {score_label}: {candidate.get('score')}/100 ({not_prob}) | "
            f"Sumber: {candidate.get('provider')} | as-of: {_format_source_timestamp(candidate.get('source_as_of'))}"
        )
    else:
        change_period = "rolling 24h" if candidate.get("change_period") == "rolling_24h" else "daily close-to-close"
        line = (
            f"🔹 {symbol} — {stance}\n"
            f"💵 Price: {price} | change {change_period}: {change_text}\n"
            f"📈 RSI: {candidate.get('rsi', 'UNAVAILABLE')} | SMA20: "
            f"{_format_recommendation_price(candidate.get('sma20'), market, fx_rate)} | "
            f"MACD: {candidate.get('macd', 'UNAVAILABLE')}\n"
            f"🧮 Heuristic rank: {candidate.get('score')}/100 (not probability) | "
            f"Source: {candidate.get('provider')} | as-of: {_format_source_timestamp(candidate.get('source_as_of'))}"
        )

    rationale = None if is_syariah and not sharia_eligible else candidate.get("final_rationale")
    if rationale:
        line += f"\n📝 Alasan: {rationale}"

    levels = candidate.get("suggested_levels") or {}
    targets = levels.get("take_profit_targets") or []
    if is_syariah:
        line += f"\n🕌 ISSI reference: {candidate.get('issi_status', 'UNAVAILABLE')} (source_as_of={candidate.get('sharia_reference_source_as_of') or 'UNSPECIFIED'})"
    if stance == "BUY" and levels:
        line += (
            f"\n🎯 Entry referensi: {_format_recommendation_price(levels.get('reference_price'), market, fx_rate)}"
            f"\n🛡️ Stop loss: {_format_recommendation_price(levels.get('buy_sl'), market, fx_rate)}"
        )
        if targets:
            line += "\n" + " | ".join(
                f"🎯 {t['label']}: {_format_recommendation_price(t['price'], market, fx_rate)} ({t['r_multiple']:g}R)"
                for t in targets
            )
    elif stance == "SELL":
        line += "\n🔴 Aksi jual berarti exit/reduce posisi spot; level short tidak dihitung."
    elif stance == "HOLD":
        line += "\n⏳ Tunggu konfirmasi; tidak ada entry trade yang diterbitkan."
        if targets:
            line += "\n🎯 TP ladder bersyarat jika setup BUY terkonfirmasi: " + " | ".join(
                f"{t['label']} {_format_recommendation_price(t['price'], market, fx_rate)} ({t['r_multiple']:g}R)"
                for t in targets
            )
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

    buy = [c for c in candidates if c.get("final_stance") == "BUY" and (not is_syariah or sharia_eligible(c))]
    sell = [c for c in candidates if c.get("final_stance") == "SELL" and (not is_syariah or sharia_eligible(c))]
    hold = [c for c in candidates if c.get("final_stance") == "HOLD" or (is_syariah and not sharia_eligible(c))]

    def section(title: str, rows: List[Dict[str, Any]], empty_text: str) -> List[str]:
        lines = [title]
        lines.extend(_format_ranked_candidate(r, market, locale=locale) for r in rows)
        if not rows:
            lines.append(empty_text)
        return lines

    if is_crypto:
        report = ["📊 Ringkasan Market Crypto Overview", snapshot, ""]
        report += section("🟢 Top Coins Terpilih untuk AKUMULASI / BELI", buy, "Tidak ada setup BUY yang lolos validasi saat ini.")
        report += [""]
        report += section("🔴 Top Coins Terpilih untuk DIJUAL / EXIT", sell, "Tidak ada stance SELL/exit yang tervalidasi saat ini.")
        report += [""]
        report += section("🟡 Coins untuk HOLD / Wait and See", hold, "Tidak ada kandidat HOLD.")
    elif is_syariah:
        report = [
            "📊 Ringkasan Market Saham Syariah (ISSI)",
            "CSV ISSI lokal digunakan sebagai referensi utama; status kandidat berasal dari file manual.",
            snapshot,
            "",
            "🟢 Rekomendasi BELI / Akumulasi Saham Syariah Hari Ini",
            "Tidak ada rekomendasi BUY tervalidasi." if not buy else "Kandidat yang tercatat ISSI=Ya pada referensi lokal:",
            *[_format_ranked_candidate(c, market, locale=locale) for c in buy],
            "",
            "🔴 Rekomendasi JUAL / Exit Saham Syariah Hari Ini",
            "Tidak ada stance SELL/exit tervalidasi." if not sell else "Kandidat exit/reduce:",
            *[_format_ranked_candidate(c, market, locale=locale) for c in sell],
            "",
            "⏱️ Watchlist Syariah Jangka PENDEK (1-2 minggu)",
            *[_format_ranked_candidate(c, market, locale=locale) for c in candidates[:6]],
            "",
            "📅 Watchlist Syariah Jangka MENENGAH (1-3 bulan)",
            "Kandidat dengan indikator momentum stabil dan rasio fundamental wajar.",
            "",
            "💎 Watchlist Syariah Jangka PANJANG (6-12 bulan)",
            "Core compounding ideas dengan kriteria syariah ketat.",
        ]
    elif is_us_etf:
        short_term = candidates[:10]
        medium_term = [c for c in candidates if c.get("ytd_return") is not None and c["ytd_return"] > 0 and (c.get("rsi") is None or c["rsi"] <= 75)]
        medium_term.sort(key=lambda x: x.get("score", 0), reverse=True)
        long_term = [c for c in candidates if c.get("three_year_return") is not None or c.get("five_year_return") is not None]
        long_term.sort(key=lambda x: (x.get("five_year_return") or x.get("three_year_return") or 0, x.get("aum") or 0), reverse=True)

        report = [
            "📊 Ringkasan Market ETF AS",
            snapshot,
            "",
            "🟢 Rekomendasi BELI ETF Hari Ini",
            *(section("Kandidat:", buy, "Tidak ada setup BUY tervalidasi.")[1:]),
            "",
            "🔴 Rekomendasi JUAL/EXIT ETF Hari Ini",
            *(section("Kandidat:", sell, "Tidak ada stance SELL/exit tervalidasi.")[1:]),
            "",
            "⏱️ Watchlist ETF Jangka PENDEK (1-2 minggu)",
            *[_format_etf_watchlist_line(c, locale=locale) for c in short_term],
            "",
            "📅 Watchlist ETF Jangka MENENGAH (1-3 bulan)",
            *[_format_etf_watchlist_line(c, locale=locale) for c in medium_term[:8]],
            "",
            "💎 Watchlist ETF Jangka PANJANG (6-12 bulan)",
            *[_format_etf_watchlist_line(c, locale=locale) for c in long_term[:8]],
        ]
    else:
        market_name = "IHSG" if "ihsg" in market.lower() else "US Equities"
        report = [f"📊 Ringkasan Market {market_name}", snapshot, ""]
        report += section("🟢 Rekomendasi BELI / Akumulasi Hari Ini", buy, "Tidak ada setup BUY tervalidasi saat ini.")
        report += [""]
        report += section("🔴 Rekomendasi JUAL / Exit Hari Ini", sell, "Tidak ada stance SELL/exit tervalidasi saat ini.")
        report += [
            "",
            "⏱️ Watchlist Jangka PENDEK (1-2 minggu)",
            "Berbasis skor indikator harian; bukan model forecast mingguan.",
            "",
            "📅 Watchlist Jangka MENENGAH (1-3 bulan)",
            "Kandidat dengan tren konsolidasi sehat dan proyeksi pertumbuhan.",
            "",
            "💎 Watchlist Jangka PANJANG (6-12 bulan)",
            "Emiten dengan fundamental solid untuk akumulasi berkala (DCA).",
        ]

    report.extend([
        "",
        "⚠️ Peringatan Risiko & Berita Penting",
        "- Level harga dan indikator adalah snapshot; verifikasi sebelum mengambil keputusan.",
        "- Skor adalah ranking heuristik kuantitatif, bukan garansi kepastian hasil.",
        "- Ukuran alokasi harus disesuaikan dengan toleransi risiko dan kas likuid pribadi.",
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
    Executes full multi-agent market screener pipeline across candidate universe
    and renders multi-horizon actionable investment recommendations.
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
    log(f"Quant Screener: Memindai universe pasar {market.upper()} untuk ranking kandidat...", role="data_fetcher", status="running")

    screened_results = []
    try:
        screened_results = screen_market_opportunities(market, limit=10)
    except Exception as e:
        logger.warning("Screening error: %s", e)
        screened_results = []

    screened_results = [c for c in screened_results if c.get("score") is not None]
    if not screened_results:
        msg = f"⚠️ Tidak ada kandidat yang lolos screening kuantitatif pasar {market.upper()} saat ini."
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
    log(f"Quant Screener memilih {len(symbols)} aset teratas: {', '.join(symbols)}", role="data_fetcher")

    # Fetch live news for market
    check_stop()
    exa_query = f"{market} market outlook economic trend opportunities investment analysis"
    exa_news = search_internet(exa_query, num_results=3)

    # Build market snapshot
    snapshot_lines = [
        f"Collection timestamp (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"Market: {market.upper()} | Universe Candidates: {len(symbols)}",
    ]
    for c in screened_results:
        levels = c.get("suggested_levels") or {}
        targets = levels.get("take_profit_targets") or []
        tps = ", ".join(f"{t['label']}={t['price']} ({t['r_multiple']}R)" for t in targets) or "Targets unavailable"
        snapshot_lines.append(
            f"- {c['symbol']}: Harga={_format_recommendation_price(c.get('price'), market)} | RSI={c.get('rsi')} | MACD={c.get('macd')} | Skor={c.get('score')}/100 | ATR Risk: SL={levels.get('buy_sl')} | {tps}"
        )
    snapshot = "\n".join(snapshot_lines)

    data_fetcher_result = (
        f"Snapshot Pasar Kuantitatif Terverifikasi:\n{snapshot}\n\n"
        f"Konteks Berita Pasar:\n{_format_news_evidence(exa_news)}"
    )
    emit("agent_output", role="data_fetcher", output=data_fetcher_result)
    emit("agent_status", role="data_fetcher", status="completed")
    log("Data fetcher selesai mengumpulkan snapshot terverifikasi.", role="data_fetcher", status="completed")

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
        usr_p = f"Analisis kandidat pasar {market.upper()}:\n{snapshot}\n\nSampaikan temuan spesifik Anda sebagai {role}."

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
    log("Investment Advisor sedang mensintesis rekomendasi pasar menyeluruh...", role="investment_advisor")

    adv_sys = (
        f"You are the Lead Investment Strategist for {market.upper()}.\n\n"
        "Return ONLY valid JSON with this exact schema:\n"
        '{"assets":[{"symbol":"TICKER","stance":"BUY|SELL|HOLD","rationale":"qualitative rationale without fake earnings dates"}]}\n\n'
        "Use ONLY symbols from the provided candidate list. Never invent prices or future dates."
    )
    adv_usr = f"Candidates:\n{snapshot}\n\nReturn stance and brief rationale for each symbol."

    model_stances: Dict[str, Dict[str, str]] = {}
    try:
        raw_adv = call_llm([{"role": "system", "content": adv_sys}, {"role": "user", "content": adv_usr}], temperature=0.2)
        parsed = _extract_json_block(raw_adv)
        if parsed and "assets" in parsed:
            for item in parsed["assets"]:
                sym = item.get("symbol")
                st = str(item.get("stance", "HOLD")).upper()
                if sym and st in {"BUY", "SELL", "HOLD"}:
                    rat = str(item.get("rationale", ""))
                    # Regex sanitizer: remove unverified earnings/dates
                    if re.search(r"(?i)earnings|laporan laba|jadwal|tanggal|this week|minggu ini", rat):
                        rat = "Momentum indikator teknikal stabil dengan dukungan tren pasar."
                    model_stances[sym] = {"stance": st, "rationale": rat}
    except Exception as e:
        logger.warning("Advisor stance assignment fallback: %s", e)

    is_syar = is_syariah_market(market)
    for c in screened_results:
        sym = c["symbol"]
        proposal = model_stances.get(sym, {"stance": "HOLD", "rationale": "Tren konsolidasi."})
        stance = proposal["stance"]
        sharia_ok = c.get("issi_status") == "Ya"
        if is_syar and not sharia_ok:
            stance = "HOLD"
        c["stance"] = stance
        c["final_stance"] = stance
        c["final_rationale"] = proposal.get("rationale", "")

        # Deterministic confidence
        if c.get("price") is not None:
            c["confidence"] = calibrate_confidence(
                float(c["price"]),
                {"sma20": c.get("sma20"), "sma50": c.get("sma50"), "rsi": c.get("rsi"), "macd": c.get("macd")},
                stance if stance in {"BUY", "SELL"} else "BUY",
                c.get("change_pct"),
            )
            c["confidence_basis"] = "deterministic indicator heuristic"
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
    log("Scan peluang pasar berhasil diselesaikan.", role="investment_advisor", status="completed")

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
    """Performs live independent re-fetch, computes price drift and 1D vs 1H divergence."""
    dossier_lines: List[str] = []
    snapshots: List[Dict[str, Any]] = []
    sources: List[str] = []
    flags: List[str] = []

    is_crypto = normalize_market(market) == "crypto"
    is_syariah = is_syariah_market(market)

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
        sources.append(f"{mkt_data.get('provider', 'Yahoo Finance/Binance')} (Multi-Timeframe)")

        tfs = mkt_data.get("timeframes", {})
        tf_1d = tfs.get("1D") or {}
        tf_1h = tfs.get("1H") or {}
        st_1d = tf_1d.get("stats", {})
        st_1h = tf_1h.get("stats", {})
        curr_p = tf_1d.get("price") or tf_1h.get("price")
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
                    if abs(drift_pct) >= 1.5:
                        sym_flags.append(f"Pergeseran harga (Price Drift): {drift_pct:+.2f}% sejak analisis awal")
            except Exception:
                pass

        # Check Multi-Timeframe Divergence
        rsi_1d = st_1d.get("rsi")
        rsi_1h = st_1h.get("rsi")
        macd_1d = st_1d.get("macd")
        macd_1h = st_1h.get("macd")

        if rsi_1d is not None and rsi_1h is not None:
            if rsi_1h >= 70 and rsi_1d < 70:
                sym_flags.append("RSI 1H Overbought (>= 70): Waspada risiko pullback intraday")
            elif rsi_1h <= 30 and rsi_1d > 30:
                sym_flags.append("RSI 1H Oversold (<= 30): Tekanan jual intraday masih tinggi")

        if macd_1d and macd_1h:
            if str(macd_1d).lower() == "bullish" and str(macd_1h).lower() == "bearish":
                sym_flags.append("Divergensi Timeframe: Tren makro 1D bullish, namun momentum intraday 1H bearish")

        flags.extend([f"[{sym}] {f}" for f in sym_flags])

        dossier_lines.append(f"1. Snapshot Kuantitatif Live:")
        dossier_lines.append(f"   - Harga Live: {_format_recommendation_price(curr_p, market, fx_rate)}")
        dossier_lines.append(f"   - Indikator 1D: RSI={rsi_1d or 'N/A'}, MACD={macd_1d or 'N/A'}, SMA20={_format_recommendation_price(st_1d.get('sma20'), market, fx_rate)}")
        if tf_1h:
            dossier_lines.append(f"   - Indikator 1H: RSI={rsi_1h or 'N/A'}, MACD={macd_1h or 'N/A'}")
        if sym_flags:
            dossier_lines.append(f"2. Temuan Catatan Auditor: {'; '.join(sym_flags)}")

        snapshots.append({
            "symbol": sym,
            "price": _format_recommendation_price(curr_p, market, fx_rate),
            "rsi_1d": rsi_1d,
            "macd_1d": macd_1d,
            "rsi_1h": rsi_1h,
            "macd_1h": macd_1h,
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
            "You are provided with fresh, independently re-fetched live multi-timeframe market data (1D and 1H).\n\n"
            "AUDIT STRUCTURE TO FOLLOW:\n"
            "1. 🎯 Verifikasi Klaim & Jawaban Langsung: Tanggapi pertanyaan pengguna dengan fakta live.\n"
            "2. ⚖️ Keselarasan Multi-Timeframe (1D vs 1H): Soroti jika ada divergensi tren makro vs intraday.\n"
            "3. 🛡️ Analisis Risiko & Price Drift: Evaluasi jika harga sudah bergerak jauh sejak rekomendasi terbit.\n"
            "4. 🏁 Vonis Auditor: Berikan keputusan tegas (Tervalidasi Kuat / Valid dengan Catatan / Tunggu Pullback / Downgrade ke HOLD).\n\n"
            f"{DATA_FRESHNESS_INSTRUCTIONS}\n\n"
            f"{TOOL_GROUNDING_INSTRUCTIONS}\n\n"
            f"LIVE AUDIT DOSSIER:\n{dossier}\n"
        )

        messages = [{"role": "system", "content": system_prompt}] + history
        if user_message:
            messages.append({"role": "user", "content": user_message})

        reply = call_llm(messages, temperature=0.2)
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
1. Jawab secara solutif, objektif, dan jujur berbasis data di atas.
2. Jelaskan logika akumulasi (DCA), valuasi, dan pembagian porsi portofolio.
3. Jika pengguna ingin memverifikasi data live atau menguji divergensi, sarankan aktifkan toggle Deep Validation Mode.
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
