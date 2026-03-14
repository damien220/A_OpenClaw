"""Local file/directory data source for the heartbeat."""

from pathlib import Path

from heartbeat.sources.base import BaseSource

from logger_pkg import get_logger

logger = get_logger(__name__)


class FileSource(BaseSource):
    """Read local files or detect changes in a directory.

    Config keys:
        path (str): File or directory path.
        pattern (str): Glob pattern for directory scanning, default "*.md".
        max_chars (int): Max characters to read per file, default 5000.
    """

    def gather(self) -> str:
        path = Path(self.config.get("path", "")).expanduser()
        if not path.exists():
            logger.warning("File source path missing", extra={"source": self.name, "path": str(path)})
            return f"[File source {self.name}]: path does not exist: {path}"

        pattern = self.config.get("pattern", "*.md")
        max_chars = self.config.get("max_chars", 5000)

        if path.is_file():
            content = path.read_text(encoding="utf-8")[:max_chars]
            logger.debug("File source gathered", extra={"source": self.name, "file": path.name, "chars": len(content)})
            return f"### Source: {self.name} (File: {path.name})\n\n{content}"

        # Directory: read matching files
        files = sorted(path.glob(pattern))
        if not files:
            return ""

        parts = []
        total = 0
        for f in files:
            if total >= max_chars:
                break
            text = f.read_text(encoding="utf-8")
            chunk = text[:max_chars - total]
            total += len(chunk)
            parts.append(f"**{f.name}:**\n{chunk}")

        body = "\n\n".join(parts)
        logger.debug("File source gathered", extra={"source": self.name, "files": len(files), "chars": total})
        return f"### Source: {self.name} (Directory: {path.name})\n\n{body}"
