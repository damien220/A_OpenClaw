"""LLM API wrapper for A_OpenClaw.

Supports Anthropic, OpenAI, and local/offline providers (Ollama, llama.cpp).
Accepts context from the memory system and a user prompt, returns the LLM response.

Provider options:
  - "anthropic"  — Anthropic API (requires ANTHROPIC_API_KEY)
  - "openai"     — OpenAI API (requires OPENAI_API_KEY)
  - "ollama"     — Local Ollama server (default: http://localhost:11434/v1)
  - "llamacpp"   — Local llama.cpp server (default: http://localhost:8080/v1)

Ollama and llama.cpp both expose OpenAI-compatible endpoints, so they reuse
the openai Python client with a custom base_url.
"""

import os
import time

from core.config_loader import load_config

from logger_pkg import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds, doubles each attempt

_LOCAL_DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "llama3.2"},
    "llamacpp": {"base_url": "http://localhost:8080/v1", "model": "default"},
}


class LLMClient:
    def __init__(self, config: dict | None = None):
        self._config = config or load_config()
        llm_cfg = self._config.get("llm", {})

        self._provider = llm_cfg.get("provider", "anthropic")
        self._model = llm_cfg.get("model")
        self._base_url = llm_cfg.get("base_url", "")
        self._max_response_tokens = llm_cfg.get("max_response_tokens", 4096)
        self._max_context_tokens = llm_cfg.get("max_context_tokens", 100000)
        self._client = None

        # Apply local provider defaults if not explicitly set
        if self._provider in _LOCAL_DEFAULTS:
            defaults = _LOCAL_DEFAULTS[self._provider]
            if not self._model:
                self._model = defaults["model"]
            if not self._base_url:
                self._base_url = defaults["base_url"]

        if not self._model:
            self._model = "claude-sonnet-4-6" if self._provider == "anthropic" else "gpt-4o"

        logger.debug(
            "LLMClient initialized",
            extra={"provider": self._provider, "model": self._model},
        )

    def _get_client(self):
        if self._client is not None:
            return self._client

        if self._provider == "anthropic":
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
            self._client = anthropic.Anthropic(api_key=api_key)

        elif self._provider == "openai":
            import openai
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY environment variable is not set")
            self._client = openai.OpenAI(api_key=api_key)

        elif self._provider in ("ollama", "llamacpp"):
            import openai
            self._client = openai.OpenAI(
                base_url=self._base_url,
                api_key="not-needed",
            )

        else:
            raise ValueError(f"Unknown LLM provider: {self._provider}")

        return self._client

    def _is_openai_compatible(self) -> bool:
        return self._provider in ("openai", "ollama", "llamacpp")

    def send(self, context: str, prompt: str, system: str | None = None) -> str:
        """Send a prompt with memory context to the LLM and return the response.

        Args:
            context: Assembled memory context (from MemoryManager.build_context()).
            prompt: The user/heartbeat message to process.
            system: Optional system prompt override.

        Returns:
            The LLM's text response.
        """
        system_prompt = system or "You are A_OpenClaw, a personal AI assistant."
        if context.strip():
            system_prompt += f"\n\n# Memory Context\n\n{context}"

        prompt_len = len(prompt)
        context_len = len(context)
        start = time.monotonic()

        logger.info(
            "LLM request",
            extra={
                "provider": self._provider,
                "model": self._model,
                "prompt_len": prompt_len,
                "context_len": context_len,
            },
        )

        last_error = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                client = self._get_client()

                if self._provider == "anthropic":
                    response = client.messages.create(
                        model=self._model,
                        max_tokens=self._max_response_tokens,
                        system=system_prompt,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    result = response.content[0].text

                elif self._is_openai_compatible():
                    response = client.chat.completions.create(
                        model=self._model,
                        max_tokens=self._max_response_tokens,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                    )
                    result = response.choices[0].message.content

                else:
                    raise ValueError(f"Unknown provider: {self._provider}")

                duration_ms = int((time.monotonic() - start) * 1000)
                logger.info(
                    "LLM response",
                    extra={
                        "provider": self._provider,
                        "model": self._model,
                        "response_len": len(result),
                        "duration_ms": duration_ms,
                        "attempt": attempt,
                    },
                )
                return result

            except ValueError:
                raise  # Don't retry config errors
            except Exception as e:
                last_error = e
                duration_ms = int((time.monotonic() - start) * 1000)
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM request failed, retrying",
                        extra={
                            "provider": self._provider,
                            "model": self._model,
                            "attempt": attempt,
                            "delay_s": delay,
                            "error": str(e),
                        },
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "LLM request failed after all retries",
                        extra={
                            "provider": self._provider,
                            "model": self._model,
                            "duration_ms": duration_ms,
                            "attempts": _MAX_RETRIES,
                        },
                        exc_info=True,
                    )

        raise last_error
