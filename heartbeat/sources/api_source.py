"""REST API data source for the heartbeat."""

import json
from urllib.request import Request, urlopen
from urllib.error import URLError

from heartbeat.sources.base import BaseSource

from logger_pkg import get_logger

logger = get_logger(__name__)


class APISource(BaseSource):
    """Fetch data from a REST API endpoint.

    Config keys:
        url (str): The API endpoint URL.
        method (str): HTTP method, default "GET".
        headers (dict): Optional HTTP headers.
        body (str): Optional request body for POST/PUT.
        timeout (int): Request timeout in seconds, default 30.
        jq (str): Optional dot-path to extract from JSON response (e.g. "data.items").
    """

    def gather(self) -> str:
        url = self.config.get("url", "")
        if not url:
            return ""

        method = self.config.get("method", "GET").upper()
        headers = self.config.get("headers", {})
        body = self.config.get("body")
        timeout = self.config.get("timeout", 30)
        jq_path = self.config.get("jq", "")

        data = body.encode("utf-8") if body else None
        req = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except (URLError, TimeoutError) as e:
            logger.error("API fetch failed", extra={"source": self.name, "url": url, "error": str(e)})
            return f"[API error for {self.name}]: {e}"

        if jq_path:
            try:
                parsed = json.loads(raw)
                for key in jq_path.split("."):
                    parsed = parsed[key]
                raw = json.dumps(parsed, indent=2) if not isinstance(parsed, str) else parsed
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning("jq extraction failed", extra={"source": self.name, "jq": jq_path})

        logger.debug("API source gathered", extra={"source": self.name, "response_len": len(raw)})
        return f"### Source: {self.name} (API)\n\n```json\n{raw[:5000]}\n```"
