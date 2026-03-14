"""Base interface for skills."""

from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """A skill that the LLM can invoke to perform an action."""

    name: str = ""
    description: str = ""
    parameters: dict[str, str] = {}  # param_name -> description

    @abstractmethod
    def execute(self, params: dict, context: dict) -> str:
        """Run the skill and return the result as a string.

        Args:
            params: Parameters extracted from the LLM's invocation.
            context: Runtime context (memory, config, adapter reference, etc.).

        Returns:
            Result string to feed back to the LLM or send to the user.
        """
        ...
