"""File-based memory system for A_OpenClaw.

Manages reading, writing, and assembling context from markdown memory files:
  - user.md    — User profile and preferences
  - memory.md  — Running knowledge base
  - skill.md   — Available skills documentation
  - logs/      — Timestamped interaction logs
"""

from datetime import datetime, timezone
from pathlib import Path

from core.config_loader import load_config

from logger_pkg import get_logger

logger = get_logger(__name__)


# Rough char-to-token ratio (1 token ~ 4 chars for English text)
_CHARS_PER_TOKEN = 4


class MemoryManager:
    def __init__(self, config: dict | None = None):
        self._config = config or load_config()
        mem_cfg = self._config.get("memory", {})
        llm_cfg = self._config.get("llm", {})
        project_root = Path(__file__).resolve().parent.parent

        self._memory_dir = project_root / mem_cfg.get("directory", "memory")
        self._user_path = self._memory_dir / mem_cfg.get("user_file", "user.md")
        self._memory_path = self._memory_dir / mem_cfg.get("memory_file", "memory.md")
        self._skill_path = self._memory_dir / mem_cfg.get("skill_file", "skill.md")
        self._logs_dir = project_root / mem_cfg.get("logs_directory", "memory/logs")
        self._max_log_files = mem_cfg.get("max_log_files", 100)
        self._max_context_chars = llm_cfg.get("max_context_tokens", 100000) * _CHARS_PER_TOKEN
        self._max_memory_chars = mem_cfg.get("max_memory_chars", 50000)

        self._path_map = {
            "user": self._user_path,
            "memory": self._memory_path,
            "skill": self._skill_path,
        }
        self._last_log_date: str | None = None

        self._logs_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("MemoryManager initialized", extra={"memory_dir": str(self._memory_dir)})

    def read_memory(self, file_key: str) -> str:
        """Read a memory file by key ('user', 'memory', or 'skill')."""
        path = self._path_map.get(file_key)
        if path is None:
            raise ValueError(f"Unknown memory file key: {file_key}")
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_memory(self, file_key: str, content: str) -> None:
        """Overwrite a memory file with new content."""
        path = self._path_map.get(file_key)
        if path is None:
            raise ValueError(f"Unknown memory file key: {file_key}")
        path.write_text(content, encoding="utf-8")
        logger.info("Memory written", extra={"file_key": file_key, "size": len(content)})

    def append_memory(self, file_key: str, content: str) -> None:
        """Append content to a memory file."""
        existing = self.read_memory(file_key)
        separator = "\n" if existing and not existing.endswith("\n") else ""
        self.write_memory(file_key, existing + separator + content)

    def build_context(self) -> str:
        """Assemble full context from all memory files for LLM injection.

        Truncates content if total exceeds max_context_chars to stay within
        the LLM's context window. Priority: user > skill > memory (memory
        is truncated first since it grows unbounded).
        """
        parts: dict[str, str] = {}
        for key, label in [
            ("user", "User Profile"),
            ("skill", "Available Skills"),
            ("memory", "Knowledge Base"),
        ]:
            content = self.read_memory(key)
            if content.strip():
                parts[label] = content.strip()

        # Truncate memory if total exceeds limit
        total = sum(len(v) for v in parts.values())
        if total > self._max_context_chars:
            overshoot = total - self._max_context_chars
            if "Knowledge Base" in parts:
                kb = parts["Knowledge Base"]
                truncated = kb[: max(0, len(kb) - overshoot)]
                last_newline = truncated.rfind("\n")
                if last_newline > 0:
                    truncated = truncated[:last_newline]
                parts["Knowledge Base"] = truncated + "\n\n[... truncated for context window ...]"
                logger.warning(
                    "Context truncated",
                    extra={"original": total, "limit": self._max_context_chars, "removed_chars": overshoot},
                )

        sections = [f"## {label}\n\n{text}" for label, text in parts.items()]
        context = "\n\n---\n\n".join(sections)
        logger.debug("Context built", extra={"context_len": len(context)})
        return context

    def compact_memory(self) -> bool:
        """Trim memory.md if it exceeds max_memory_chars.

        Keeps the last max_memory_chars characters (most recent entries).
        Returns True if compaction occurred.
        """
        content = self.read_memory("memory")
        if len(content) <= self._max_memory_chars:
            return False

        # Keep the tail (newest entries), cut at a line boundary
        trimmed = content[-self._max_memory_chars:]
        first_newline = trimmed.find("\n")
        if first_newline > 0:
            trimmed = trimmed[first_newline + 1:]

        header = "# Knowledge Base\n\n[... older entries compacted ...]\n\n"
        self.write_memory("memory", header + trimmed)
        logger.info(
            "Memory compacted",
            extra={"before": len(content), "after": len(header + trimmed)},
        )
        return True

    def log_interaction(self, role: str, content: str) -> Path:
        """Write a timestamped log entry. Returns the log file path."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        log_file = self._logs_dir / f"{date_str}.md"

        timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        entry = f"\n### [{timestamp}] {role}\n\n{content}\n"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        if date_str != self._last_log_date:
            self._last_log_date = date_str
            self._rotate_logs()

        return log_file

    def _rotate_logs(self) -> None:
        """Remove oldest log files if count exceeds max_log_files."""
        log_files = sorted(self._logs_dir.glob("*.md"))
        removed = 0
        while len(log_files) > self._max_log_files:
            log_files.pop(0).unlink()
            removed += 1
        if removed:
            logger.info("Log files rotated", extra={"removed": removed})
