"""Telegram adapter — uses python-telegram-bot library.

Requires: pip install python-telegram-bot
Configure in config.toml:
    [adapter]
    type = "telegram"
    [adapter.config]
    bot_token = "YOUR_BOT_TOKEN"
    allowlist = []  # empty = allow all, or list of Telegram user IDs
"""

import threading

from adapters.base import BaseAdapter

from logger_pkg import get_logger

logger = get_logger(__name__)


class TelegramAdapter(BaseAdapter):
    """Telegram bot adapter using python-telegram-bot."""

    def __init__(self, config: dict):
        super().__init__(name="telegram", config=config)
        self._app = None
        self._thread: threading.Thread | None = None

    def _build_app(self):
        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot is not installed. "
                "Install it with: pip install python-telegram-bot"
            )

        bot_token = self.config.get("bot_token", "")
        if not bot_token:
            raise RuntimeError("Telegram bot_token is not configured in [adapter.config]")

        app = ApplicationBuilder().token(bot_token).build()

        async def handle_message(update, context):
            if update.message is None or update.message.text is None:
                return

            sender = str(update.message.from_user.id)
            chat_id = str(update.message.chat_id)
            text = update.message.text

            if not self.is_allowed(sender):
                logger.warning("Telegram message from blocked sender", extra={"sender": sender})
                return

            logger.info(
                "Telegram message received",
                extra={"sender": sender, "chat_id": chat_id, "message_len": len(text)},
            )

            if self._message_handler is None:
                return

            metadata = {
                "adapter": "telegram",
                "chat_id": chat_id,
                "sender": sender,
                "username": update.message.from_user.username or "",
            }

            try:
                response = self._message_handler(text, sender, metadata)
                await update.message.reply_text(response)
                logger.info("Telegram response sent", extra={"chat_id": chat_id, "response_len": len(response)})
            except Exception:
                logger.error("Telegram handler failed", exc_info=True)
                await update.message.reply_text("[Error processing your message]")

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        return app

    def start(self) -> None:
        """Start the Telegram bot polling. Blocks the calling thread."""
        self._app = self._build_app()
        logger.info("Telegram adapter started")
        self._app.run_polling()

    def start_background(self) -> threading.Thread:
        """Start the Telegram bot in a background thread."""
        self._thread = threading.Thread(target=self.start, daemon=True, name="telegram-adapter")
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        if self._app:
            self._app.stop()
        logger.info("Telegram adapter stopped")

    def send(self, message: str, target: str) -> None:
        """Send a message to a Telegram chat ID."""
        if self._app is None:
            logger.warning("Cannot send: Telegram adapter not started")
            return

        import asyncio

        async def _send():
            await self._app.bot.send_message(chat_id=target, text=message)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_send())
        except RuntimeError:
            asyncio.run(_send())

        logger.info("Telegram outbound message", extra={"target": target, "message_len": len(message)})
