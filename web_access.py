import os
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

USER_AGENT = "NEURA/1.0 (+local personal assistant)"


class WebSearchError(RuntimeError):
    pass


def _clean(text: str, limit: int = 900) -> str:
    return " ".join(text.split())[:limit]


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Use Tavily when configured; otherwise use DuckDuckGo's HTML endpoint."""
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if tavily_key:
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_answer": False,
                },
                headers={"User-Agent": USER_AGENT},
            )
        if r.status_code >= 400:
            raise WebSearchError(f"Tavily: {r.status_code} {r.text[:300]}")
        return [
            {"title": x.get("title", ""), "url": x.get("url", ""), "snippet": _clean(x.get("content", ""))}
            for x in r.json().get("results", [])[:max_results]
        ]

    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        r = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
        )
    if r.status_code >= 400:
        raise WebSearchError(f"Ricerca web non disponibile: HTTP {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for block in soup.select(".result"):
        link = block.select_one(".result__a")
        snippet = block.select_one(".result__snippet")
        if not link:
            continue
        href = link.get("href", "")
        results.append({"title": _clean(link.get_text(" "), 180), "url": href, "snippet": _clean(snippet.get_text(" ") if snippet else "")})
        if len(results) >= max_results:
            break
    return results


async def read_page(url: str, max_chars: int = 6000) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise WebSearchError("URL non consentito")
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": USER_AGENT})
    if r.status_code >= 400:
        raise WebSearchError(f"Impossibile leggere la pagina: HTTP {r.status_code}")
    ctype = r.headers.get("content-type", "")
    if "text/html" not in ctype and "text/plain" not in ctype:
        raise WebSearchError("Formato della pagina non supportato")
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    title = _clean(soup.title.get_text(" ") if soup.title else url, 200)
    text = _clean(soup.get_text(" "), max_chars)
    return {"title": title, "url": str(r.url), "text": text}
