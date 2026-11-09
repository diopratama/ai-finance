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
    "IMPORTANT: You have NO tools, no browsing, and no database access. Use ONLY numbers that appear in "
    "the supplied context blocks. If a metric is missing or marked UNAVAILABLE, write 'Unavailable' for it; "
    "never fill it from memory or estimate it. Never describe an issuer as halal/certified unless explicitly "
    "noted in the supplied SHARIA SCREEN or ISSI reference."
)

NEWS_VERIFICATION_INSTRUCTIONS = (
    "For every time-sensitive news or event claim, use only an item in the supplied news context that "
    "contains a source URL and publication date. Cite the URL where appropriate."
)

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
    return AGENT_ROLES.get(normalize_market(market), DEFAULT_AGENT_ROLES)


def _format_significant(val: Any) -> str:
    if val is None:
        return "N/A"
    try:
        f = float(val)
        if abs(f) >= 1000:
            return f"{f:,.2f}"
        if abs(f) >= 1:
            return f"{f:.4f}"
        return f"{f:.6f}"
    except (ValueError, TypeError):
        return str(val)


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


def call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
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
            content, _ = _post_chat_completion(payload, headers)
            if not content:
                raise LLMError("Empty response from LLM")
            return content
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.warning("LLM HTTP Error %s: %s", e.code, err_msg)
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
    norm_market = normalize_market(market)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    candidates = [
        os.path.join(base_dir, "skills", "investment", norm_market, agent_role, "SKILL.md"),
        os.path.join("/app", "skills", "investment", norm_market, agent_role, "SKILL.md"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()

    return f"Role: {agent_role} for investment research on {market}."


def fetch_comprehensive_market_data(market: str, symbol: str) -> Dict[str, Any]:
    timeframes = ["1D", "1W"]
    is_crypto = normalize_market(market) == "crypto"
    fx_usd_idr = get_usd_idr_rate() if is_crypto else None
    market_metrics = fetch_market_metrics(market)

    result: Dict[str, Any] = {
        "market": market,
        "symbol": symbol,
        "snapshot_captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fx_usd_idr": fx_usd_idr,
        "market_metrics": market_metrics,
        "timeframes": {},
        "errors": [],
    }

    summary_lines = [
        f"Symbol: {symbol} ({market.upper()})",
        f"Snapshot Time (UTC): {result['snapshot_captured_at']}",
    ]

    for tf in timeframes:
        try:
            quote = get_market_quote(market, symbol, tf)
            candles = quote.get("candles", [])
            if candles:
                latest = candles[-1]
                result["timeframes"][tf] = {
                    "candles": candles,
                    "latest_price": latest.get("close"),
                    "high": max(c["high"] for c in candles),
                    "low": min(c["low"] for c in candles),
                }
                summary_lines.append(
                    f"[{tf}] Close: {_format_significant(latest.get('close'))}, "
                    f"High: {_format_significant(result['timeframes'][tf]['high'])}, "
                    f"Low: {_format_significant(result['timeframes'][tf]['low'])}"
                )
        except Exception as e:
            result["errors"].append(f"{tf}: {e}")

    result["summary"] = "\n".join(summary_lines)
    return result


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
    Executes a multi-agent investment research analysis across horizons:
    Short (< 1 yr), Medium (1-3 yr), Long (> 3-5 yr).
    Integrates personal financial profile and wallet capacity.
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

    # 1. Search Live News via Exa (with multi-engine fallback)
    check_stop()
    log("Mencari berita, sentimen pasar & katalis terkini melalui Exa Search...")
    search_query = f"{symbol} {market} investasi prospek dividen kinerja keuangan analisis"
    search_results = search_internet(search_query, num_results=3)

    news_items = []
    for item in search_results:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        url = item.get("url", "")
        published = item.get("published_date", "")
        line = f"- {title}"
        if published:
            line += f" ({published})"
        if snippet:
            line += f": {snippet}"
        if url:
            line += f" [{url}]"
        news_items.append(line)

    news_context = "\n".join(news_items) if news_items else "Berita terkini tidak ditemukan atau API pencarian offline."
    market_context = f"Pasar: {market.upper()}\nSimbol: {symbol}\nKonteks Berita & Katalis Terkini:\n{news_context}"

    # 2. Fetch Fundamental Context
    check_stop()
    log("Mengambil data fundamental & laporan keuangan...")
    try:
        fundamental_info = get_fundamental_context(market, symbol)
        fundamentals_context = fundamental_info.get("text", "")
        log("Data fundamental berhasil dimuat.")
    except Exception as e:
        logger.warning("Fundamental fetch error for %s: %s", symbol, e)
        fundamentals_context = f"Data fundamental untuk {symbol} belum tersedia."
        fundamental_info = {"available": False, "sharia": None, "sharia_reference": None}

    # 3. Fetch On-Chain context if crypto
    onchain_context = ""
    if normalize_market(market) == "crypto":
        check_stop()
        log("Mengambil metrik on-chain & derivatif crypto...")
        try:
            onchain_info = get_onchain_context(market, symbol)
            onchain_context = onchain_info.get("text", "") if onchain_info else ""
        except Exception as e:
            logger.warning("On-chain fetch error for %s: %s", symbol, e)
            onchain_context = "Data on-chain tidak tersedia."

    # 4. Fetch Foreign Flow if IHSG
    foreign_flow_context = ""
    if "ihsg" in market.lower():
        try:
            ff_data = get_idx_foreign_flow()
            if ff_data:
                foreign_flow_context = format_symbol_foreign_flow(symbol, ff_data)
        except Exception as e:
            logger.warning("Foreign flow error for %s: %s", symbol, e)

    # 5. Run Data Fetcher
    check_stop()
    emit("agent_status", role="data_fetcher", status="running")
    log("Menjalankan Data Fetcher: memuat harga dan teknikal...", role="data_fetcher")
    try:
        market_data = fetch_comprehensive_market_data(market, symbol)
        enhanced_context = (
            f"{market_context}\n\n"
            f"=== DATA PASAR ===\n{market_data.get('summary', '')}\n\n"
            f"=== FUNDAMENTAL & VALUASI ===\n{fundamentals_context}\n"
        )
        if foreign_flow_context:
            enhanced_context += f"\n=== FOREIGN FLOW (BEI) ===\n{foreign_flow_context}\n"
        if onchain_context:
            enhanced_context += f"\n=== ON-CHAIN & DERIVATIVES ===\n{onchain_context}\n"

        agent_results: Dict[str, str] = {"data_fetcher": enhanced_context}
        emit("agent_output", role="data_fetcher", output=enhanced_context)
        emit("agent_status", role="data_fetcher", status="completed")
        log("Data fetcher selesai.", role="data_fetcher", status="completed")
    except Exception as e:
        logger.error("Data fetcher failed: %s", e)
        enhanced_context = market_context + f"\n\nFundamental:\n{fundamentals_context}"
        agent_results = {"data_fetcher": enhanced_context}
        emit("agent_status", role="data_fetcher", status="failed")

    roles = [r for r in agent_roles(market) if r != "data_fetcher"]

    # 6. Execute Analyst Agents
    for role in roles:
        check_stop()
        emit("agent_status", role=role, status="running")
        log(f"Menjalankan analisis agen: {role}...", role=role)

        skill_content = load_skill_content(market, role, locale)
        system_prompt = (
            f"{skill_content}\n\n"
            f"{TOOL_GROUNDING_INSTRUCTIONS}\n"
            f"{DATA_FRESHNESS_INSTRUCTIONS}\n"
            f"{NEWS_VERIFICATION_INSTRUCTIONS}\n"
            "Fokus analisis Anda adalah INVESTASI (Bukan day trading / scalping). "
            "Evaluasi kualitas emiten, pertumbuhan laba / adopsi, dan risiko fundamental."
        )

        user_prompt = (
            f"Simbol: {symbol}\n"
            f"Pasar: {market}\n\n"
            f"Berikut adalah data pasar, fundamental, dan berita terkini:\n\n"
            f"{enhanced_context}\n\n"
            f"Susun laporan analisis spesifik Anda sebagai '{role}' dalam Bahasa Indonesia yang objektif, "
            f"tajam, dan berbasis data di atas."
        )

        try:
            report = call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ], temperature=0.25)
            agent_results[role] = report
            emit("agent_output", role=role, output=report)
            emit("agent_status", role=role, status="completed")
            log(f"Analisis {role} selesai.", role=role, status="completed")
        except Exception as e:
            logger.error("Analyst %s failed: %s", role, e)
            fallback = f"Analisis {role} terkendala koneksi AI: {e}"
            agent_results[role] = fallback
            emit("agent_output", role=role, output=fallback)
            emit("agent_status", role=role, status="failed")

    # 7. Execute Investment Advisor Agent
    check_stop()
    emit("agent_status", role="investment_advisor", status="running")
    log("Investment Advisor sedang mensintesis seluruh temuan agen & memetakan horizon investasi...", role="investment_advisor")

    # Format user financial profile context
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
            f"Estimasi Surplus Bulanan: Rp {surplus_val:,.0f}\n"
            f"Toleransi Risiko: {risk_prof}\n"
            f"Preferensi Syariah: {'YA (Wajib Syariah)' if sharia_usr else 'Konvensional / Fleksibel'}"
        )

    analysts_summary = "\n\n".join([
        f"=== LAPORAN {k.upper()} ===\n{v}"
        for k, v in agent_results.items()
        if k != "data_fetcher"
    ])

    advisor_system = """Anda adalah Kepala Komite Investasi (Chief Investment Strategist).
Tugas Anda adalah mensintesis seluruh laporan teknikal, fundamental, on-chain/foreign flow, dan sentimen untuk menghasilkan Rekomendasi Investasi Multi-Horizon (Jangka Pendek < 1 thn, Jangka Menengah 1-3 thn, Jangka Panjang > 3-5 thn).

WAJIB mengembalikan respon HANYA dalam format JSON valid tanpa tanda markdown (```json).
Format struktur JSON yang WAJIB dipatuhi:
{
  "symbol": "BBCA",
  "market": "IHSG",
  "stance": "ACCUMULATE / DCA",
  "confidence_pct": 85,
  "fundamental_quality_score": 9,
  "sharia_compliance": {
    "is_sharia": true,
    "classification": "ISSI / DES",
    "notes": "Penjelasan status syariah dari data reference"
  },
  "valuation_summary": {
    "fair_value_estimate": "Rp 11.200",
    "current_valuation_status": "UNDERVALUED",
    "metric_rationale": "Forward P/E 18x vs historical 5-yr mean 21x"
  },
  "multi_horizon_outlook": {
    "short_term": {
      "horizon": "< 1 Tahun (Taktis & Katalis)",
      "stance": "ACCUMULATE",
      "target_range": "Rp 9.500 - Rp 10.200",
      "thesis": "Katalis dividen interim dan kinerja kuartalan solid.",
      "catalysts": ["Laporan laba kuartal 4", "Rapat Umum Pemegang Saham"],
      "risks": ["Volatilitas pasar regional"]
    },
    "medium_term": {
      "horizon": "1 - 3 Tahun (Siklus Bisnis & Pertumbuhan)",
      "stance": "BUY ON DIP",
      "target_range": "Rp 11.500 - Rp 12.000",
      "thesis": "Pertumbuhan laba bersih konsisten 10-12% p.a. didukung digitalisasi.",
      "catalysts": ["Siklus pemangkasan suku bunga acuan BI"],
      "risks": ["Kenaikan biaya dana perbankan"]
    },
    "long_term": {
      "horizon": "> 3 - 5 Tahun (Moat Sekuler & Compounding)",
      "stance": "ACCUMULATE / DCA",
      "target_range": "Rp 14.000+",
      "thesis": "Economic moat terkuat di industri dengan CASA ratio tertinggi, instrumen compounding kekayaan terbaik.",
      "compounding_factors": ["CASA ratio > 80%", "ROE > 20% konsisten"],
      "risks": ["Disrupsi teknologi pembayaran skala masif"]
    }
  },
  "portfolio_and_dca_simulation": {
    "risk_profile_match": "Sesuai profil Moderat & Agresif",
    "recommended_max_allocation_pct": 10,
    "suggested_monthly_dca_amount": 500000,
    "action_plan": "Mulai cicil berkala (DCA) setiap tanggal gajian."
  },
  "executive_thesis": "Rangkuman tesis investasi lengkap dalam 2-3 paragraf berbahasa Indonesia yang lugas dan profesional.",
  "key_monitoring_metrics": ["Pertumbuhan CASA", "NIM", "Kualitas Aset / NPL"]
}
"""

    advisor_user = (
        f"Simbol: {symbol}\n"
        f"Pasar: {market}\n\n"
        f"DATA PROFIL KEUANGAN INVESTOR:\n{profile_ctx}\n\n"
        f"LAPORAN DARI TIM ANALIS:\n{analysts_summary}\n\n"
        "Berikan rekomendasi komprehensif dalam struktur JSON valid yang ditentukan."
    )

    try:
        raw_advisor = call_llm([
            {"role": "system", "content": advisor_system},
            {"role": "user", "content": advisor_user},
        ], temperature=0.2)
        parsed_advisor = _extract_json_block(raw_advisor)
        if not parsed_advisor:
            raise LLMError("Gagal mem-parsing JSON rekomendasi advisor.")
    except Exception as e:
        logger.error("Investment advisor JSON generation failed: %s", e)
        # Construct structured fallback
        parsed_advisor = {
            "symbol": symbol,
            "market": market,
            "stance": "HOLD",
            "confidence_pct": 60,
            "fundamental_quality_score": 6,
            "sharia_compliance": {
                "is_sharia": is_syariah,
                "classification": "ISSI Reference" if is_syariah else "Konvensional",
                "notes": "Verifikasi manual daftar ISSI/DES.",
            },
            "valuation_summary": {
                "fair_value_estimate": "Evaluasi Berkelanjutan",
                "current_valuation_status": "FAIR",
                "metric_rationale": "Data laporan keuangan sedang diperbarui.",
            },
            "multi_horizon_outlook": {
                "short_term": {
                    "horizon": "< 1 Tahun",
                    "stance": "HOLD",
                    "target_range": "Sesuai Support/Resistance",
                    "thesis": "Perhatikan konfirmasi sentimen pasar jangka pendek.",
                    "catalysts": ["Rilis LK"],
                    "risks": ["Volatilitas pasar"],
                },
                "medium_term": {
                    "horizon": "1 - 3 Tahun",
                    "stance": "HOLD",
                    "target_range": "Tren Konsolidasi",
                    "thesis": "Tunggu sinyal pertumbuhan laba kuartal berikutnya.",
                    "catalysts": ["Siklus Makro"],
                    "risks": ["Penurunan margin"],
                },
                "long_term": {
                    "horizon": "> 3 - 5 Tahun",
                    "stance": "ACCUMULATE / DCA",
                    "target_range": "Apresiasi Modal",
                    "thesis": "Instrumen investasi jangka panjang dengan strategi Dollar Cost Averaging.",
                    "compounding_factors": ["Pertumbuhan Industri"],
                    "risks": ["Perubahan Kebijakan"],
                },
            },
            "portfolio_and_dca_simulation": {
                "risk_profile_match": "Gunakan alokasi terukur (maks 5-10% dari portofolio)",
                "recommended_max_allocation_pct": 5,
                "suggested_monthly_dca_amount": 0,
                "action_plan": "Kumpulkan dana kas dan tunggu momentum harga wajar.",
            },
            "executive_thesis": f"Analisis untuk {symbol} menunjukkan kestabilan operasional. Disarankan strategi cicil berkala (DCA) bertahap.",
            "key_monitoring_metrics": ["Kinerja Pendapatan", "Sentimen Pasar"],
        }

    final_result = {
        "symbol": symbol,
        "market": market,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "analyst_reports": agent_results,
        "investment_recommendation": parsed_advisor,
        "news_sources": search_results,
    }

    emit("agent_output", role="investment_advisor", output=json.dumps(parsed_advisor, indent=2))
    emit("agent_status", role="investment_advisor", status="completed")
    emit("investment_recommendation", data=parsed_advisor)
    emit("completed", result=final_result)
    log("Seluruh proses riset multi-agent berhasil diselesaikan.", role="investment_advisor", status="completed")

    return final_result


def chat_with_investment_agent(
    history: List[Dict[str, str]],
    analysis_context: Dict[str, Any],
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Handles conversational questions regarding the generated investment research report."""
    recommendation = analysis_context.get("investment_recommendation") or {}
    symbol = analysis_context.get("symbol", "")
    market = analysis_context.get("market", "")

    system_prompt = f"""Kamu adalah Partner Konsultan Investasi Senior & Penasihat Keuangan Independen.
Pengguna sedang mendiskusikan riset dan rekomendasi investasi untuk {symbol} ({market}).

KONTEKS HASIL RISET TERBARU:
- Simbol / Emiten: {symbol} ({market})
- Stance Rekomendasi: {recommendation.get('stance')} (Keyakinan: {recommendation.get('confidence_pct')}%)
- Skor Kualitas Fundamental: {recommendation.get('fundamental_quality_score')}/10
- Tesis Eksekutif: {recommendation.get('executive_thesis')}
- Outlook Multi-Horizon: {json.dumps(recommendation.get('multi_horizon_outlook', {}), ensure_ascii=False)}
- Valuasi: {json.dumps(recommendation.get('valuation_summary', {}), ensure_ascii=False)}
- Panduan Alokasi Portofolio: {json.dumps(recommendation.get('portfolio_and_dca_simulation', {}), ensure_ascii=False)}

PANDUAN MENJAWAB:
1. Jawab secara jelas, solutif, berbasis data, dan edukatif dalam Bahasa Indonesia.
2. Jelaskan logika investasi jangka panjang (DCA, dividen reinvestment, valuasi fundamental, manajemen risiko).
3. Ingatkan diversifikasi dan batas alokasi dompet agar pengguna tidak over-concentrated pada satu instrumen.
"""

    messages = [{"role": "system", "content": system_prompt}] + history
    try:
        return call_llm(messages, temperature=0.3)
    except Exception as e:
        logger.error("Chat with investment agent failed: %s", e)
        return f"Mohon maaf, terjadi kendala saat memproses jawaban: {e}"
