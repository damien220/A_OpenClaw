"""Base adapter interface for channel adapters."""

from abc import ABC, abstractmethod
from typing import Callable


class BaseAdapter(ABC):
    """Interface that all channel adapters must implement.

    The message handler callback signature:
        callback(message: str, sender: str, metadata: dict) -> str
    It receives the incoming message text, sender identifier, and platform-specific
    metadata. It must return the response string to send back.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self._message_handler: Callable[[str, str, dict], str] | None = None

    def on_message(self, callback: Callable[[str, str, dict], str]) -> None:
        """Register the handler that processes incoming messages.

        Args:
            callback: Function(message, sender, metadata) -> response_text
        """
        self._message_handler = callback

    @abstractmethod
    def start(self) -> None:
        """Start listening for messages. May block (e.g., polling loop)."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop the adapter gracefully."""
        ...

    @abstractmethod
    def send(self, message: str, target: str) -> None:
        """Send an outbound message to a target (chat ID, channel, etc.)."""
        ...

    def is_allowed(self, sender: str) -> bool:
        """Check if a sender is allowed based on config allowlist.

        If no allowlist is configured, all senders are allowed.
        """
        allowlist = self.config.get("allowlist", [])
        if not allowlist:
            return True
        return sender in allowlist
