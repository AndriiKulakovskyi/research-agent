"""Deep-research tools: literature search, web retrieval, and strategic reflection.

The literature tools (arXiv, Semantic Scholar) are keyless public APIs — the
core research loop works with no extra accounts. General web search uses
Tavily only when TAVILY_API_KEY is set, and degrades to guidance otherwise.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

import httpx
from langchain_core.tools import tool

MAX_RESULTS = 10
MAX_FETCH_CHARS = 8000

_ATOM = "{http://www.w3.org/2005/Atom}"

_http_client: httpx.Client | None = None


def _http() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "deep-harness-agent/0.1 (research tool)"},
        )
    return _http_client


def set_http_client(client: httpx.Client | None) -> None:
    """Override the HTTP client (tests inject a MockTransport)."""
    global _http_client
    _http_client = client


@tool
def arxiv_search(query: str, max_results: int = 5) -> str:
    """Search arXiv for academic papers (machine learning, statistics, CS, math,
    physics). Returns title, authors, year, arXiv id, link, and abstract for
    each match. The primary tool for literature research on algorithms.
    """
    max_results = max(1, min(max_results, MAX_RESULTS))
    try:
        response = _http().get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "max_results": max_results,
                "sortBy": "relevance",
            },
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as exc:
        return f"arXiv search failed: {exc}"

    entries = root.findall(f"{_ATOM}entry")
    if not entries:
        return f"No arXiv results for {query!r}. Try different terms."
    blocks = []
    for entry in entries:
        title = re.sub(r"\s+", " ", entry.findtext(f"{_ATOM}title", "")).strip()
        authors = ", ".join(
            a.findtext(f"{_ATOM}name", "") for a in entry.findall(f"{_ATOM}author")[:6]
        )
        published = entry.findtext(f"{_ATOM}published", "")[:4]
        link = entry.findtext(f"{_ATOM}id", "")
        arxiv_id = link.rsplit("/abs/", 1)[-1] if "/abs/" in link else link
        summary = re.sub(r"\s+", " ", entry.findtext(f"{_ATOM}summary", "")).strip()[:600]
        blocks.append(
            f"{title} ({published})\n  authors: {authors}\n  arXiv: {arxiv_id} — {link}\n"
            f"  abstract: {summary}"
        )
    return "\n\n".join(blocks)


@tool
def semantic_scholar_search(query: str, limit: int = 5) -> str:
    """Search Semantic Scholar across all academic literature. Returns title,
    year, authors, citation count, venue, and abstract — citation counts help
    identify the influential papers on a topic.
    """
    limit = max(1, min(limit, MAX_RESULTS))
    try:
        response = _http().get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": limit,
                "fields": "title,year,citationCount,venue,authors,abstract,url,externalIds",
            },
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"Semantic Scholar search failed: {exc} (the free API rate-limits; retry shortly)"

    papers = data.get("data") or []
    if not papers:
        return f"No Semantic Scholar results for {query!r}."
    blocks = []
    for p in papers:
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:6])
        abstract = (p.get("abstract") or "")[:600]
        arxiv_id = (p.get("externalIds") or {}).get("ArXiv", "")
        blocks.append(
            f"{p.get('title')} ({p.get('year')}) — {p.get('citationCount', 0)} citations\n"
            f"  authors: {authors}\n"
            f"  venue: {p.get('venue') or 'n/a'}"
            + (f" | arXiv: {arxiv_id}" if arxiv_id else "")
            + f"\n  url: {p.get('url')}\n  abstract: {abstract}"
        )
    return "\n\n".join(blocks)


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """General web search (requires TAVILY_API_KEY on the server). For academic
    literature prefer arxiv_search / semantic_scholar_search, which need no key.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return (
            "Web search is not configured (no TAVILY_API_KEY on the server). "
            "Use arxiv_search / semantic_scholar_search for literature, or "
            "fetch_url if you already know a relevant page."
        )
    try:
        response = _http().post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": min(max_results, MAX_RESULTS)},
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except Exception as exc:
        return f"Web search failed: {exc}"
    if not results:
        return f"No web results for {query!r}."
    return "\n\n".join(
        f"{r.get('title')}\n  {r.get('url')}\n  {(r.get('content') or '')[:500]}" for r in results
    )


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"[ \t]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


@tool
def fetch_url(url: str) -> str:
    """Fetch a web page or document URL and return its readable text content
    (HTML is stripped to plain text; truncated to ~8000 chars). Use after a
    search to read a promising source in full.
    """
    if not url.startswith(("http://", "https://")):
        return "Rejected: only http(s) URLs can be fetched."
    try:
        response = _http().get(url)
        response.raise_for_status()
    except Exception as exc:
        return f"Fetch failed for {url}: {exc}"
    content_type = response.headers.get("content-type", "")
    if "html" in content_type:
        text = _html_to_text(response.text)
    elif content_type.startswith(("text/", "application/json", "application/xml")):
        text = response.text
    else:
        return f"Unsupported content type {content_type!r} for {url} (binary?)."
    if len(text) > MAX_FETCH_CHARS:
        text = text[:MAX_FETCH_CHARS] + f"\n... truncated at {MAX_FETCH_CHARS} chars."
    return text or "(page had no extractable text)"


@tool
def think_tool(reflection: str) -> str:
    """Strategic reflection checkpoint during research. After each round of
    searches, record: what did I find, what is still missing, is the evidence
    sufficient, and what is the single best next step? This costs nothing and
    prevents both premature conclusions and aimless searching.
    """
    return f"Reflection recorded:\n{reflection}"


RESEARCH_TOOLS = [arxiv_search, semantic_scholar_search, web_search, fetch_url, think_tool]
