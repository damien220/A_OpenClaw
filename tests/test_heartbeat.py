"""Tests for the heartbeat engine and data sources."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config_loader import load_config
from heartbeat.sources.base import BaseSource
from heartbeat.sources.file_source import FileSource
from heartbeat.source_registry import create_source, register_source_type


class TestSourceRegistry(unittest.TestCase):

    def test_create_file_source(self):
        src = create_source({"name": "test", "type": "file", "path": ".", "pattern": "*.md"})
        self.assertIsInstance(src, FileSource)
        self.assertEqual(src.name, "test")

    def test_create_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            create_source({"name": "x", "type": "nonexistent"})

    def test_register_custom_source(self):
        class CustomSource(BaseSource):
            def gather(self):
                return "custom data"

        register_source_type("custom", CustomSource)
        src = create_source({"name": "c", "type": "custom"})
        self.assertEqual(src.gather(), "custom data")


class TestFileSource(unittest.TestCase):

    def test_gather_directory(self):
        src = FileSource("test", {"path": "memory", "pattern": "*.md"})
        result = src.gather()
        self.assertIn("Source: test", result)

    def test_gather_missing_path(self):
        src = FileSource("test", {"path": "/nonexistent/path"})
        result = src.gather()
        self.assertIn("does not exist", result)

    def test_gather_single_file(self):
        src = FileSource("test", {"path": "config/config.toml"})
        result = src.gather()
        self.assertIn("Source: test", result)

    def test_gather_empty_dir(self):
        src = FileSource("test", {"path": ".", "pattern": "*.nonexistent_extension"})
        result = src.gather()
        self.assertEqual(result, "")


class TestAPISource(unittest.TestCase):

    def test_empty_url(self):
        from heartbeat.sources.api_source import APISource
        src = APISource("test", {"url": ""})
        self.assertEqual(src.gather(), "")

    @patch("heartbeat.sources.api_source.urlopen")
    def test_successful_fetch(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"key": "value"}'
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        from heartbeat.sources.api_source import APISource
        src = APISource("test", {"url": "http://example.com/api"})
        result = src.gather()
        self.assertIn("Source: test", result)
        self.assertIn("key", result)


class TestRSSSource(unittest.TestCase):

    def test_empty_url(self):
        from heartbeat.sources.rss_source import RSSSource
        src = RSSSource("test", {"url": ""})
        self.assertEqual(src.gather(), "")


class TestHeartbeatRunner(unittest.TestCase):

    def _make_config(self, sources=None):
        return {
            "llm": {"provider": "anthropic", "model": "test"},
            "memory": {
                "directory": "memory",
                "user_file": "user.md",
                "memory_file": "memory.md",
                "skill_file": "skill.md",
                "logs_directory": "memory/logs",
                "max_log_files": 100,
            },
            "heartbeat": {
                "enabled": False,
                "interval_seconds": 60,
                "sources": sources or [],
            },
        }

    def test_init_no_sources(self):
        from heartbeat.runner import HeartbeatRunner
        runner = HeartbeatRunner(self._make_config())
        self.assertEqual(len(runner._sources), 0)

    def test_init_with_file_source(self):
        from heartbeat.runner import HeartbeatRunner
        sources = [{"name": "test", "type": "file", "path": "memory", "pattern": "*.md"}]
        runner = HeartbeatRunner(self._make_config(sources))
        self.assertEqual(len(runner._sources), 1)

    def test_gather_all_empty(self):
        from heartbeat.runner import HeartbeatRunner
        runner = HeartbeatRunner(self._make_config())
        result = runner.gather_all()
        self.assertEqual(result, "")

    def test_gather_all_with_source(self):
        from heartbeat.runner import HeartbeatRunner
        sources = [{"name": "test", "type": "file", "path": "memory", "pattern": "*.md"}]
        runner = HeartbeatRunner(self._make_config(sources))
        result = runner.gather_all()
        self.assertIn("Source: test", result)

    def test_process_empty_data(self):
        from heartbeat.runner import HeartbeatRunner
        runner = HeartbeatRunner(self._make_config())
        result = runner.process("")
        self.assertEqual(result["summary"], "No data from sources.")

    def test_set_adapter(self):
        from heartbeat.runner import HeartbeatRunner
        runner = HeartbeatRunner(self._make_config())
        adapter = MagicMock()
        runner.set_adapter(adapter)
        self.assertIs(runner._adapter, adapter)

    def test_stop_event(self):
        from heartbeat.runner import HeartbeatRunner
        runner = HeartbeatRunner(self._make_config())
        self.assertFalse(runner._stop_event.is_set())
        runner.stop()
        self.assertTrue(runner._stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
