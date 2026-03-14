"""RSS/Atom feed data source for the heartbeat."""

from heartbeat.sources.base import BaseSource

from logger_pkg import get_logger

logger = get_logger(__name__)


class RSSSource(BaseSource):
    """Parse an RSS or Atom feed and return recent entries.

    Config keys:
        url (str): Feed URL.
        max_entries (int): Max entries to return, default 5.
    """

    def gather(self) -> str:
        url = self.config.get("url", "")
        if not url:
            return ""

        max_entries = self.config.get("max_entries", 5)

        try:
            import feedparser
        except ImportError:
            logger.error("feedparser not installed", extra={"source": self.name})
            return f"[RSS source {self.name}]: feedparser not installed (pip install feedparser)"

        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            logger.warning("RSS feed parse failed", extra={"source": self.name, "url": url})
            return f"[RSS source {self.name}]: failed to parse feed from {url}"

        entries = feed.entries[:max_entries]
        if not entries:
            return ""

        lines = []
        for entry in entries:
            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            published = entry.get("published", "")
            summary = entry.get("summary", "")[:200]
            lines.append(f"- **{title}** ({published})\n  {link}\n  {summary}")

        body = "\n".join(lines)
        logger.debug("RSS source gathered", extra={"source": self.name, "entries": len(entries)})
        return f"### Source: {self.name} (RSS)\n\n{body}"
