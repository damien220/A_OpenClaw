"""Reminder skill — set and check reminders stored in memory.

Reminders are stored in memory.md with a special format:
  - [reminder][YYYY-MM-DD HH:MM] reminder text

The heartbeat can check for due reminders and send them through the adapter.
"""

from datetime import datetime, timezone

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)

_REMINDER_PREFIX = "- [reminder]"


class ReminderSkill(BaseSkill):
    name = "reminder"
    description = "Set a reminder for a future time, or check for due reminders. Reminders are stored in the knowledge base and checked by the heartbeat."
    parameters = {
        "action": "'set' to create a reminder, 'check' to list due reminders, 'list' to show all.",
        "text": "The reminder text (required for action='set').",
        "due": "Due datetime as 'YYYY-MM-DD HH:MM' in UTC (required for action='set').",
    }

    def execute(self, params: dict, context: dict) -> str:
        action = params.get("action", "set")
        memory_manager = context.get("memory")

        if memory_manager is None:
            return "[reminder: memory manager not available in context]"

        if action == "set":
            return self._set(params, memory_manager)
        elif action == "check":
            return self._check(memory_manager)
        elif action == "list":
            return self._list(memory_manager)
        return f"[reminder: unknown action '{action}'. Use 'set', 'check', or 'list'.]"

    def _set(self, params: dict, memory_manager) -> str:
        text = params.get("text", "")
        due = params.get("due", "")
        if not text:
            return "[reminder: no text provided]"
        if not due:
            return "[reminder: no due datetime provided (use 'YYYY-MM-DD HH:MM')]"

        # Validate format
        try:
            datetime.strptime(due, "%Y-%m-%d %H:%M")
        except ValueError:
            return f"[reminder: invalid date format '{due}'. Use 'YYYY-MM-DD HH:MM']"

        entry = f"\n{_REMINDER_PREFIX}[{due}] {text}"
        memory_manager.append_memory("memory", entry)
        logger.info("Reminder set", extra={"due": due, "text": text[:50]})
        return f"Reminder set for {due} UTC: {text}"

    def _check(self, memory_manager) -> str:
        """Return reminders that are due (past current time)."""
        now = datetime.now(timezone.utc)
        content = memory_manager.read_memory("memory")
        due_reminders = []

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith(_REMINDER_PREFIX):
                continue
            # Parse: - [reminder][YYYY-MM-DD HH:MM] text
            rest = stripped[len(_REMINDER_PREFIX):]
            if not rest.startswith("["):
                continue
            try:
                close = rest.index("]")
                due_str = rest[1:close]
                text = rest[close + 1:].strip()
                due_dt = datetime.strptime(due_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                if due_dt <= now:
                    due_reminders.append(f"- **{due_str}**: {text}")
            except (ValueError, IndexError):
                continue

        if not due_reminders:
            return "No due reminders."
        return "### Due Reminders\n\n" + "\n".join(due_reminders)

    def _list(self, memory_manager) -> str:
        """Return all reminders."""
        content = memory_manager.read_memory("memory")
        reminders = [
            line.strip() for line in content.splitlines()
            if line.strip().startswith(_REMINDER_PREFIX)
        ]
        if not reminders:
            return "No reminders set."
        return "### All Reminders\n\n" + "\n".join(reminders)
