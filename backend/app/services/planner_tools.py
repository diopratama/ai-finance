import json
import logging
from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import InvestmentAnalysisHistory, SessionLocal
from app.investment_ai.fundamental_data import get_fundamental_context
from app.investment_ai.market_data import (
    calculate_investment_zones,
    fetch_long_term_market_metrics,
    get_market_quote,
)
from app.services.web_search_service import (
    format_search_results_for_prompt,
    search_internet,
)

logger = logging.getLogger(__name__)

_CRYPTO_HINTS = {
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "ADA",
    "AVAX",
    "LINK",
    "DOT",
    "SUI",
    "ARB",
    "OP",
    "TON",
    "NEAR",
    "ATOM",
    "UNI",
    "AAVE",
}

_US_ETF_HINTS = {
    "SPY",
    "QQQ",
    "VOO",
    "VTI",
    "SCHD",
    "IVV",
    "VEA",
    "VWO",
    "BND",
    "TLT",
    "GLD",
    "SGOV",
    "VXUS",
    "SPUS",
    "HLAL",
}

PLANNER_TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_internet_live",
            "description": (
                "Mencari berita terbaru, data makro, kurs, harga emas, suku bunga BI/Fed, pajak, atau "
                "informasi keuangan terkini di internet ketika data belum ada di konteks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Kata kunci pencarian finansial yang spesifik (bahasa Indonesia atau Inggris).",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_asset_market_and_fundamentals",
            "description": (
                "Mengambil data harga pasar terkini, metrik risiko jangka panjang (CAGR 1Y/3Y/5Y, Max Drawdown, "
                "posisi siklus SMA), metrik fundamental (FMP DCF Fair Value, Margin of Safety, Piotroski F-Score, "
                "ROIC, ROE, Dividend Yield, atau MCap/FDV & TVL untuk crypto), dan 3 Zona Harga Investasi."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Simbol aset, misal: BBCA.JK, TLKM.JK, AAPL, MSFT, SPY, BTC/USDT, ETH/USDT.",
                    },
                    "market": {
                        "type": "string",
                        "enum": ["auto", "ihsg", "ihsg_syariah", "us_stock", "us_etf", "crypto"],
                        "description": "Jenis pasar aset. Gunakan 'auto' jika ingin deteksi otomatis dari simbol.",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_investment_analysis_detail",
            "description": (
                "Mengambil detail lengkap (laporan penuh seluruh agen swarm atau daftar kandidat screener) "
                "dari salah satu riwayat analisis investasi user berdasarkan run_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "ID run analisis swarm (misal dari daftar 5 analisis terakhir).",
                    }
                },
                "required": ["run_id"],
            },
        },
    },
]


def _safe_json_loads(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _truncate(text: Optional[str], limit: int = 420) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _format_zones_summary(zones: Any) -> str:
    if not isinstance(zones, dict) or not zones:
        return "-"
    acc = zones.get("accumulation_zone") or {}
    fv = zones.get("fair_value_target") or {}
    inv = zones.get("thesis_invalidation") or {}
    parts: List[str] = []
    if acc:
        parts.append(f"Zona Akumulasi: {acc.get('low', '-')}–{acc.get('high', '-')}")
    if fv:
        mos = fv.get("margin_of_safety_pct")
        mos_str = f" (MoS {mos:+.1f}%)" if isinstance(mos, (int, float)) else ""
        parts.append(f"Fair Value Target: {fv.get('target', fv.get('dcf_fair_value', '-'))}{mos_str}")
    if inv:
        parts.append(f"Invalidasi Tesis: {_truncate(inv.get('trigger_summary') or inv.get('fundamental_triggers'), 140)}")
    return " | ".join(parts) if parts else "-"


def _format_single_analysis_entry(row: InvestmentAnalysisHistory) -> str:
    res = _safe_json_loads(row.result_json)
    dt_str = (
        row.created_at.replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if row.created_at
        else "-"
    )
    display_sym = "Screener Multi-Aset" if row.analysis_type == "recommend" else (row.symbol or "-")
    header = (
        f"• [run_id={row.run_id}] {dt_str} | Market={row.market} | Tipe={row.analysis_type} | "
        f"Horizon={row.investment_horizon} | Simbol={display_sym}"
    )

    if row.analysis_type == "recommend":
        candidates = res.get("top_candidates") or res.get("candidates") or []
        lines = [header]
        if isinstance(candidates, list) and candidates:
            for idx, c in enumerate(candidates[:3], 1):
                if not isinstance(c, dict):
                    continue
                z_str = _format_zones_summary(c.get("investment_zones"))
                lines.append(
                    f"  Kandidat #{idx}: {c.get('symbol')} | Skor={c.get('score')} "
                    f"(Fund={c.get('fundamental_score')}, Siklus={c.get('cycle_score')}) | "
                    f"Stance={c.get('stance', '-')} | {z_str}"
                )
        macro = res.get("macro_regime") or {}
        if isinstance(macro, dict) and macro:
            lines.append(
                f"  Macro Regime: USD/IDR={macro.get('usd_idr_rate', '-')}, "
                f"US10Y={macro.get('us10y_yield_pct', '-')}% ({macro.get('interest_rate_regime', '-')})"
            )
        if res.get("report"):
            lines.append(f"  Ringkasan Laporan: {_truncate(res.get('report'), 450)}")
        return "\n".join(lines)

    rec = res.get("recommendation") or {}
    if not isinstance(rec, dict):
        rec = {}
    stance = rec.get("stance") or row.decision or "-"
    conf = rec.get("confidence_pct") if rec.get("confidence_pct") is not None else row.confidence
    price = res.get("current_price") or rec.get("current_price") or (rec.get("investment_zones") or {}).get("reference_price")

    lines = [
        header,
        f"  Keputusan: {stance} (Confidence={conf}%) | Harga saat analisis: {price}",
        f"  3 Zona Investasi: {_format_zones_summary(rec.get('investment_zones'))}",
    ]

    fund = res.get("fundamental_metrics") or rec.get("fundamental_metrics") or {}
    if isinstance(fund, dict) and fund:
        f_parts = []
        for k, label in (
            ("dcf_fair_value", "DCF"),
            ("margin_of_safety_pct", "MoS%"),
            ("piotroski_f_score", "F-Score"),
            ("altman_z_score", "Z-Score"),
            ("roic", "ROIC"),
            ("roe", "ROE"),
            ("trailing_pe", "P/E"),
            ("dividend_yield", "DivYield%"),
            ("mcap_to_fdv_ratio", "MCap/FDV"),
        ):
            if fund.get(k) is not None:
                f_parts.append(f"{label}={fund[k]}")
        if f_parts:
            lines.append(f"  Fundamental: {', '.join(f_parts)}")

    lt = res.get("long_term_metrics") or rec.get("long_term_metrics") or {}
    if isinstance(lt, dict) and lt:
        lines.append(
            f"  Risiko & Siklus Jangka Panjang: CAGR 1Y={lt.get('cagr_1y_pct', '-')}% | "
            f"3Y={lt.get('cagr_3y_pct', '-')}% | 5Y={lt.get('cagr_5y_pct', '-')}% | "
            f"MaxDD={lt.get('max_drawdown_pct', '-')}% | Siklus={lt.get('cycle_position', '-')}"
        )

    dca = rec.get("dca_simulation") or res.get("dca_simulation") or {}
    if isinstance(dca, dict) and dca.get("horizons"):
        h_str = ", ".join(
            f"{h.get('years')}Y: nilai≈{h.get('projected_value')} (dividen/thn≈{h.get('annual_dividend_income')})"
            for h in (dca.get("horizons") or [])[:3]
            if isinstance(h, dict)
        )
        if h_str:
            lines.append(f"  Simulasi DCA ({dca.get('currency', '')}): {h_str}")

    conc = rec.get("portfolio_concentration") or res.get("portfolio_concentration") or {}
    if isinstance(conc, dict) and conc:
        lines.append(
            f"  Konsentrasi Portofolio User: Status={conc.get('concentration_status', '-')} | "
            f"Bobot sekarang={conc.get('current_exposure_pct', '-')}% | "
            f"Saran={_truncate(conc.get('allocation_advice') or conc.get('warning'), 180)}"
        )

    reports = res.get("agent_reports") or {}
    if isinstance(reports, dict) and reports:
        rep_bits = [
            f"{k}: {_truncate(v, 220)}"
            for k, v in list(reports.items())[:4]
            if isinstance(v, str) and v.strip()
        ]
        if rep_bits:
            lines.append("  Ringkasan Agen: " + " || ".join(rep_bits))
    elif row.report_preview:
        lines.append(f"  Preview Laporan: {_truncate(row.report_preview, 350)}")

    return "\n".join(lines)


def build_recent_swarm_analyses_context(
    db: Session,
    user_id: str,
    limit: int = 5,
) -> Dict[str, Any]:
    """Loads structured summaries of the user's latest completed swarm investment analyses."""
    rows = (
        db.query(InvestmentAnalysisHistory)
        .filter(
            InvestmentAnalysisHistory.user_id == user_id,
            InvestmentAnalysisHistory.status == "completed",
        )
        .order_by(desc(InvestmentAnalysisHistory.created_at))
        .limit(limit)
        .all()
    )
    if not rows:
        return {
            "count": 0,
            "summary_text": "  • Belum ada riwayat analisis Swarm Agent yang tersimpan.",
            "runs": [],
        }

    formatted = [_format_single_analysis_entry(r) for r in rows]
    runs_meta = [
        {
            "run_id": r.run_id,
            "symbol": r.symbol,
            "market": r.market,
            "analysis_type": r.analysis_type,
            "decision": r.decision,
        }
        for r in rows
    ]
    return {
        "count": len(rows),
        "summary_text": "\n\n".join(formatted),
        "runs": runs_meta,
    }


def _infer_market_from_symbol(symbol: str, requested_market: str = "auto") -> Tuple[str, str]:
    clean = (symbol or "").strip().upper()
    if requested_market and requested_market != "auto":
        return requested_market, clean

    if clean.endswith(".JK"):
        return "ihsg", clean
    if "/USDT" in clean or "-USD" in clean or clean in _CRYPTO_HINTS:
        norm_sym = clean if "/" in clean or "-" in clean else f"{clean}/USDT"
        return "crypto", norm_sym
    if clean in _US_ETF_HINTS:
        return "us_etf", clean
    if clean.isalpha() and len(clean) == 4 and clean in {
        "BBCA", "BBRI", "BMRI", "BBNI", "TLKM", "ASII", "UNVR", "ICBP", "INDF",
        "ADRO", "PTBA", "ITMG", "ANTM", "INCO", "MDKA", "BRIS", "GOTO", "AMRT",
    }:
        return "ihsg", f"{clean}.JK"
    return "us_stock", clean


def _tool_search_internet(query: str) -> Tuple[str, str]:
    clean_q = (query or "").strip()
    status_msg = f"Mencari informasi terbaru di internet: \"{clean_q[:45]}\"..."
    results = search_internet(clean_q, max_results=5)
    formatted = format_search_results_for_prompt(results)
    return status_msg, formatted


def _tool_fetch_asset_data(symbol: str, market: str = "auto") -> Tuple[str, str]:
    resolved_market, resolved_symbol = _infer_market_from_symbol(symbol, market)
    status_msg = f"Mengambil data harga, siklus & fundamental {resolved_symbol} ({resolved_market})..."

    quote = get_market_quote(resolved_market, resolved_symbol, timeframe="1D")
    lt_metrics = fetch_long_term_market_metrics(resolved_market, resolved_symbol)
    fund_ctx = get_fundamental_context(resolved_market, resolved_symbol)

    price = quote.get("price") or 0.0
    stats = quote.get("indicators") or {}
    fund_raw = fund_ctx.get("raw") or {}
    zones = (
        calculate_investment_zones(
            price=float(price),
            stats=stats,
            long_term_metrics=lt_metrics,
            fundamental_data=fund_raw,
            market=resolved_market,
        )
        if price and float(price) > 0
        else {}
    )

    payload = {
        "symbol": resolved_symbol,
        "market": resolved_market,
        "quote": {
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
            "currency": quote.get("currency"),
            "provider": quote.get("provider"),
            "indicators": {
                k: stats.get(k)
                for k in ("rsi", "sma20", "sma50", "sma200", "macd", "support", "resistance")
                if stats.get(k) is not None
            },
        },
        "long_term_metrics": lt_metrics,
        "investment_zones": zones,
        "fundamentals_available": fund_ctx.get("available"),
        "fundamentals_summary": fund_ctx.get("text"),
        "sharia_screen": fund_ctx.get("sharia"),
    }
    return status_msg, json.dumps(payload, ensure_ascii=False, default=str)


def _tool_get_analysis_detail(run_id: str, user_id: Optional[str]) -> Tuple[str, str]:
    status_msg = f"Membaca detail lengkap analisis swarm ({run_id})..."
    if not user_id:
        return status_msg, json.dumps({"error": "user_id tidak tersedia untuk mengakses riwayat analisis."})

    db = SessionLocal()
    try:
        row = (
            db.query(InvestmentAnalysisHistory)
            .filter(
                InvestmentAnalysisHistory.run_id == run_id,
                InvestmentAnalysisHistory.user_id == user_id,
            )
            .first()
        )
        if not row:
            return status_msg, json.dumps({"error": f"Analisis dengan run_id={run_id} tidak ditemukan."})

        res = _safe_json_loads(row.result_json)
        # Strip heavy raw OHLCV candles if present so payload stays within model context
        res_clean = {k: v for k, v in res.items() if k not in {"candles", "candles_1d", "candles_1w"}}
        return status_msg, json.dumps(
            {
                "run_id": row.run_id,
                "market": row.market,
                "analysis_type": row.analysis_type,
                "symbol": row.symbol,
                "decision": row.decision,
                "confidence": row.confidence,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "result": res_clean,
            },
            ensure_ascii=False,
            default=str,
        )
    finally:
        db.close()


def describe_planner_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Human-readable status indicator emitted to SSE before executing a tool."""
    if tool_name == "search_internet_live":
        q = str(arguments.get("query") or "").strip()
        return f"Mencari info terkini di internet: \"{q[:45]}\"..." if q else "Mencari info terkini di internet..."
    if tool_name == "fetch_asset_market_and_fundamentals":
        sym = str(arguments.get("symbol") or "").upper().strip()
        return f"Mengambil data harga & fundamental {sym or 'aset'}..."
    if tool_name == "get_investment_analysis_detail":
        rid = str(arguments.get("run_id") or "").strip()
        return f"Membaca detail laporan swarm {rid}..."
    return f"Menjalankan {tool_name}..."


def execute_planner_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    user_id: Optional[str] = None,
) -> Tuple[str, str]:
    """Executes one planner tool safely and returns (ui_status_label, result_text)."""
    try:
        if tool_name == "search_internet_live":
            return _tool_search_internet(str(arguments.get("query") or ""))
        if tool_name == "fetch_asset_market_and_fundamentals":
            return _tool_fetch_asset_data(
                symbol=str(arguments.get("symbol") or ""),
                market=str(arguments.get("market") or "auto"),
            )
        if tool_name == "get_investment_analysis_detail":
            return _tool_get_analysis_detail(
                run_id=str(arguments.get("run_id") or ""),
                user_id=user_id,
            )
        return "Menjalankan tool...", json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as exc:
        logger.warning("Planner tool %s failed: %s", tool_name, exc)
        return describe_planner_tool_call(tool_name, arguments), json.dumps(
            {"error": f"Tool {tool_name} gagal mengambil data: {exc}"}
        )

