"""Summarizer skill — summarize a URL or long text via the LLM."""

import re
from urllib.request import Request, urlopen
from urllib.error import URLError

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)

_LENGTH_INSTRUCTIONS = {
    "short": "Summarize in 1-2 sentences.",
    "medium": "Summarize in one concise paragraph.",
    "long": "Summarize as a bullet-point list of the key points.",
}
_MAX_CONTENT_CHARS = 20_000


def _fetch_url(url: str) -> str:
    req = Request(url, headers={"User-Agent": "A_OpenClaw/0.1"})
    with urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    # Strip HTML tags and collapse whitespace
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class SummarizerSkill(BaseSkill):
    name = "summarize"
    description = (
        "Summarize a URL or long text. "
        "Provide either 'url' or 'text', not both."
    )
    parameters = {
        "text": "Text to summarize (use this OR 'url').",
        "url": "URL to fetch and summarize (use this OR 'text').",
        "length": "'short' (1-2 sentences), 'medium' (paragraph), or 'long' (bullet points). Default: medium.",
    }

    def execute(self, params: dict, context: dict) -> str:
        text = params.get("text", "").strip()
        url = params.get("url", "").strip()
        length = params.get("length", "medium").lower()
        if length not in _LENGTH_INSTRUCTIONS:
            length = "medium"

        if not text and not url:
            return "[summarize: provide 'text' or 'url']"

        llm = context.get("llm")
        if llm is None:
            return "[summarize: LLM not available in context]"

        if url:
            try:
                text = _fetch_url(url)
                logger.info("URL fetched for summarization", extra={"url": url, "chars": len(text)})
            except (URLError, TimeoutError) as e:
                logger.error("URL fetch failed", extra={"url": url, "error": str(e)})
                return f"[summarize: failed to fetch URL — {e}]"

        content = text[:_MAX_CONTENT_CHARS]
        instruction = _LENGTH_INSTRUCTIONS[length]
        source_note = f" (from {url})" if url else ""
        prompt = (
            f"{instruction} Do not add any preamble — output the summary only.\n\n"
            f"Content{source_note}:\n{content}"
        )

        try:
            result = llm.send("", prompt)
            logger.info("Summarization done", extra={"length": length, "input_chars": len(content)})
            return result
        except Exception as e:
            logger.error("Summarization failed", extra={"error": str(e)})
            return f"[summarize: error — {e}]"
