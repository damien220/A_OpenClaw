"""Tests for core components: config loader, memory manager, LLM client."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.config_loader import load_config, validate_config


class TestConfigLoader(unittest.TestCase):

    def test_loads_default_config(self):
        config = load_config()
        self.assertIn("app", config)
        self.assertIn("llm", config)
        self.assertIn("memory", config)
        self.assertEqual(config["app"]["name"], "a_openclaw")

    def test_env_override(self):
        with patch.dict(os.environ, {"A_OPENCLAW_LLM_PROVIDER": "ollama"}):
            config = load_config()
            self.assertEqual(config["llm"]["provider"], "ollama")

    def test_missing_config_file_returns_empty(self):
        config = load_config(config_path=Path("/nonexistent/config.toml"))
        # Should not crash, returns env overrides only
        self.assertIsInstance(config, dict)


class TestConfigValidation(unittest.TestCase):

    def test_valid_config(self):
        config = load_config()
        errors = validate_config(config)
        self.assertEqual(errors, [])

    def test_invalid_provider(self):
        config = load_config()
        config["llm"]["provider"] = "invalid_provider"
        errors = validate_config(config)
        self.assertTrue(any("provider" in e for e in errors))

    def test_invalid_max_tokens(self):
        config = load_config()
        config["llm"]["max_response_tokens"] = -1
        errors = validate_config(config)
        self.assertTrue(any("max_response_tokens" in e for e in errors))

    def test_invalid_heartbeat_interval(self):
        config = load_config()
        config["heartbeat"]["interval_seconds"] = 0
        errors = validate_config(config)
        self.assertTrue(any("interval_seconds" in e for e in errors))

    def test_invalid_log_format(self):
        config = load_config()
        config["logging"]["format"] = "xml"
        errors = validate_config(config)
        self.assertTrue(any("format" in e for e in errors))

    def test_source_missing_type(self):
        config = load_config()
        config["heartbeat"]["sources"] = [{"name": "test"}]
        errors = validate_config(config)
        self.assertTrue(any("type" in e for e in errors))


class TestMemoryManager(unittest.TestCase):

    def setUp(self):
        self.config = load_config()
        from core.memory_manager import MemoryManager
        self.memory = MemoryManager(self.config)

    def test_read_write_memory(self):
        self.memory.write_memory("memory", "test content")
        content = self.memory.read_memory("memory")
        self.assertIn("test content", content)

    def test_append_memory(self):
        self.memory.write_memory("memory", "line1")
        self.memory.append_memory("memory", "line2")
        content = self.memory.read_memory("memory")
        self.assertIn("line1", content)
        self.assertIn("line2", content)

    def test_unknown_key_raises(self):
        with self.assertRaises(ValueError):
            self.memory.read_memory("nonexistent")

    def test_build_context(self):
        context = self.memory.build_context()
        self.assertIsInstance(context, str)

    def test_log_interaction(self):
        path = self.memory.log_interaction("test", "test entry")
        self.assertTrue(path.exists())
        content = path.read_text()
        self.assertIn("test entry", content)

    def test_compact_memory_noop_when_small(self):
        self.memory.write_memory("memory", "small content")
        result = self.memory.compact_memory()
        self.assertFalse(result)

    def test_compact_memory_trims_when_large(self):
        # Set a very low limit for testing
        self.memory._max_memory_chars = 100
        large_content = "line\n" * 1000
        self.memory.write_memory("memory", large_content)
        result = self.memory.compact_memory()
        self.assertTrue(result)
        content = self.memory.read_memory("memory")
        self.assertIn("compacted", content)
        self.assertLess(len(content), len(large_content))

    def test_context_truncation(self):
        self.memory._max_context_chars = 200
        self.memory.write_memory("memory", "x" * 500)
        context = self.memory.build_context()
        # The Knowledge Base section should be truncated
        self.assertIn("truncated", context)
        # Full context includes user.md and skill.md too, but memory portion is cut
        kb_start = context.find("Knowledge Base")
        self.assertGreater(kb_start, -1)


class TestLLMClient(unittest.TestCase):

    def test_init_defaults(self):
        from core.llm_client import LLMClient
        config = load_config()
        client = LLMClient(config)
        self.assertEqual(client._provider, "anthropic")
        self.assertIsNotNone(client._model)

    def test_ollama_defaults(self):
        from core.llm_client import LLMClient
        config = {"llm": {"provider": "ollama"}}
        client = LLMClient(config)
        self.assertEqual(client._model, "llama3.2")
        self.assertIn("11434", client._base_url)

    def test_llamacpp_defaults(self):
        from core.llm_client import LLMClient
        config = {"llm": {"provider": "llamacpp"}}
        client = LLMClient(config)
        self.assertEqual(client._model, "default")
        self.assertIn("8080", client._base_url)

    def test_unknown_provider_raises_on_get_client(self):
        from core.llm_client import LLMClient
        config = {"llm": {"provider": "unknown_provider"}}
        client = LLMClient(config)
        with self.assertRaises(ValueError):
            client._get_client()

    def test_missing_api_key_raises(self):
        from core.llm_client import LLMClient
        config = {"llm": {"provider": "anthropic", "model": "test"}}
        client = LLMClient(config)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with self.assertRaises((RuntimeError, ModuleNotFoundError)):
                # RuntimeError if anthropic is installed but key missing
                # ModuleNotFoundError if anthropic package not installed
                client._get_client()


if __name__ == "__main__":
    unittest.main()
