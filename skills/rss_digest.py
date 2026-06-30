"""RSS digest skill — fetch and summarize entries from one or more feeds."""

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)


class RSSDigestSkill(BaseSkill):
    name = "rss_digest"
    description = "Fetch recent entries from one or more RSS/Atom feed URLs."
    parameters = {
        "urls": "Comma-separated list of RSS/Atom feed URLs.",
        "max_entries": "Maximum entries per feed (default: 5).",
    }

    def execute(self, params: dict, context: dict) -> str:
        try:
            import feedparser
        except ImportError:
            return "[rss_digest: feedparser is not installed — run: pip install feedparser]"

        raw_urls = params.get("urls", "").strip()
        if not raw_urls:
            return "[rss_digest: no URLs provided]"

        urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
        max_entries = int(params.get("max_entries", 5))
        sections: list[str] = []

        for url in urls:
            try:
                feed = feedparser.parse(url)
            except Exception as e:
                logger.error("Feed parse error", extra={"url": url, "error": str(e)})
                sections.append(f"**{url}**\n[error: {e}]")
                continue

            title = feed.feed.get("title", url)
            entries = feed.entries[:max_entries]

            if not entries:
                sections.append(f"**{title}**\nNo entries found.")
                continue

            lines = [f"**{title}**"]
            for entry in entries:
                name = entry.get("title", "(no title)")
                link = entry.get("link", "")
                summary = entry.get("summary", "")
                # Strip HTML from summary
                import re
                summary = re.sub(r"<[^>]+>", " ", summary)
                summary = re.sub(r"\s+", " ", summary).strip()
                summary = summary[:200] + "…" if len(summary) > 200 else summary
                line = f"- {name}"
                if summary:
                    line += f"\n  {summary}"
                if link:
                    line += f"\n  {link}"
                lines.append(line)

            sections.append("\n".join(lines))
            logger.info("Feed fetched", extra={"url": url, "entries": len(entries)})

        if not sections:
            return "No feed data retrieved."

        return "### RSS Digest\n\n" + "\n\n---\n\n".join(sections)
