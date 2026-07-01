"""Tests for the skills system: registry, parser, and built-in skills."""

import unittest
from unittest.mock import MagicMock

from core.config_loader import load_config
from core.memory_manager import MemoryManager
from skills.base import BaseSkill
from skills.registry import SkillRegistry
from skills.skill_parser import extract_skill_calls, process_skill_calls


class EchoSkill(BaseSkill):
    name = "echo"
    description = "Echoes the input back."
    parameters = {"text": "Text to echo."}

    def execute(self, params, context):
        return f"Echo: {params.get('text', '')}"


class TestSkillRegistry(unittest.TestCase):

    def test_register_and_invoke(self):
        registry = SkillRegistry()
        registry.register(EchoSkill())
        result = registry.invoke("echo", {"text": "hello"})
        self.assertEqual(result, "Echo: hello")

    def test_list_skills(self):
        registry = SkillRegistry()
        registry.register(EchoSkill())
        self.assertEqual(registry.list_skills(), ["echo"])

    def test_invoke_unknown_skill(self):
        registry = SkillRegistry()
        result = registry.invoke("nonexistent", {})
        self.assertIn("not found", result)

    def test_unregister(self):
        registry = SkillRegistry()
        registry.register(EchoSkill())
        registry.unregister("echo")
        self.assertEqual(registry.list_skills(), [])

    def test_auto_discover(self):
        registry = SkillRegistry()
        registry.auto_discover()
        names = registry.list_skills()
        self.assertIn("note", names)
        self.assertIn("reminder", names)
        self.assertIn("web_search", names)
        self.assertIn("shell_exec", names)

    def test_generate_skill_md(self):
        registry = SkillRegistry()
        registry.register(EchoSkill())
        md = registry.generate_skill_md()
        self.assertIn("echo", md)
        self.assertIn("Echoes the input back", md)
        self.assertIn("text", md)

    def test_generate_skill_md_empty(self):
        registry = SkillRegistry()
        md = registry.generate_skill_md()
        self.assertIn("No skills registered", md)

    def test_skill_execution_error(self):
        class BadSkill(BaseSkill):
            name = "bad"
            description = "Always fails."
            parameters = {}
            def execute(self, params, context):
                raise RuntimeError("boom")

        registry = SkillRegistry()
        registry.register(BadSkill())
        result = registry.invoke("bad", {})
        self.assertIn("Error", result)
        self.assertIn("boom", result)

    def test_register_no_name_raises(self):
        class NoName(BaseSkill):
            name = ""
            description = "No name."
            parameters = {}
            def execute(self, params, context):
                return ""

        registry = SkillRegistry()
        with self.assertRaises(ValueError):
            registry.register(NoName())


class TestSkillParser(unittest.TestCase):

    def test_extract_single_call(self):
        text = 'Some text\n```skill\n{"skill": "echo", "params": {"text": "hi"}}\n```\nMore text'
        calls = extract_skill_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["skill"], "echo")
        self.assertEqual(calls[0]["params"]["text"], "hi")

    def test_extract_multiple_calls(self):
        text = '```skill\n{"skill": "a", "params": {}}\n```\ntext\n```skill\n{"skill": "b", "params": {}}\n```'
        calls = extract_skill_calls(text)
        self.assertEqual(len(calls), 2)

    def test_extract_no_calls(self):
        calls = extract_skill_calls("Just regular text with no skill blocks")
        self.assertEqual(calls, [])

    def test_extract_invalid_json(self):
        text = '```skill\nnot valid json\n```'
        calls = extract_skill_calls(text)
        self.assertEqual(calls, [])

    def test_process_replaces_block(self):
        registry = SkillRegistry()
        registry.register(EchoSkill())
        text = 'Before\n```skill\n{"skill": "echo", "params": {"text": "world"}}\n```\nAfter'
        result = process_skill_calls(text, registry)
        self.assertIn("Echo: world", result)
        self.assertIn("Before", result)
        self.assertIn("After", result)
        self.assertNotIn("```skill", result)

    def test_process_chaining(self):
        """If a skill result contains another skill block, it should be processed."""
        class ChainSkill(BaseSkill):
            name = "chain"
            description = "Returns another skill block."
            parameters = {}
            def execute(self, params, context):
                return '```skill\n{"skill": "echo", "params": {"text": "chained"}}\n```'

        registry = SkillRegistry()
        registry.register(EchoSkill())
        registry.register(ChainSkill())

        text = '```skill\n{"skill": "chain", "params": {}}\n```'
        result = process_skill_calls(text, registry, max_rounds=3)
        self.assertIn("Echo: chained", result)

    def test_process_max_rounds(self):
        """Chaining should stop after max_rounds."""
        class InfiniteSkill(BaseSkill):
            name = "infinite"
            description = "Always returns another skill call."
            parameters = {}
            def execute(self, params, context):
                return '```skill\n{"skill": "infinite", "params": {}}\n```'

        registry = SkillRegistry()
        registry.register(InfiniteSkill())

        text = '```skill\n{"skill": "infinite", "params": {}}\n```'
        result = process_skill_calls(text, registry, max_rounds=2)
        # After 2 rounds, there's still a block left (not processed)
        self.assertIn("```skill", result)


class TestNoteTakerSkill(unittest.TestCase):

    def setUp(self):
        self.config = load_config()
        self.memory = MemoryManager(self.config)
        self.ctx = {"memory": self.memory}

    def test_save_and_list(self):
        from skills.note_taker import NoteTakerSkill
        skill = NoteTakerSkill()

        result = skill.execute({"action": "save", "content": "test note", "tag": "test"}, self.ctx)
        self.assertIn("saved", result.lower())

        result = skill.execute({"action": "list"}, self.ctx)
        self.assertIn("test note", result)

    def test_save_no_content(self):
        from skills.note_taker import NoteTakerSkill
        skill = NoteTakerSkill()
        result = skill.execute({"action": "save"}, self.ctx)
        self.assertIn("no content", result)

    def test_no_memory_manager(self):
        from skills.note_taker import NoteTakerSkill
        skill = NoteTakerSkill()
        result = skill.execute({"action": "list"}, {})
        self.assertIn("not available", result)


class TestReminderSkill(unittest.TestCase):

    def setUp(self):
        self.config = load_config()
        self.memory = MemoryManager(self.config)
        self.ctx = {"memory": self.memory}

    def test_set_and_list(self):
        from skills.reminder import ReminderSkill
        skill = ReminderSkill()

        result = skill.execute({"action": "set", "text": "do stuff", "due": "2020-01-01 09:00"}, self.ctx)
        self.assertIn("Reminder set", result)

        result = skill.execute({"action": "list"}, self.ctx)
        self.assertIn("do stuff", result)

    def test_check_due(self):
        from skills.reminder import ReminderSkill
        skill = ReminderSkill()

        # Set a past reminder
        skill.execute({"action": "set", "text": "past reminder", "due": "2020-01-01 09:00"}, self.ctx)
        result = skill.execute({"action": "check"}, self.ctx)
        self.assertIn("past reminder", result)

    def test_invalid_date(self):
        from skills.reminder import ReminderSkill
        skill = ReminderSkill()
        result = skill.execute({"action": "set", "text": "test", "due": "not-a-date"}, self.ctx)
        self.assertIn("invalid", result.lower())

    def test_no_text(self):
        from skills.reminder import ReminderSkill
        skill = ReminderSkill()
        result = skill.execute({"action": "set", "due": "2030-01-01 09:00"}, self.ctx)
        self.assertIn("no text", result)


class TestWebSearchSkill(unittest.TestCase):

    @staticmethod
    def _mock_response(body: bytes):
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    def test_no_query(self):
        from skills.web_search import WebSearchSkill
        skill = WebSearchSkill()
        result = skill.execute({}, {})
        self.assertIn("no query provided", result)

    def test_brave_search_used_when_api_key_set(self):
        from skills.web_search import WebSearchSkill
        from unittest.mock import patch
        import json

        brave_json = json.dumps(
            {
                "web": {
                    "results": [
                        {
                            "title": "Example Title",
                            "url": "https://example.com",
                            "description": "Example description.",
                        }
                    ]
                }
            }
        ).encode("utf-8")

        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "test-key"}), \
             patch("skills.web_search.urlopen", return_value=self._mock_response(brave_json)) as mock_urlopen:
            skill = WebSearchSkill()
            result = skill.execute({"query": "python asyncio"}, {})

        self.assertIn("Example Title", result)
        self.assertIn("https://example.com", result)
        self.assertIn("Example description.", result)
        sent_request = mock_urlopen.call_args[0][0]
        self.assertEqual(sent_request.get_header("X-subscription-token"), "test-key")

    def test_brave_search_no_results(self):
        from skills.web_search import WebSearchSkill
        from unittest.mock import patch
        import json

        brave_json = json.dumps({"web": {"results": []}}).encode("utf-8")

        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "test-key"}), \
             patch("skills.web_search.urlopen", return_value=self._mock_response(brave_json)):
            skill = WebSearchSkill()
            result = skill.execute({"query": "python asyncio"}, {})

        self.assertIn("No results found", result)

    def test_brave_search_error(self):
        from skills.web_search import WebSearchSkill
        from unittest.mock import patch
        from urllib.error import URLError

        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": "test-key"}), \
             patch("skills.web_search.urlopen", side_effect=URLError("boom")):
            skill = WebSearchSkill()
            result = skill.execute({"query": "python"}, {})

        self.assertIn("web_search error", result)

    def test_falls_back_to_duckduckgo_without_api_key(self):
        from skills.web_search import WebSearchSkill
        from unittest.mock import patch
        import json
        import os

        instant_json = json.dumps(
            {"AbstractText": "Quick answer.", "AbstractSource": "Wikipedia"}
        ).encode("utf-8")

        env = dict(os.environ)
        env.pop("BRAVE_SEARCH_API_KEY", None)
        with patch.dict("os.environ", env, clear=True), \
             patch("skills.web_search.urlopen", return_value=self._mock_response(instant_json)):
            skill = WebSearchSkill()
            result = skill.execute({"query": "python"}, {})

        self.assertIn("Wikipedia", result)
        self.assertIn("Quick answer.", result)

    def test_no_api_key_and_no_abstract_prompts_for_key(self):
        from skills.web_search import WebSearchSkill
        from unittest.mock import patch
        import json
        import os

        empty_instant = json.dumps({"AbstractText": ""}).encode("utf-8")

        env = dict(os.environ)
        env.pop("BRAVE_SEARCH_API_KEY", None)
        with patch.dict("os.environ", env, clear=True), \
             patch("skills.web_search.urlopen", return_value=self._mock_response(empty_instant)):
            skill = WebSearchSkill()
            result = skill.execute({"query": "python"}, {})

        self.assertIn("No results found", result)
        self.assertIn("BRAVE_SEARCH_API_KEY", result)


class TestTranslatorSkill(unittest.TestCase):

    def test_no_text(self):
        from skills.translator import TranslatorSkill
        skill = TranslatorSkill()
        result = skill.execute({"target_language": "French"}, {})
        self.assertIn("no text provided", result)

    def test_no_target_language(self):
        from skills.translator import TranslatorSkill
        skill = TranslatorSkill()
        result = skill.execute({"text": "Hello"}, {})
        self.assertIn("no target_language", result)

    def test_no_llm_in_context(self):
        from skills.translator import TranslatorSkill
        skill = TranslatorSkill()
        result = skill.execute({"text": "Hello", "target_language": "French"}, {})
        self.assertIn("LLM not available", result)

    def test_successful_translation(self):
        from skills.translator import TranslatorSkill
        from unittest.mock import MagicMock
        skill = TranslatorSkill()
        llm = MagicMock()
        llm.send.return_value = "Bonjour"
        result = skill.execute({"text": "Hello", "target_language": "French"}, {"llm": llm})
        self.assertEqual(result, "Bonjour")
        prompt = llm.send.call_args[0][1]
        self.assertIn("French", prompt)
        self.assertIn("Hello", prompt)

    def test_with_source_language(self):
        from skills.translator import TranslatorSkill
        from unittest.mock import MagicMock
        skill = TranslatorSkill()
        llm = MagicMock()
        llm.send.return_value = "Hola"
        skill.execute({"text": "Hello", "target_language": "Spanish", "source_language": "English"}, {"llm": llm})
        prompt = llm.send.call_args[0][1]
        self.assertIn("from English", prompt)

    def test_llm_error(self):
        from skills.translator import TranslatorSkill
        from unittest.mock import MagicMock
        skill = TranslatorSkill()
        llm = MagicMock()
        llm.send.side_effect = RuntimeError("API down")
        result = skill.execute({"text": "Hello", "target_language": "French"}, {"llm": llm})
        self.assertIn("error", result)


class TestSummarizerSkill(unittest.TestCase):

    def test_no_input(self):
        from skills.summarizer import SummarizerSkill
        skill = SummarizerSkill()
        result = skill.execute({}, {})
        self.assertIn("provide 'text' or 'url'", result)

    def test_no_llm_in_context(self):
        from skills.summarizer import SummarizerSkill
        skill = SummarizerSkill()
        result = skill.execute({"text": "Some text"}, {})
        self.assertIn("LLM not available", result)

    def test_summarize_text(self):
        from skills.summarizer import SummarizerSkill
        from unittest.mock import MagicMock
        skill = SummarizerSkill()
        llm = MagicMock()
        llm.send.return_value = "A short summary."
        result = skill.execute({"text": "Long text here", "length": "short"}, {"llm": llm})
        self.assertEqual(result, "A short summary.")
        prompt = llm.send.call_args[0][1]
        self.assertIn("1-2 sentences", prompt)

    def test_summarize_url(self):
        from skills.summarizer import SummarizerSkill
        from unittest.mock import MagicMock, patch
        skill = SummarizerSkill()
        llm = MagicMock()
        llm.send.return_value = "Summary of page."
        fake_html = b"<html><body><p>Page content here</p></body></html>"
        with patch("skills.summarizer._fetch_url", return_value="Page content here"):
            result = skill.execute({"url": "http://example.com"}, {"llm": llm})
        self.assertEqual(result, "Summary of page.")

    def test_url_fetch_error(self):
        from skills.summarizer import SummarizerSkill
        from unittest.mock import MagicMock, patch
        from urllib.error import URLError
        skill = SummarizerSkill()
        llm = MagicMock()
        with patch("skills.summarizer._fetch_url", side_effect=URLError("timeout")):
            result = skill.execute({"url": "http://example.com"}, {"llm": llm})
        self.assertIn("failed to fetch URL", result)

    def test_invalid_length_falls_back_to_medium(self):
        from skills.summarizer import SummarizerSkill
        from unittest.mock import MagicMock
        skill = SummarizerSkill()
        llm = MagicMock()
        llm.send.return_value = "Summary."
        skill.execute({"text": "text", "length": "tiny"}, {"llm": llm})
        prompt = llm.send.call_args[0][1]
        self.assertIn("paragraph", prompt)


class TestFileManagerSkill(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.ctx = {"config": {"files": {"base_dir": self._tmpdir}}}

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _skill(self):
        from skills.file_manager import FileManagerSkill, _PROJECT_ROOT
        from unittest.mock import patch
        skill = FileManagerSkill()
        # Override base_dir resolution to use our temp dir
        original = skill._base_dir
        skill._base_dir = lambda cfg: (
            __import__("pathlib").Path(self._tmpdir)
        )
        return skill

    def test_list_empty(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        result = skill.execute({"action": "list"}, self.ctx)
        self.assertIn("empty", result.lower())

    def test_write_and_read(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        result = skill.execute({"action": "write", "path": "test.txt", "content": "hello"}, self.ctx)
        self.assertIn("written", result)
        result = skill.execute({"action": "read", "path": "test.txt"}, self.ctx)
        self.assertIn("hello", result)

    def test_write_and_list(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        skill.execute({"action": "write", "path": "a.txt", "content": "a"}, self.ctx)
        result = skill.execute({"action": "list"}, self.ctx)
        self.assertIn("a.txt", result)

    def test_delete(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        skill.execute({"action": "write", "path": "del.txt", "content": "bye"}, self.ctx)
        result = skill.execute({"action": "delete", "path": "del.txt"}, self.ctx)
        self.assertIn("deleted", result)
        result = skill.execute({"action": "read", "path": "del.txt"}, self.ctx)
        self.assertIn("not found", result)

    def test_path_escape_blocked(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        result = skill.execute({"action": "read", "path": "../../etc/passwd"}, self.ctx)
        self.assertIn("outside the allowed directory", result)

    def test_read_missing_file(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        result = skill.execute({"action": "read", "path": "ghost.txt"}, self.ctx)
        self.assertIn("not found", result)

    def test_unknown_action(self):
        from skills.file_manager import FileManagerSkill
        from pathlib import Path
        skill = FileManagerSkill()
        skill._base_dir = lambda cfg: Path(self._tmpdir)
        result = skill.execute({"action": "explode", "path": "x.txt"}, self.ctx)
        self.assertIn("unknown action", result)


class TestShellExecSkill(unittest.TestCase):

    @staticmethod
    def _ctx(allowlist, timeout_seconds=30):
        return {"config": {"shell": {"allowlist": allowlist, "timeout_seconds": timeout_seconds}}}

    def test_no_command(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute({}, self._ctx(["echo"]))
        self.assertIn("no command provided", result)

    def test_empty_allowlist_blocks_everything(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute({"command": "echo hi"}, self._ctx([]))
        self.assertIn("no commands are allowlisted", result)

    def test_non_allowlisted_command_blocked(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute({"command": "rm -rf /"}, self._ctx(["echo"]))
        self.assertIn("not in the allowlist", result)

    def test_allowlisted_command_runs(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute({"command": "echo hello world"}, self._ctx(["echo"]))
        self.assertIn("hello world", result)
        self.assertIn("Exit code: 0", result)

    def test_shell_metacharacters_not_interpreted(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        # `&&` and the trailing command are passed to `echo` as literal
        # argv entries — never handed to a shell, so nothing else runs.
        result = skill.execute({"command": "echo safe && rm -rf /"}, self._ctx(["echo"]))
        self.assertIn("safe && rm -rf /", result)

    def test_cwd_escape_blocked(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute(
            {"command": "echo hi", "cwd": "../../../../etc"}, self._ctx(["echo"])
        )
        self.assertIn("outside the project directory", result)

    def test_command_timeout(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute({"command": "sleep 5"}, self._ctx(["sleep"], timeout_seconds=0.2))
        self.assertIn("timed out", result)

    def test_nonexistent_program_errors(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute(
            {"command": "definitely_not_a_real_binary_xyz --help"},
            self._ctx(["definitely_not_a_real_binary_xyz"]),
        )
        self.assertIn("failed to run command", result)

    def test_unparseable_command(self):
        from skills.shell_exec import ShellExecSkill
        skill = ShellExecSkill()
        result = skill.execute({"command": 'echo "unterminated'}, self._ctx(["echo"]))
        self.assertIn("could not parse command", result)

    def test_auto_discovered(self):
        from skills.registry import SkillRegistry
        registry = SkillRegistry()
        registry.auto_discover()
        self.assertIn("shell_exec", registry.list_skills())


class TestRSSDigestSkill(unittest.TestCase):

    def test_no_urls(self):
        from skills.rss_digest import RSSDigestSkill
        skill = RSSDigestSkill()
        result = skill.execute({}, {})
        self.assertIn("no URLs provided", result)

    def test_successful_fetch(self):
        from skills.rss_digest import RSSDigestSkill
        from unittest.mock import patch, MagicMock
        skill = RSSDigestSkill()

        fake_feed = MagicMock()
        fake_feed.feed.get.return_value = "Test Feed"
        entry = MagicMock()
        entry.get.side_effect = lambda k, default="": {
            "title": "Article 1", "link": "http://example.com/1", "summary": "Summary text"
        }.get(k, default)
        fake_feed.entries = [entry]

        with patch("feedparser.parse", return_value=fake_feed):
            result = skill.execute({"urls": "http://example.com/feed"}, {})

        self.assertIn("RSS Digest", result)
        self.assertIn("Article 1", result)

    def test_multiple_urls(self):
        from skills.rss_digest import RSSDigestSkill
        from unittest.mock import patch, MagicMock
        skill = RSSDigestSkill()

        def fake_parse(url):
            feed = MagicMock()
            feed.feed.get.return_value = f"Feed {url}"
            feed.entries = []
            return feed

        with patch("feedparser.parse", side_effect=fake_parse):
            result = skill.execute({"urls": "http://a.com/rss, http://b.com/rss"}, {})

        self.assertIn("RSS Digest", result)

    def test_empty_feed(self):
        from skills.rss_digest import RSSDigestSkill
        from unittest.mock import patch, MagicMock
        skill = RSSDigestSkill()
        fake_feed = MagicMock()
        fake_feed.feed.get.return_value = "Empty Feed"
        fake_feed.entries = []
        with patch("feedparser.parse", return_value=fake_feed):
            result = skill.execute({"urls": "http://example.com/feed"}, {})
        self.assertIn("No entries", result)


class TestWeatherSkill(unittest.TestCase):

    def _make_geo_response(self, name="Paris", lat=48.85341, lon=2.3488, country="France", admin1="Ile-de-France"):
        return {
            "results": [{"name": name, "latitude": lat, "longitude": lon,
                         "country": country, "admin1": admin1}]
        }

    def _make_weather_response(self, temp=18.5, feels=17.0, humidity=62,
                                wind_speed=14.2, wind_dir=270, code=2):
        return {
            "current": {
                "temperature_2m": temp,
                "apparent_temperature": feels,
                "relative_humidity_2m": humidity,
                "wind_speed_10m": wind_speed,
                "wind_direction_10m": wind_dir,
                "weather_code": code,
            }
        }

    def _patch_fetch(self, geo_resp, weather_resp):
        """Return a side_effect list for patching _fetch_json with two calls."""
        return [geo_resp, weather_resp]

    def test_no_location(self):
        from skills.weather import WeatherSkill
        skill = WeatherSkill()
        result = skill.execute({}, {})
        self.assertIn("[weather: no location provided]", result)

    def test_location_not_found(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        skill = WeatherSkill()
        with patch("skills.weather._fetch_json", return_value={"results": []}):
            result = skill.execute({"location": "Xyzzy"}, {})
        self.assertIn("not found", result)

    def test_geocoding_error(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        from urllib.error import URLError
        skill = WeatherSkill()
        with patch("skills.weather._fetch_json", side_effect=URLError("timeout")):
            result = skill.execute({"location": "Paris"}, {})
        self.assertIn("geocoding error", result)

    def test_weather_api_error(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        from urllib.error import URLError
        skill = WeatherSkill()
        geo = self._make_geo_response()
        with patch("skills.weather._fetch_json", side_effect=[geo, URLError("503")]):
            result = skill.execute({"location": "Paris"}, {})
        self.assertIn("API error", result)

    def test_metric_output(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        skill = WeatherSkill()
        geo = self._make_geo_response()
        wx = self._make_weather_response(temp=18.5, feels=17.0, humidity=62,
                                          wind_speed=14.2, wind_dir=270, code=2)
        with patch("skills.weather._fetch_json", side_effect=[geo, wx]):
            result = skill.execute({"location": "Paris", "units": "metric"}, {})

        self.assertIn("Paris", result)
        self.assertIn("18.5°C", result)
        self.assertIn("17.0°C", result)
        self.assertIn("62%", result)
        self.assertIn("14.2 km/h", result)
        self.assertIn("Partly cloudy", result)

    def test_imperial_output(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        skill = WeatherSkill()
        geo = self._make_geo_response(name="New York", country="United States", admin1="New York")
        wx = self._make_weather_response(temp=72.0, feels=70.0, humidity=55,
                                          wind_speed=9.0, wind_dir=0, code=0)
        with patch("skills.weather._fetch_json", side_effect=[geo, wx]):
            result = skill.execute({"location": "New York", "units": "imperial"}, {})

        self.assertIn("72.0°F", result)
        self.assertIn("mph", result)
        self.assertNotIn("km/h", result)
        self.assertIn("Clear sky", result)

    def test_invalid_units_falls_back_to_metric(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        skill = WeatherSkill()
        geo = self._make_geo_response()
        wx = self._make_weather_response()
        with patch("skills.weather._fetch_json", side_effect=[geo, wx]):
            result = skill.execute({"location": "Paris", "units": "kelvin"}, {})
        self.assertIn("°C", result)

    def test_wind_direction_label(self):
        from skills.weather import WeatherSkill
        from unittest.mock import patch
        skill = WeatherSkill()
        geo = self._make_geo_response()
        wx = self._make_weather_response(wind_dir=90)  # East
        with patch("skills.weather._fetch_json", side_effect=[geo, wx]):
            result = skill.execute({"location": "Paris"}, {})
        self.assertIn(" E", result)

    def test_auto_discovered(self):
        registry = SkillRegistry()
        registry.auto_discover()
        self.assertIn("weather", registry.list_skills())


if __name__ == "__main__":
    unittest.main()
