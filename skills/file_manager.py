"""File manager skill — read, write, list, and delete files in a sandboxed directory."""

from pathlib import Path

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_safe(base: Path, rel_path: str) -> Path | None:
    """Resolve rel_path inside base, returning None if it escapes the sandbox."""
    try:
        target = (base / rel_path).resolve()
        target.relative_to(base.resolve())  # raises ValueError if outside
        return target
    except (ValueError, RuntimeError):
        return None


class FileManagerSkill(BaseSkill):
    name = "file"
    description = (
        "Read, write, list, or delete files within the configured files directory. "
        "Paths are relative to that directory; attempts to escape it are blocked."
    )
    parameters = {
        "action": "'read', 'write', 'list', or 'delete'.",
        "path": "Relative path within the files directory (e.g. 'notes/todo.txt').",
        "content": "Content to write (required for action='write').",
    }

    def _base_dir(self, config: dict) -> Path:
        rel = config.get("files", {}).get("base_dir", "files")
        d = _PROJECT_ROOT / rel
        d.mkdir(parents=True, exist_ok=True)
        return d

    def execute(self, params: dict, context: dict) -> str:
        action = params.get("action", "").lower()
        rel_path = params.get("path", "").strip()
        config = context.get("config", {})
        base = self._base_dir(config)

        if action == "list":
            target = base if not rel_path else _resolve_safe(base, rel_path)
            if target is None:
                return "[file: path is outside the allowed directory]"
            if not target.exists():
                return f"[file: directory not found: {rel_path or '.'}]"
            entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
            if not entries:
                return "Directory is empty."
            lines = [f"{'D' if p.is_dir() else 'F'}  {p.name}" for p in entries]
            return f"### Contents of {rel_path or '.'}\n\n" + "\n".join(lines)

        if not rel_path:
            return "[file: 'path' is required for this action]"

        target = _resolve_safe(base, rel_path)
        if target is None:
            return "[file: path is outside the allowed directory]"

        if action == "read":
            if not target.exists():
                return f"[file: not found: {rel_path}]"
            try:
                content = target.read_text(encoding="utf-8")
                logger.info("File read", extra={"path": rel_path, "size": len(content)})
                return f"### {rel_path}\n\n{content}"
            except OSError as e:
                return f"[file: read error — {e}]"

        elif action == "write":
            content = params.get("content", "")
            if content is None:
                return "[file: 'content' is required for write]"
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                logger.info("File written", extra={"path": rel_path, "size": len(content)})
                return f"File written: {rel_path}"
            except OSError as e:
                return f"[file: write error — {e}]"

        elif action == "delete":
            if not target.exists():
                return f"[file: not found: {rel_path}]"
            try:
                target.unlink()
                logger.info("File deleted", extra={"path": rel_path})
                return f"File deleted: {rel_path}"
            except OSError as e:
                return f"[file: delete error — {e}]"

        return f"[file: unknown action '{action}'. Use 'read', 'write', 'list', or 'delete'.]"
