"""Tests for the adapter system.

These tests verify the adapter interface, factory, CLI adapter behavior,
message handler wiring, allowlist filtering, and heartbeat integration.
Telegram adapter tests are included but require python-telegram-bot to run.

NOTE: LLM API tokens are NOT configured in the test environment.
Tests that would hit a real LLM use mocks or skip.
"""

import threading
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from adapters.base import BaseAdapter
from adapters.cli_adapter import CLIAdapter
from adapters.adapter_factory import create_adapter, register_adapter_type


class DummyAdapter(BaseAdapter):
    """Minimal concrete adapter for testing the base interface."""

    def __init__(self, config: dict):
        super().__init__(name="dummy", config=config)
        self.started = False
        self.stopped = False
        self.sent_messages: list[tuple[str, str]] = []

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def send(self, message: str, target: str):
        self.sent_messages.append((message, target))


class TestBaseAdapter(unittest.TestCase):
    """Tests for the BaseAdapter interface."""

    def test_on_message_registers_handler(self):
        adapter = DummyAdapter(config={})
        handler = MagicMock(return_value="response")
        adapter.on_message(handler)
        self.assertIs(adapter._message_handler, handler)

    def test_send_records_message(self):
        adapter = DummyAdapter(config={})
        adapter.send("hello", "user1")
        adapter.send("world", "user2")
        self.assertEqual(adapter.sent_messages, [("hello", "user1"), ("world", "user2")])

    def test_start_stop(self):
        adapter = DummyAdapter(config={})
        adapter.start()
        self.assertTrue(adapter.started)
        adapter.stop()
        self.assertTrue(adapter.stopped)

    def test_is_allowed_empty_allowlist(self):
        """Empty allowlist means everyone is allowed."""
        adapter = DummyAdapter(config={"allowlist": []})
        self.assertTrue(adapter.is_allowed("anyone"))
        self.assertTrue(adapter.is_allowed("12345"))

    def test_is_allowed_no_allowlist_key(self):
        """No allowlist key in config means everyone is allowed."""
        adapter = DummyAdapter(config={})
        self.assertTrue(adapter.is_allowed("anyone"))

    def test_is_allowed_with_allowlist(self):
        adapter = DummyAdapter(config={"allowlist": ["user1", "user2"]})
        self.assertTrue(adapter.is_allowed("user1"))
        self.assertTrue(adapter.is_allowed("user2"))
        self.assertFalse(adapter.is_allowed("user3"))
        self.assertFalse(adapter.is_allowed(""))

    def test_name_and_config(self):
        adapter = DummyAdapter(config={"key": "value"})
        self.assertEqual(adapter.name, "dummy")
        self.assertEqual(adapter.config["key"], "value")


class TestCLIAdapter(unittest.TestCase):
    """Tests for the CLI adapter."""

    def test_init_defaults(self):
        adapter = CLIAdapter(config={})
        self.assertEqual(adapter.name, "cli")
        self.assertFalse(adapter._running)

    def test_send_prints_to_stdout(self, ):
        adapter = CLIAdapter(config={})
        with patch("builtins.print") as mock_print:
            adapter.send("hello", "default")
            mock_print.assert_called_once_with("[default] hello")

    def test_stop_sets_running_false(self):
        adapter = CLIAdapter(config={})
        adapter._running = True
        adapter.stop()
        self.assertFalse(adapter._running)

    def test_start_no_handler_prints_warning(self):
        """Start with no handler registered should print a warning for each input."""
        adapter = CLIAdapter(config={"prompt": "test> "})
        with patch("builtins.input", side_effect=["hello", "quit"]):
            with patch("builtins.print") as mock_print:
                adapter.start()
                # Should print the no-handler warning for "hello", then "Bye." for "quit"
                calls = [str(c) for c in mock_print.call_args_list]
                self.assertTrue(any("No message handler" in c for c in calls))

    def test_start_with_handler(self):
        """Messages should flow through the registered handler."""
        adapter = CLIAdapter(config={})
        handler = MagicMock(return_value="echo: hello")
        adapter.on_message(handler)

        with patch("builtins.input", side_effect=["hello", "quit"]):
            with patch("builtins.print"):
                adapter.start()

        handler.assert_called_once_with("hello", "cli-user", {"adapter": "cli"})

    def test_start_exits_on_eof(self):
        adapter = CLIAdapter(config={})
        with patch("builtins.input", side_effect=EOFError):
            with patch("builtins.print"):
                adapter.start()
        self.assertFalse(adapter._running)

    def test_start_exits_on_keyboard_interrupt(self):
        adapter = CLIAdapter(config={})
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with patch("builtins.print"):
                adapter.start()
        self.assertFalse(adapter._running)

    def test_start_exits_on_empty_input(self):
        adapter = CLIAdapter(config={})
        with patch("builtins.input", side_effect=["", "quit"]):
            with patch("builtins.print"):
                adapter.start()
        self.assertFalse(adapter._running)

    def test_handler_exception_prints_error(self):
        adapter = CLIAdapter(config={})
        handler = MagicMock(side_effect=RuntimeError("boom"))
        adapter.on_message(handler)

        with patch("builtins.input", side_effect=["hello", "quit"]):
            with patch("builtins.print") as mock_print:
                adapter.start()
                calls = [str(c) for c in mock_print.call_args_list]
                self.assertTrue(any("Error" in c for c in calls))


class TestAdapterFactory(unittest.TestCase):
    """Tests for the adapter factory."""

    def test_default_to_cli(self):
        """No adapter type configured should default to CLI."""
        config = {"adapter": {"type": "", "config": {}}}
        adapter = create_adapter(config)
        self.assertIsInstance(adapter, CLIAdapter)

    def test_explicit_cli(self):
        config = {"adapter": {"type": "cli", "config": {"prompt": ">> "}}}
        adapter = create_adapter(config)
        self.assertIsInstance(adapter, CLIAdapter)
        self.assertEqual(adapter.config["prompt"], ">> ")

    def test_no_adapter_section(self):
        """Missing [adapter] section should default to CLI."""
        adapter = create_adapter({})
        self.assertIsInstance(adapter, CLIAdapter)

    def test_unknown_type_raises(self):
        config = {"adapter": {"type": "nonexistent", "config": {}}}
        with self.assertRaises(ValueError) as ctx:
            create_adapter(config)
        self.assertIn("nonexistent", str(ctx.exception))

    def test_register_custom_adapter(self):
        register_adapter_type("dummy", DummyAdapter)
        config = {"adapter": {"type": "dummy", "config": {"key": "val"}}}
        adapter = create_adapter(config)
        self.assertIsInstance(adapter, DummyAdapter)
        self.assertEqual(adapter.config["key"], "val")

    def test_telegram_lazy_import(self):
        """Telegram adapter should be available via lazy import."""
        config = {"adapter": {"type": "telegram", "config": {"bot_token": "test-token"}}}
        # This test just verifies the factory can resolve "telegram" to the class
        # without actually starting the bot (which would fail without a real token)
        try:
            adapter = create_adapter(config)
            self.assertEqual(adapter.name, "telegram")
        except RuntimeError as e:
            # If python-telegram-bot is not installed, that's expected
            if "dependencies" not in str(e):
                raise


class TestAdapterHeartbeatIntegration(unittest.TestCase):
    """Tests that heartbeat outbound messages route through the adapter."""

    def test_heartbeat_sends_through_adapter(self):
        """execute_actions should call adapter.send for each message."""
        from heartbeat.runner import HeartbeatRunner

        config = {
            "llm": {"provider": "anthropic"},
            "memory": {
                "directory": "memory",
                "user_file": "user.md",
                "memory_file": "memory.md",
                "skill_file": "skill.md",
                "logs_directory": "memory/logs",
                "max_log_files": 100,
            },
            "heartbeat": {"enabled": False, "interval_seconds": 60, "sources": []},
        }
        runner = HeartbeatRunner(config)
        adapter = DummyAdapter(config={})
        runner.set_adapter(adapter)

        actions = {
            "summary": "test",
            "memory_updates": "",
            "messages": ["msg1", "msg2"],
            "target": "channel-1",
        }
        runner.execute_actions(actions)

        self.assertEqual(adapter.sent_messages, [("msg1", "channel-1"), ("msg2", "channel-1")])

    def test_heartbeat_no_adapter_no_crash(self):
        """execute_actions with messages but no adapter should not crash."""
        from heartbeat.runner import HeartbeatRunner

        config = {
            "llm": {"provider": "anthropic"},
            "memory": {
                "directory": "memory",
                "user_file": "user.md",
                "memory_file": "memory.md",
                "skill_file": "skill.md",
                "logs_directory": "memory/logs",
                "max_log_files": 100,
            },
            "heartbeat": {"enabled": False, "interval_seconds": 60, "sources": []},
        }
        runner = HeartbeatRunner(config)
        # No adapter set
        actions = {"summary": "test", "memory_updates": "", "messages": ["msg1"]}
        runner.execute_actions(actions)  # Should not raise


class TestMessageHandlerFlow(unittest.TestCase):
    """Tests for the full message flow: adapter -> handler -> response."""

    def test_handler_receives_correct_args(self):
        adapter = DummyAdapter(config={})
        received = {}

        def handler(message, sender, metadata):
            received["message"] = message
            received["sender"] = sender
            received["metadata"] = metadata
            return "ok"

        adapter.on_message(handler)
        result = adapter._message_handler("hello", "user1", {"adapter": "test"})

        self.assertEqual(result, "ok")
        self.assertEqual(received["message"], "hello")
        self.assertEqual(received["sender"], "user1")
        self.assertEqual(received["metadata"]["adapter"], "test")

    def test_handler_return_value_is_response(self):
        adapter = DummyAdapter(config={})
        adapter.on_message(lambda m, s, md: f"echo: {m}")
        result = adapter._message_handler("test", "u", {})
        self.assertEqual(result, "echo: test")


if __name__ == "__main__":
    unittest.main()
