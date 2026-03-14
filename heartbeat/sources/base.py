"""Base interface for heartbeat data sources."""

from abc import ABC, abstractmethod


class BaseSource(ABC):
    """A data source that the heartbeat gathers information from."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    @abstractmethod
    def gather(self) -> str:
        """Collect data and return as a formatted string.

        Returns an empty string if no new data is available.
        """
        ...
