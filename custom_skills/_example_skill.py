"""Example custom skill — copy and rename this file to create your own.

Drop any .py file in this directory that defines a BaseSkill subclass.
It will be auto-discovered on next app start (no rebuild needed).

Files starting with _ are ignored, so this example won't be loaded.
"""

from skills.base import BaseSkill


class HelloSkill(BaseSkill):
    name = "hello"
    description = "Say hello — a minimal example skill."
    parameters = {"name": "Who to greet (default: World)"}

    def execute(self, params: dict, context: dict) -> str:
        name = params.get("name", "World")
        return f"Hello, {name}! This is a custom skill."
