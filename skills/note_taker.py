"""Note taker skill — save and retrieve notes in memory."""

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)


class NoteTakerSkill(BaseSkill):
    name = "note"
    description = "Save or retrieve notes in the knowledge base. Use action='save' to add a note, action='list' to see all notes."
    parameters = {
        "action": "'save' to add a note, 'list' to show existing notes.",
        "content": "The note content (required for action='save').",
        "tag": "Optional tag/category for the note.",
    }

    def execute(self, params: dict, context: dict) -> str:
        action = params.get("action", "save")
        memory_manager = context.get("memory")

        if memory_manager is None:
            return "[note: memory manager not available in context]"

        if action == "list":
            content = memory_manager.read_memory("memory")
            notes = self._extract_notes(content)
            if not notes:
                return "No notes saved yet."
            return "### Saved Notes\n\n" + "\n".join(notes)

        elif action == "save":
            note_content = params.get("content", "")
            if not note_content:
                return "[note: no content provided]"

            tag = params.get("tag", "general")
            entry = f"\n- [{tag}] {note_content}"
            memory_manager.append_memory("memory", entry)
            logger.info("Note saved", extra={"tag": tag, "length": len(note_content)})
            return f"Note saved under [{tag}]."

        return f"[note: unknown action '{action}'. Use 'save' or 'list'.]"

    def _extract_notes(self, memory_content: str) -> list[str]:
        """Extract note entries (lines starting with '- [') from memory."""
        notes = []
        for line in memory_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [") and "] " in stripped:
                notes.append(stripped)
        return notes
