# Available Skills

To use a skill, respond with a JSON block:
```skill
{"skill": "<skill_name>", "params": {<parameters>}}
```

---

## note

Save or retrieve notes in the knowledge base. Use action='save' to add a note, action='list' to see all notes.

**Parameters:**
- `action` — 'save' to add a note, 'list' to show existing notes.
- `content` — The note content (required for action='save').
- `tag` — Optional tag/category for the note.

---

## reminder

Set a reminder for a future time, or check for due reminders. Reminders are stored in the knowledge base and checked by the heartbeat.

**Parameters:**
- `action` — 'set' to create a reminder, 'check' to list due reminders, 'list' to show all.
- `text` — The reminder text (required for action='set').
- `due` — Due datetime as 'YYYY-MM-DD HH:MM' in UTC (required for action='set').

---

## web_search

Search the web for information and return summarized results.

**Parameters:**
- `query` — The search query string.
- `max_results` — Maximum number of results to return (default: 5).

---
