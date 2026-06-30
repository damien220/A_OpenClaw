"""A_OpenClaw — Entry point.

Loads configuration, initializes core components, and runs the assistant.
"""

import sys

from core.config_loader import load_config, validate_config
from core.memory_manager import MemoryManager
from core.llm_client import LLMClient
from heartbeat.runner import HeartbeatRunner
from adapters.adapter_factory import create_adapter
from skills.registry import SkillRegistry
from skills.skill_parser import process_skill_calls

from logger_pkg import setup_logging, get_logger

logger = get_logger(__name__)


def _init_logging(config: dict):
    """Initialize structured logging from config."""
    log_cfg = config.get("logging", {})
    level = log_cfg.get("level", "info").upper()
    fmt = log_cfg.get("format", "text")

    listener = setup_logging(
        level=level,
        format="json" if fmt == "json" else "console",
        file_enabled=True,
        file_path="logs/a_openclaw.log",
        file_rotation="time",
        file_when="midnight",
        file_backup_count=30,
        pii_filter_enabled=True,
        extra_fields={"service": "a_openclaw", "version": config.get("app", {}).get("version", "0.1.0")},
    )
    return listener


def main():
    config = load_config()
    listener = _init_logging(config)

    # Validate config
    errors = validate_config(config)
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        print(f"Configuration has {len(errors)} error(s). Check logs or fix config/config.toml.")
        sys.exit(1)

    logger.info(
        "A_OpenClaw initialized",
        extra={
            "provider": config.get("llm", {}).get("provider"),
            "model": config.get("llm", {}).get("model"),
            "memory_dir": config.get("memory", {}).get("directory"),
        },
    )

    memory = MemoryManager(config)
    llm = LLMClient(config)

    # Initialize skills (built-in + custom_skills/ directory)
    skill_registry = SkillRegistry()
    skill_registry.auto_discover(extra_dirs=["custom_skills"])
    skill_registry.update_skill_memory(memory)
    logger.info("Skills loaded", extra={"skills": skill_registry.list_skills()})

    # Skill execution context — shared with all skill invocations
    skill_context = {"memory": memory, "config": config, "llm": llm}

    # Start heartbeat if enabled
    heartbeat = HeartbeatRunner(config)
    hb_cfg = config.get("heartbeat", {})
    if hb_cfg.get("enabled", False):
        sources = hb_cfg.get("sources", [])
        logger.info(
            "Heartbeat started",
            extra={"interval": hb_cfg.get("interval_seconds", 300), "source_count": len(sources)},
        )
        heartbeat.start_background()
    else:
        logger.info("Heartbeat disabled")

    # Create the adapter
    adapter = create_adapter(config)

    # Wire the message handler: adapter -> memory -> LLM -> skills -> response
    def handle_message(message: str, sender: str, metadata: dict) -> str:
        # Built-in commands
        if message.lower() == "/heartbeat":
            try:
                actions = heartbeat.run_once()
                return f"Heartbeat: {actions.get('summary', 'N/A')}"
            except Exception as e:
                logger.error("Manual heartbeat failed", exc_info=True)
                return f"[Heartbeat error: {e}]"

        context = memory.build_context()
        memory.log_interaction("user", message)

        try:
            response = llm.send(context, message)
        except Exception as e:
            logger.error("LLM call failed", exc_info=True)
            return f"[LLM error: {e}]"

        # Process any skill invocations in the LLM response
        response = process_skill_calls(response, skill_registry, skill_context)

        memory.log_interaction("assistant", response)

        # Periodic memory compaction
        memory.compact_memory()

        return response

    adapter.on_message(handle_message)

    # Wire heartbeat outbound messages through the adapter
    heartbeat.set_adapter(adapter)

    # Start the adapter (blocks for CLI, runs polling for Telegram)
    try:
        adapter.start()
    except KeyboardInterrupt:
        pass
    finally:
        adapter.stop()
        heartbeat.stop()
        if listener:
            listener.stop()
        logger.info("A_OpenClaw shutdown")


if __name__ == "__main__":
    main()
