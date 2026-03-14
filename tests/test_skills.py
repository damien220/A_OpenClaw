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


if __name__ == "__main__":
    unittest.main()
