"""Web search skill — search the web and return results."""

import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote_plus

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)


class WebSearchSkill(BaseSkill):
    name = "web_search"
    description = "Search the web for information and return summarized results."
    parameters = {
        "query": "The search query string.",
        "max_results": "Maximum number of results to return (default: 5).",
    }

    def execute(self, params: dict, context: dict) -> str:
        query = params.get("query", "")
        if not query:
            return "[web_search: no query provided]"

        max_results = int(params.get("max_results", 5))

        # Use DuckDuckGo Instant Answer API (no API key needed)
        encoded = quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

        try:
            req = Request(url, headers={"User-Agent": "A_OpenClaw/0.1"})
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.error("Web search failed", extra={"query": query, "error": str(e)})
            return f"[web_search error: {e}]"

        results = []

        # Abstract (main answer)
        abstract = data.get("AbstractText", "")
        if abstract:
            source = data.get("AbstractSource", "")
            results.append(f"**{source}:** {abstract}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            text = topic.get("Text", "")
            link = topic.get("FirstURL", "")
            if text:
                results.append(f"- {text}\n  {link}")

        if not results:
            return f"No results found for: {query}"

        logger.debug("Web search results", extra={"query": query, "count": len(results)})
        return f"### Search results for: {query}\n\n" + "\n\n".join(results)
