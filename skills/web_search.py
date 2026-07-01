"""Web search skill — search the web and return results."""

import json
import os
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote_plus

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class WebSearchSkill(BaseSkill):
    name = "web_search"
    description = (
        "Search the web for information and return results. Uses the Brave "
        "Search API for full results when BRAVE_SEARCH_API_KEY is set; "
        "otherwise falls back to DuckDuckGo's Instant Answer API, which only "
        "covers well-known entities."
    )
    parameters = {
        "query": "The search query string.",
        "max_results": "Maximum number of results to return (default: 5).",
    }

    def execute(self, params: dict, context: dict) -> str:
        query = params.get("query", "")
        if not query:
            return "[web_search: no query provided]"

        max_results = int(params.get("max_results", 5))
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")

        if api_key:
            try:
                results = self._brave_search(query, max_results, api_key)
            except (URLError, TimeoutError, json.JSONDecodeError) as e:
                logger.error("Brave search failed", extra={"query": query, "error": str(e)})
                return f"[web_search error: {e}]"
            if not results:
                return f"No results found for: {query}"
            logger.debug("Web search results", extra={"query": query, "count": len(results)})
            return f"### Search results for: {query}\n\n" + "\n\n".join(results)

        # No API key configured — fall back to DuckDuckGo's Instant Answer API.
        # It only returns results for well-known entities (Wikipedia-style
        # infobox answers), not general open-ended queries.
        abstract = self._duckduckgo_instant_answer(query)
        if not abstract:
            return (
                f"No results found for: {query}\n"
                "[web_search: set BRAVE_SEARCH_API_KEY for full web search results — "
                "without it, only well-known-entity lookups work]"
            )
        return f"### Search results for: {query}\n\n{abstract}"

    @staticmethod
    def _brave_search(query: str, max_results: int, api_key: str) -> list:
        encoded = quote_plus(query)
        url = f"{_BRAVE_SEARCH_URL}?q={encoded}&count={max_results}"
        req = Request(
            url,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        )
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("web", {}).get("results", [])[:max_results]:
            title = item.get("title", "")
            link = item.get("url", "")
            description = item.get("description", "")
            if title and link:
                results.append(f"- **{title}**\n  {link}\n  {description}")
        return results

    @staticmethod
    def _duckduckgo_instant_answer(query: str) -> str:
        encoded = quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        try:
            req = Request(url, headers={"User-Agent": "A_OpenClaw/0.1"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError):
            return ""
        abstract = data.get("AbstractText", "")
        if not abstract:
            return ""
        source = data.get("AbstractSource", "")
        return f"**{source}:** {abstract}" if source else abstract
