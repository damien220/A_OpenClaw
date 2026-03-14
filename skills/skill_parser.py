"""Parse LLM responses for skill invocation blocks.

The LLM is instructed to use this format:
```skill
{"skill": "skill_name", "params": {"key": "value"}}
```

This module extracts those blocks, executes the skills, and returns
a modified response with skill results injected.
"""

import json
import re

from skills.registry import SkillRegistry

from logger_pkg import get_logger

logger = get_logger(__name__)

_SKILL_BLOCK_RE = re.compile(
    r"```skill\s*\n(.*?)\n```",
    re.DOTALL,
)


def extract_skill_calls(text: str) -> list[dict]:
    """Extract skill invocation blocks from LLM response text.

    Returns a list of dicts with 'skill' and 'params' keys.
    """
    calls = []
    for match in _SKILL_BLOCK_RE.finditer(text):
        raw = match.group(1).strip()
        try:
            parsed = json.loads(raw)
            if "skill" in parsed:
                calls.append({
                    "skill": parsed["skill"],
                    "params": parsed.get("params", {}),
                    "match": match,
                })
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in skill block", extra={"raw": raw[:200]})
    return calls


def process_skill_calls(
    response: str,
    registry: SkillRegistry,
    context: dict | None = None,
    max_rounds: int = 3,
) -> str:
    """Process all skill invocation blocks in an LLM response.

    Replaces each ```skill block with the skill's execution result.
    Supports chaining: if a skill result contains another skill block,
    it will be processed up to max_rounds times.

    Returns the final response with all skill blocks resolved.
    """
    for round_num in range(max_rounds):
        calls = extract_skill_calls(response)
        if not calls:
            break

        logger.info(
            "Processing skill calls",
            extra={"round": round_num + 1, "call_count": len(calls)},
        )

        # Process in reverse order so string indices remain valid
        for call in reversed(calls):
            skill_name = call["skill"]
            params = call["params"]
            match = call["match"]

            result = registry.invoke(skill_name, params, context)

            # Replace the skill block with the result
            response = response[:match.start()] + result + response[match.end():]

    return response
