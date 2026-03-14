"""Skill registry — discovers, registers, and invokes skills.

Skills are Python modules in the skills/ directory that define a class
inheriting from BaseSkill. The registry auto-discovers them on init
and generates memory/skill.md so the LLM knows what's available.
"""

import importlib
import pkgutil
import sys
from pathlib import Path

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)

# Skill invocation format the LLM should use
SKILL_INVOKE_FORMAT = """To use a skill, respond with a JSON block:
```skill
{"skill": "<skill_name>", "params": {<parameters>}}
```"""


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        if not skill.name:
            raise ValueError(f"Skill {skill.__class__.__name__} has no name")
        self._skills[skill.name] = skill
        logger.info("Skill registered", extra={"skill": skill.name})

    def unregister(self, name: str) -> None:
        """Remove a skill by name."""
        self._skills.pop(name, None)

    def get(self, name: str) -> BaseSkill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[str]:
        """Return list of registered skill names."""
        return list(self._skills.keys())

    def invoke(self, name: str, params: dict, context: dict | None = None) -> str:
        """Invoke a skill by name with the given parameters.

        Returns the skill's result string, or an error message if the skill
        is not found or execution fails.
        """
        skill = self._skills.get(name)
        if skill is None:
            logger.warning("Skill not found", extra={"skill": name})
            return f"[Error: skill '{name}' not found. Available: {', '.join(self._skills)}]"

        ctx = context or {}
        logger.info("Skill invoked", extra={"skill": name, "params": list(params.keys())})

        try:
            result = skill.execute(params, ctx)
            logger.info("Skill completed", extra={"skill": name, "result_len": len(result)})
            return result
        except Exception as e:
            logger.error("Skill execution failed", extra={"skill": name}, exc_info=True)
            return f"[Error executing skill '{name}': {e}]"

    def auto_discover(self, extra_dirs: list[str] | None = None) -> None:
        """Auto-discover and register skill classes from the skills package
        and any extra directories.

        Scans all modules in the skills/ directory for classes that inherit
        from BaseSkill (excluding BaseSkill itself). Then scans extra_dirs
        (e.g. custom_skills/) so users can add skills without modifying the
        core codebase.

        Args:
            extra_dirs: Additional directories to scan for skill .py files.
        """
        # Built-in skills from skills/ package
        skills_dir = Path(__file__).parent
        for importer, modname, ispkg in pkgutil.iter_modules([str(skills_dir)]):
            if modname in ("base", "registry", "__init__"):
                continue
            try:
                mod = importlib.import_module(f"skills.{modname}")
                self._register_from_module(mod, f"skills.{modname}")
            except Exception as e:
                logger.warning("Failed to load skill module", extra={"module": modname, "error": str(e)})

        # Custom skills from extra directories
        for extra_dir in extra_dirs or []:
            extra_path = Path(extra_dir)
            if not extra_path.is_dir():
                continue
            if str(extra_path) not in sys.path:
                sys.path.insert(0, str(extra_path))
            for importer, modname, ispkg in pkgutil.iter_modules([str(extra_path)]):
                if modname.startswith("_"):
                    continue
                try:
                    mod = importlib.import_module(modname)
                    self._register_from_module(mod, modname)
                except Exception as e:
                    logger.warning("Failed to load custom skill", extra={"module": modname, "dir": str(extra_path), "error": str(e)})

    def _register_from_module(self, mod, mod_name: str) -> None:
        """Register all BaseSkill subclasses found in a module."""
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseSkill)
                and attr is not BaseSkill
            ):
                instance = attr()
                self.register(instance)

    def generate_skill_md(self) -> str:
        """Generate the content for memory/skill.md from registered skills."""
        lines = [
            "# Available Skills",
            "",
            SKILL_INVOKE_FORMAT,
            "",
            "---",
            "",
        ]

        if not self._skills:
            lines.append("No skills registered.")
            return "\n".join(lines)

        for skill in self._skills.values():
            lines.append(f"## {skill.name}")
            lines.append("")
            lines.append(skill.description)
            lines.append("")
            if skill.parameters:
                lines.append("**Parameters:**")
                for param, desc in skill.parameters.items():
                    lines.append(f"- `{param}` — {desc}")
                lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def update_skill_memory(self, memory_manager) -> None:
        """Write the generated skill documentation to memory/skill.md."""
        content = self.generate_skill_md()
        memory_manager.write_memory("skill", content)
        logger.info("skill.md updated", extra={"skill_count": len(self._skills)})
