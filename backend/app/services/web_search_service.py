import html
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx

from app.services.market_rates_service import fetch_live_market_rates

logger = logging.getLogger(__name__)

# Keywords that indicate the query requires live / current internet data
_LIVE_KEYWORDS = [
    "kurs",
    "dollar",
    "dolar",
    "usd",
    "nilai tukar",
    "emas",
    "harga emas",
    "antam",
    "pegadaian",
    "logam mulia",
    "spot gold",
    "xau",
    "sbn",
    "ori",
    "sukuk",
    "sbr",
    "kupon sbn",
    "bi rate",
    "suku bunga",
    "bi 7-day",
    "reverse repo",
    "bank indonesia",
    "inflasi",
    "bps",
    "ihsg",
    "bursa efek",
    "saham",
    "lq45",
    "idx30",
    "crypto",
    "bitcoin",
    "btc",
    "pajak",
    "pph",
    "ppn",
    "uu hpp",
    "regulasi",
    "hari ini",
    "sekarang",
    "terkini",
    "terbaru",
    "update",
    "2025",
    "2026",
    "tahun ini",
    "bulan ini",
    "berita",
]

_SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}


def should_search_internet(query: str) -> bool:
    """Detects whether a user message requires real-time web search."""
    if not query:
        return False
    q_lower = query.lower()
    return any(k in q_lower for k in _LIVE_KEYWORDS)


def _clean_html_text(raw: str) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(html.unescape(raw))
    stripped = re.sub(r"<[^>]+>", " ", unescaped)
    cleaned = html.unescape(stripped)
    # Remove misleading JS template placeholders like "Rp 0/gr"
    cleaned = re.sub(r"Harga\s+Beli\s+Emas\s+Rp\s*0\s*/\s*gr", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _unwrap_yahoo_url(raw_url: str) -> str:
    """Extracts the target URL from Yahoo redirect wrapper (/RU=https%3A%2F%2F.../RK=...)."""
    m = re.search(r"/RU=([^/]+)/RK=", raw_url)
    if m:
        return urllib.parse.unquote(m.group(1))
    return raw_url


def _search_yahoo_id(client: httpx.Client, clean_query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Searches Yahoo Search Indonesia (accessible on all Indonesian networks without ISP block)."""
    results: List[Dict[str, str]] = []
    url = f"https://id.search.yahoo.com/search?p={urllib.parse.quote(clean_query)}&ei=UTF-8"
    try:
        res = client.get(url, headers=_SEARCH_HEADERS)
        if res.status_code != 200:
            return []

        raw_html = res.text
        # Match organic search result blocks in Yahoo Search HTML
        titles = re.findall(
            r'<h3[^>]*class="[^"]*title[^"]*"[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            raw_html,
            re.DOTALL | re.IGNORECASE,
        )
        snippets = re.findall(
            r'<div[^>]*class="[^"]*compText[^"]*"[^>]*>(.*?)</div>',
            raw_html,
            re.DOTALL | re.IGNORECASE,
        )

        for idx, (raw_href, raw_title) in enumerate(titles):
            if len(results) >= max_results:
                break
            actual_url = _unwrap_yahoo_url(raw_href)
            if "yahoo.com" in actual_url and "search.yahoo.com" in actual_url:
                continue
            title = _clean_html_text(raw_title)
            snippet = _clean_html_text(snippets[idx]) if idx < len(snippets) else ""
            if title and snippet:
                results.append(
                    {
                        "title": title,
                        "snippet": snippet,
                        "url": actual_url,
                    }
                )
    except Exception as e:
        logger.debug("Yahoo ID search notice: %s", e)

    return results


def _search_google_news_rss(client: httpx.Client, clean_query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Fetches real-time financial & news headlines from Google News Indonesia RSS."""
    results: List[Dict[str, str]] = []
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean_query)}&hl=id&gl=ID&ceid=ID:id"
    try:
        res = client.get(url, headers=_SEARCH_HEADERS)
        if res.status_code != 200:
            return []

        xml_text = res.text
        items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL | re.IGNORECASE)
        for item in items[:max_results]:
            t_m = re.search(r"<title>(.*?)</title>", item, re.DOTALL | re.IGNORECASE)
            l_m = re.search(r"<link>(.*?)</link>", item, re.DOTALL | re.IGNORECASE)
            d_m = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL | re.IGNORECASE)
            s_m = re.search(r"<source[^>]*>(.*?)</source>", item, re.DOTALL | re.IGNORECASE)
            desc_m = re.search(r"<description>(.*?)</description>", item, re.DOTALL | re.IGNORECASE)

            title = _clean_html_text(t_m.group(1)) if t_m else ""
            link = _clean_html_text(l_m.group(1)) if l_m else ""
            pub_date = _clean_html_text(d_m.group(1)) if d_m else ""
            source_name = _clean_html_text(s_m.group(1)) if s_m else "Google News ID"
            desc_text = _clean_html_text(desc_m.group(1)) if desc_m else title

            if title:
                snippet = f"[{source_name} - {pub_date}] {desc_text}" if pub_date else f"[{source_name}] {desc_text}"
                results.append(
                    {
                        "title": title,
                        "snippet": snippet,
                        "url": link or f"https://news.google.com ({source_name})",
                    }
                )
    except Exception as e:
        logger.debug("Google News RSS search notice: %s", e)

    return results


def _search_bing_news_rss(client: httpx.Client, clean_query: str, max_results: int = 2) -> List[Dict[str, str]]:
    """Fallback search via Bing News RSS."""
    results: List[Dict[str, str]] = []
    url = f"https://www.bing.com/news/search?q={urllib.parse.quote(clean_query)}&format=rss"
    try:
        res = client.get(url, headers=_SEARCH_HEADERS)
        if res.status_code != 200:
            return []

        xml_text = res.text
        items = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL | re.IGNORECASE)
        for item in items[:max_results]:
            t_m = re.search(r"<title>(.*?)</title>", item, re.DOTALL | re.IGNORECASE)
            l_m = re.search(r"<link>(.*?)</link>", item, re.DOTALL | re.IGNORECASE)
            desc_m = re.search(r"<description>(.*?)</description>", item, re.DOTALL | re.IGNORECASE)

            title = _clean_html_text(t_m.group(1)) if t_m else ""
            link = _clean_html_text(l_m.group(1)) if l_m else ""
            snippet = _clean_html_text(desc_m.group(1)) if desc_m else title

            if title and snippet:
                results.append(
                    {
                        "title": title,
                        "snippet": snippet,
                        "url": link or "https://www.bing.com/news",
                    }
                )
    except Exception as e:
        logger.debug("Bing News RSS search notice: %s", e)

    return results


def search_internet(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """
    Searches the live web for recent financial data, market quotes, or regulations.
    Combines Yahoo Search Indonesia + Google News Indonesia RSS + Bing News RSS
    so it never gets blocked by Indonesian ISP filters (Kominfo).
    """
    if not query or not query.strip():
        return []

    clean_query = query.strip()
    clean_query = re.sub(r"^/(?:finplanner|planner|ask|tanya)\s*", "", clean_query, flags=re.IGNORECASE).strip()
    if not clean_query:
        clean_query = query.strip()

    results: List[Dict[str, str]] = []
    seen_titles = set()

    with httpx.Client(timeout=4.5, follow_redirects=True) as client:
        # 1. Organic web snippets from Yahoo Search Indonesia
        for item in _search_yahoo_id(client, clean_query, max_results=3):
            key = item["title"].lower()[:50]
            if key not in seen_titles:
                seen_titles.add(key)
                results.append(item)

        # 2. Latest Indonesian news headlines from Google News RSS
        if len(results) < max_results:
            for item in _search_google_news_rss(client, clean_query, max_results=3):
                key = item["title"].lower()[:50]
                if key not in seen_titles:
                    seen_titles.add(key)
                    results.append(item)
                    if len(results) >= max_results:
                        break

        # 3. Fallback to Bing News RSS if still empty
        if not results:
            for item in _search_bing_news_rss(client, clean_query, max_results=max_results):
                results.append(item)

    return results[:max_results]


def _fmt_rp(val: float) -> str:
    return f"Rp {int(round(val)):,}".replace(",", ".")


def format_search_results_for_prompt(results: List[Dict[str, str]]) -> str:
    """Formats live market rates and web search results into an injected context section for the LLM."""
    now_str = datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")
    rates = fetch_live_market_rates()

    lines = [
        f"--- DATA TERKINI DARI INTERNET (Real-Time Web Search & Live Market API) [Diambil: {now_str}] ---",
        "1. RINGKASAN KURS & HARGA EMAS LIVE HARI INI (Data API Terverifikasi):",
        f"   • Harga Beli Emas Antam (1 Gram Ritel Indonesia): {_fmt_rp(rates.get('gold_antam_idr', rates['gold_idr_per_gram']))} / gram",
        f"   • Harga Jual Kembali / Buyback Emas Antam: {_fmt_rp(rates.get('gold_buyback_idr', 2373000))} / gram",
        f"   • Harga Emas Spot Dunia (XAU): ${rates.get('gold_xau_usd', 4110):,.2f} / troy oz (≈ {_fmt_rp(rates.get('gold_spot_idr', 2390000))} / gram)",
        f"   • Nilai Tukar Kurs Dollar (USD/IDR): {_fmt_rp(rates['usd_idr'])} per $1 USD",
        f"   • Sumber Data Kurs & Komoditas: {rates.get('source', 'Live Market Feed')}",
    ]

    if results:
        lines.append("")
        lines.append("2. HASIL PENCARIAN WEB & BERITA FINANSIAL TERKINI:")
        for idx, r in enumerate(results, 1):
            lines.append(f"   [{idx}] Judul: {r.get('title', '')}")
            lines.append(f"       Sumber/URL: {r.get('url', '')}")
            lines.append(f"       Ringkasan: {r.get('snippet', '')}")

    lines.extend(
        [
            "",
            "--- PEDOMAN PENGGUNAAN DATA REAL-TIME ---",
            "WAJIB gunakan angka kurs, harga emas Antam, buyback, spot XAU, dan berita terkini di atas untuk menjawab pertanyaan user secara langsung dan akurat.",
            "DILARANG menjawab 'Data tidak tersedia di snapshot lokal' karena data pasar real-time sudah disuplai di atas.",
            "-------------------------------------------------------------------------------",
        ]
    )
    return "\n".join(lines)
