"""
Quantro Web Access Tooling
Provides web_fetch (HTML to Markdown converter) and web_search (online documentation/web search).
"""

import re
import urllib.parse
from typing import Dict, Any, List
import httpx

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Quantro/2.0"


def html_to_markdown(html_text: str) -> str:
    """Converts raw HTML text into clean readable markdown, stripping layout tags."""
    # Remove script, style, svg, noscript
    cleaned = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", "", html_text, flags=re.DOTALL | re.IGNORECASE)
    # Remove header, footer, nav
    cleaned = re.sub(r"<(header|footer|nav)[^>]*>.*?</\1>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Convert common elements
    cleaned = re.sub(r"<h[1-2][^>]*>(.*?)</h[1-2]>", r"\n\n# \1\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<h[3-4][^>]*>(.*?)</h[3-4]>", r"\n\n## \1\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<h[5-6][^>]*>(.*?)</h[5-6]>", r"\n\n### \1\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", r"\n```\n\1\n```\n", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\n\1\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<li[^>]*>(.*?)</li>", r"\n* \1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<a[^>]*href=[\"'](.*?)[\"'][^>]*>(.*?)</a>", r"[\2](\1)", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)

    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", cleaned)

    # Normalize whitespace
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    compacted = "\n".join(l for l in lines if l)
    return compacted


class WebTools:
    """Handles internet connectivity for documentation lookups and search."""

    def web_fetch(self, url: str) -> Dict[str, Any]:
        """Fetches URL and returns readable Markdown content."""
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"success": False, "error": "URL must start with http:// or https://"}

        headers = {"User-Agent": USER_AGENT}
        try:
            with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
                res = client.get(url)

            if res.status_code != 200:
                return {
                    "success": False,
                    "url": url,
                    "status_code": res.status_code,
                    "error": f"HTTP {res.status_code}: Could not fetch page"
                }

            md = html_to_markdown(res.text)
            char_limit = 9000
            truncated = len(md) > char_limit
            final_content = md[:char_limit] + ("\n\n... [İçerik kesildi]" if truncated else "")

            return {
                "success": True,
                "url": url,
                "status_code": res.status_code,
                "content": final_content,
                "truncated": truncated
            }
        except Exception as e:
            return {"success": False, "url": url, "error": f"Failed fetching web page: {str(e)}"}

    def web_search(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Performs web search via DuckDuckGo and returns top results with summaries."""
        headers = {"User-Agent": USER_AGENT}
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        try:
            with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
                res = client.get(url)

            if res.status_code != 200:
                return {"success": False, "error": f"Search engine returned HTTP {res.status_code}"}

            html = res.text
            results: List[Dict[str, str]] = []

            # Extract result blocks
            blocks = re.findall(r'<div class="result__body">(.*?)</div>\s*</div>', html, re.DOTALL)
            for block in blocks[:max_results]:
                title_match = re.search(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
                snippet_match = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)

                raw_url = title_match.group(1) if title_match else ""
                # Parse redirect url if duckduckgo uddg parameter exists
                if "uddg=" in raw_url:
                    parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query)
                    raw_url = parsed_q.get("uddg", [raw_url])[0]

                raw_title = re.sub(r"<[^>]+>", "", title_match.group(2)).strip() if title_match else "No title"
                raw_snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip() if snippet_match else ""

                if raw_url:
                    results.append({
                        "title": raw_title,
                        "url": raw_url,
                        "snippet": raw_snippet
                    })

            if not results:
                # Fallback: simple text extract
                return {
                    "success": True,
                    "query": query,
                    "results_count": 0,
                    "results": [],
                    "message": "No direct search matches found."
                }

            return {
                "success": True,
                "query": query,
                "results_count": len(results),
                "results": results
            }
        except Exception as e:
            return {"success": False, "query": query, "error": f"Web search failed: {str(e)}"}
