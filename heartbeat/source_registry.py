"""Registry that maps source type names to their classes."""

from heartbeat.sources.base import BaseSource
from heartbeat.sources.api_source import APISource
from heartbeat.sources.file_source import FileSource
from heartbeat.sources.rss_source import RSSSource

_SOURCE_TYPES: dict[str, type[BaseSource]] = {
    "api": APISource,
    "file": FileSource,
    "rss": RSSSource,
}


def create_source(source_config: dict) -> BaseSource:
    """Create a source instance from a config dict.

    Expected keys:
        name (str): Human-readable source name.
        type (str): One of "api", "file", "rss".
        ... (additional keys passed as source config)
    """
    source_type = source_config.get("type", "")
    name = source_config.get("name", source_type)
    cls = _SOURCE_TYPES.get(source_type)
    if cls is None:
        raise ValueError(
            f"Unknown source type: {source_type!r}. "
            f"Available: {', '.join(_SOURCE_TYPES)}"
        )
    return cls(name=name, config=source_config)


def register_source_type(type_name: str, cls: type[BaseSource]) -> None:
    """Register a custom source type."""
    _SOURCE_TYPES[type_name] = cls
