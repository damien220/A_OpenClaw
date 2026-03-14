"""CLI adapter — interactive terminal interface.

This is the default adapter. It requires no external dependencies and provides
a simple input/output loop for local testing and personal use.
"""

from adapters.base import BaseAdapter

from logger_pkg import get_logger

logger = get_logger(__name__)


class CLIAdapter(BaseAdapter):
    """Interactive command-line adapter."""

    def __init__(self, config: dict):
        super().__init__(name="cli", config=config)
        self._running = False

    def start(self) -> None:
        """Run the interactive CLI loop. Blocks until quit."""
        self._running = True
        logger.info("CLI adapter started")

        prompt = self.config.get("prompt", "> ")
        print("Type a message (or 'quit' to exit):")

        while self._running:
            try:
                user_input = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not user_input or user_input.lower() in ("quit", "exit"):
                print("Bye.")
                break

            # Pass through to handler
            if self._message_handler is None:
                print("[No message handler registered]")
                continue

            try:
                response = self._message_handler(user_input, "cli-user", {"adapter": "cli"})
                print(f"\n{response}\n")
            except Exception as e:
                logger.error("CLI message handler failed", exc_info=True)
                print(f"[Error: {e}]")

        self._running = False
        logger.info("CLI adapter stopped")

    def stop(self) -> None:
        self._running = False

    def send(self, message: str, target: str) -> None:
        """Print outbound message to terminal."""
        print(f"[{target}] {message}")
        logger.debug("CLI outbound message", extra={"target": target, "message_len": len(message)})
