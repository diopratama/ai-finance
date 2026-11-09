import html
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx

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
    "spot gold",
    "sbn",
    "ori",
    "sukuk",
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
]


def should_search_internet(query: str) -> bool:
    """Detects whether a user message requires real-time web search."""
    if not query:
        return False
    q_lower = query.lower()
    return any(k in q_lower for k in _LIVE_KEYWORDS)


def search_internet(query: str, max_results: int = 4) -> List[Dict[str, str]]:
    """
    Searches the live web for recent financial data, market quotes, or regulations.
    Returns a list of dicts: [{'title': '...', 'snippet': '...', 'url': '...'}]
    Uses DuckDuckGo HTML parser with graceful fallback.
    """
    if not query.strip():
        return []

    results: List[Dict[str, str]] = []

    # Clean query for search
    clean_query = query.strip()
    clean_query = re.sub(r"^/(?:finplanner|planner|ask|tanya)\s*", "", clean_query, flags=re.IGNORECASE).strip()
    if not clean_query:
        clean_query = query

    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        with httpx.Client(timeout=4.5, follow_redirects=True) as client:
            res = client.get(search_url, headers=headers)
            if res.status_code == 200:
                raw_html = res.text
                # Extract DuckDuckGo HTML results: class="result__body"
                # Extract title, url, and snippet
                snippets = re.findall(
                    r'<a[^>]+class="result__snippet[^>]*>(.*?)</a>',
                    raw_html,
                    re.DOTALL | re.IGNORECASE,
                )
                titles = re.findall(
                    r'<a[^>]+class="result__url[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    raw_html,
                    re.DOTALL | re.IGNORECASE,
                )
                web_titles = re.findall(
                    r'<a[^>]+class="result__snippet[^"]*".*?</h2>.*?<a[^>]+class="result__url',
                    raw_html,
                    re.DOTALL | re.IGNORECASE,
                )

                # Alternative regex for result block
                blocks = re.findall(
                    r'<div[^>]+class="[^"]*result__body[^"]*"[^>]*>(.*?)</div>\s*</div>',
                    raw_html,
                    re.DOTALL | re.IGNORECASE,
                )

                for block in blocks[:max_results]:
                    # Extract title & link
                    t_match = re.search(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)
                    s_match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL | re.IGNORECASE)

                    if t_match and s_match:
                        raw_link = t_match.group(1)
                        # DuckDuckGo redirect link /l/?kh=-1&uddg=https%3A%2F%2F...
                        actual_url = raw_link
                        if "uddg=" in raw_link:
                            parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                            if "uddg" in parsed_qs:
                                actual_url = parsed_qs["uddg"][0]

                        raw_t = re.sub(r"<[^>]+>", "", t_match.group(2))
                        raw_s = re.sub(r"<[^>]+>", "", s_match.group(1))

                        title = html.unescape(raw_t).strip()
                        snippet = html.unescape(raw_s).strip()

                        if title and snippet:
                            results.append({
                                "title": title,
                                "snippet": snippet,
                                "url": actual_url,
                            })
    except Exception as e:
        logger.debug("DuckDuckGo HTML search notice: %s", e)

    return results


def format_search_results_for_prompt(results: List[Dict[str, str]]) -> str:
    """Formats list of search results into an injected context section for the LLM."""
    if not results:
        return ""

    now_str = datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")
    lines = [
        f"--- DATA TERKINI DARI INTERNET (Real-Time Web Search) [Diambil: {now_str}] ---",
        "Berikut adalah rangkuman data dan informasi faktual terbaru yang ditemukan dari pencarian web:",
    ]

    for idx, r in enumerate(results, 1):
        lines.append(f"{idx}. Judul: {r.get('title', '')}")
        lines.append(f"   Sumber/URL: {r.get('url', '')}")
        lines.append(f"   Rangkuman: {r.get('snippet', '')}")

    lines.append("--- PEDOMAN PENGGUNAAN DATA TERKINI ---")
    lines.append("Gunakan data dan angka faktual terkini di atas untuk menjawab pertanyaan pengguna dengan presisi. Cantumkan rujukan/sumber secara natural jika relevan.")
    lines.append("-------------------------------------------------------------------------------")
    return "\n".join(lines)

