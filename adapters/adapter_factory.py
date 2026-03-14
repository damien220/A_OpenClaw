"""Factory that creates the right adapter from config."""

from adapters.base import BaseAdapter
from adapters.cli_adapter import CLIAdapter

from logger_pkg import get_logger

logger = get_logger(__name__)

_ADAPTER_TYPES: dict[str, type[BaseAdapter]] = {
    "cli": CLIAdapter,
}

# Lazy-register adapters that have external dependencies
_LAZY_ADAPTERS = {
    "telegram": ("adapters.telegram_adapter", "TelegramAdapter"),
}


def create_adapter(config: dict) -> BaseAdapter:
    """Create an adapter instance from the app config.

    Reads [adapter] section:
        type = "cli" | "telegram" | ...
        [adapter.config] = platform-specific settings
    """
    adapter_cfg = config.get("adapter", {})
    adapter_type = adapter_cfg.get("type", "").strip()
    adapter_config = adapter_cfg.get("config", {})

    # Default to CLI if no type specified
    if not adapter_type:
        adapter_type = "cli"
        logger.info("No adapter type configured, defaulting to CLI")

    # Check registered adapters first
    cls = _ADAPTER_TYPES.get(adapter_type)

    # Try lazy imports for adapters with external deps
    if cls is None and adapter_type in _LAZY_ADAPTERS:
        module_path, class_name = _LAZY_ADAPTERS[adapter_type]
        import importlib
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
        except ImportError:
            raise RuntimeError(
                f"Adapter '{adapter_type}' requires additional dependencies. "
                f"Check the adapter module for install instructions."
            )

    if cls is None:
        available = sorted(set(list(_ADAPTER_TYPES) + list(_LAZY_ADAPTERS)))
        raise ValueError(
            f"Unknown adapter type: {adapter_type!r}. Available: {', '.join(available)}"
        )

    logger.info("Adapter created", extra={"type": adapter_type})
    return cls(config=adapter_config)


def register_adapter_type(type_name: str, cls: type[BaseAdapter]) -> None:
    """Register a custom adapter type."""
    _ADAPTER_TYPES[type_name] = cls
