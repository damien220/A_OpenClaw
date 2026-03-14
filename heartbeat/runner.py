"""Heartbeat engine — scheduled data gathering and LLM processing.

Runs on a configurable interval. Each tick:
  1. Gathers data from all configured sources.
  2. Builds memory context.
  3. Sends gathered data + context to the LLM.
  4. Parses the LLM response for actions (memory updates, messages).
  5. Executes the actions.
"""

import json
import threading

from core.config_loader import load_config
from core.memory_manager import MemoryManager
from core.llm_client import LLMClient
from heartbeat.source_registry import create_source
from heartbeat.sources.base import BaseSource

from logger_pkg import get_logger, bind_context
from logger_pkg.context import reset_context

logger = get_logger(__name__)

HEARTBEAT_SYSTEM_PROMPT = """You are A_OpenClaw's heartbeat processor. You receive data gathered from \
configured sources and the assistant's memory context.

Analyze the data and respond with a JSON object containing any actions to take:

{
  "memory_updates": "text to append to the knowledge base (or empty string)",
  "summary": "brief summary of what was found (always provide this)",
  "messages": ["optional list of messages to send through the adapter"]
}

Only include memory_updates if there is genuinely new, important information worth remembering.
Keep the summary concise — one or two sentences."""


class HeartbeatRunner:
    def __init__(self, config: dict | None = None):
        self._config = config or load_config()
        hb_cfg = self._config.get("heartbeat", {})

        self._enabled = hb_cfg.get("enabled", False)
        self._interval = hb_cfg.get("interval_seconds", 300)
        self._source_configs = hb_cfg.get("sources", [])

        self._memory = MemoryManager(self._config)
        self._llm = LLMClient(self._config)
        self._sources: list[BaseSource] = []
        self._stop_event = threading.Event()
        self._tick_counter = 0
        self._adapter = None

        self._init_sources()

    def set_adapter(self, adapter) -> None:
        """Set the adapter for dispatching outbound messages."""
        self._adapter = adapter

    def _init_sources(self) -> None:
        for src_cfg in self._source_configs:
            try:
                source = create_source(src_cfg)
                self._sources.append(source)
                logger.debug("Source registered", extra={"source": source.name, "type": src_cfg.get("type")})
            except ValueError as e:
                logger.warning("Skipping source", extra={"error": str(e)})

    def gather_all(self) -> str:
        """Run all sources and return combined output."""
        results = []
        for source in self._sources:
            try:
                data = source.gather()
                if data.strip():
                    results.append(data)
                    logger.debug("Source gathered", extra={"source": source.name, "data_len": len(data)})
            except Exception as e:
                logger.error("Source gather failed", extra={"source": source.name}, exc_info=True)
                results.append(f"[Error from {source.name}]: {e}")
        return "\n\n---\n\n".join(results)

    def process(self, gathered_data: str) -> dict:
        """Send gathered data to LLM and parse the response."""
        if not gathered_data.strip():
            logger.info("Heartbeat tick: no data from sources")
            return {"summary": "No data from sources.", "memory_updates": "", "messages": []}

        context = self._memory.build_context()
        prompt = f"# Heartbeat Data\n\n{gathered_data}"

        raw_response = self._llm.send(context, prompt, system=HEARTBEAT_SYSTEM_PROMPT)

        # Try to parse JSON from response
        try:
            # Handle response that may have markdown code fences
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            logger.warning("LLM response not valid JSON, using raw text", extra={"response_len": len(raw_response)})
            result = {"summary": raw_response[:500], "memory_updates": "", "messages": []}

        return result

    def execute_actions(self, actions: dict) -> None:
        """Execute parsed actions from the LLM response."""
        # Memory updates
        mem_update = actions.get("memory_updates", "")
        if mem_update and mem_update.strip():
            self._memory.append_memory("memory", f"\n{mem_update.strip()}")
            logger.info("Memory updated by heartbeat", extra={"update_len": len(mem_update)})

        # Log the heartbeat
        summary = actions.get("summary", "")
        self._memory.log_interaction("heartbeat", summary)

        # Dispatch outbound messages through the adapter
        messages = actions.get("messages", [])
        if messages:
            self._memory.log_interaction("heartbeat-outbound", "\n".join(messages))
            if self._adapter:
                target = actions.get("target", "default")
                for msg in messages:
                    try:
                        self._adapter.send(msg, target)
                    except Exception:
                        logger.error("Failed to send heartbeat message", exc_info=True)
            logger.info("Heartbeat outbound messages sent", extra={"count": len(messages)})

    def tick(self) -> dict:
        """Execute one heartbeat cycle. Returns the actions dict."""
        self._tick_counter += 1
        token = bind_context(tick_id=self._tick_counter, phase="heartbeat")
        try:
            logger.info("Heartbeat tick start", extra={"source_count": len(self._sources)})
            gathered = self.gather_all()
            actions = self.process(gathered)
            self.execute_actions(actions)
            logger.info("Heartbeat tick complete", extra={"summary": actions.get("summary", "")[:100]})
            return actions
        except Exception:
            logger.error("Heartbeat tick failed", exc_info=True)
            raise
        finally:
            reset_context(token)

    def run_once(self) -> dict:
        """Run a single heartbeat tick (for cron or manual invocation)."""
        return self.tick()

    def run_loop(self) -> None:
        """Run the heartbeat in a loop with the configured interval."""
        logger.info(
            "Heartbeat loop starting",
            extra={"interval": self._interval, "source_count": len(self._sources)},
        )
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                pass  # Already logged in tick()
            self._stop_event.wait(self._interval)
        logger.info("Heartbeat loop stopped")

    def start_background(self) -> threading.Thread:
        """Start the heartbeat loop in a background daemon thread."""
        thread = threading.Thread(target=self.run_loop, daemon=True, name="heartbeat")
        thread.start()
        return thread

    def stop(self) -> None:
        """Signal the heartbeat loop to stop."""
        self._stop_event.set()
