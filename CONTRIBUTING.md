# Contributing to A_OpenClaw

Thanks for your interest in improving A_OpenClaw. This is a small, single-maintainer project — keep changes focused and this stays easy for everyone.

## Getting set up

```bash
git clone https://github.com/damien220/A_OpenClaw
cd A_OpenClaw
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add an API key so you can run the app locally
```

Run the test suite before and after your change:

```bash
python -m pytest tests/ -v
```

## Ground rules

- **One change per PR.** Bug fix, one skill, one adapter — not a bundle.
- **Add tests.** Every skill, source, and adapter in this repo has a matching test class in `tests/`. New code should too. `pytest` uses only stdlib mocks — no new test dependencies.
- **No secrets in commits.** API keys and tokens go in `.env` (gitignored), never in code or config.toml.
- **Match existing style.** No docstring essays — a one-line module docstring and short comments only where the *why* isn't obvious from the code. Look at an existing skill/source/adapter of the same kind before writing a new one.
- **Don't break the sandbox.** `file` and `shell_exec` are deliberately sandboxed/allowlisted. Any change that widens what they can touch needs a clear justification in the PR description.

## Project layout

```
core/       config loading, memory (markdown files), LLM client (Anthropic/OpenAI/Ollama/llama.cpp)
adapters/   channel adapters (CLI, Telegram) behind BaseAdapter
skills/     LLM-invokable capabilities behind BaseSkill, auto-discovered at startup
heartbeat/  scheduled background data gathering behind BaseSource
tests/      one test file per component area, unittest-based
```

## Adding a skill

Create `skills/my_skill.py`:

```python
from skills.base import BaseSkill

class MySkill(BaseSkill):
    name = "my_skill"
    description = "What this skill does — the LLM reads this to decide when to call it."
    parameters = {"param": "Description of param."}

    def execute(self, params, context):
        # context: {"memory": MemoryManager, "config": dict, "llm": LLMClient}
        return "result"
```

It's auto-discovered on the next run — no registration step. Add a `TestMySkillSkill` class in `tests/test_skills.py` mocking any network/subprocess calls.

## Adding a heartbeat source

Subclass `BaseSource` in `heartbeat/sources/`, then register the type key in `heartbeat/source_registry.py`:

```python
from heartbeat.sources.base import BaseSource

class MySource(BaseSource):
    def gather(self) -> str:
        return "### Source: my_source\n\ndata here"
```

```python
# heartbeat/source_registry.py
_SOURCE_TYPES = {..., "mytype": MySource}
```

## Adding an adapter

Subclass `BaseAdapter` in `adapters/`, then call `register_adapter_type("name", MyAdapter)` from `adapter_factory.py`. Keep heavy/optional dependencies (like `python-telegram-bot`) lazily imported inside the adapter, not at module load time, so users who don't need them aren't forced to install them.

## Submitting a change

1. Fork, branch off `main`.
2. Make the change, add/update tests, run `python -m pytest tests/ -v`.
3. If you add a runtime dependency, add it to `requirements.txt` with a version floor (`>=`).
4. Open a PR describing what changed and why. Link any related issue.

## Reporting bugs / requesting features

Open a GitHub issue with steps to reproduce (for bugs) or the use case (for features). For security issues, do not open a public issue — contact the maintainer directly.
