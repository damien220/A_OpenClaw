"""Translator skill — translate text to any language via the LLM."""

from skills.base import BaseSkill

from logger_pkg import get_logger

logger = get_logger(__name__)


class TranslatorSkill(BaseSkill):
    name = "translate"
    description = "Translate text to another language using the LLM."
    parameters = {
        "text": "The text to translate.",
        "target_language": "Language to translate into, e.g. 'French', 'Japanese', 'Arabic'.",
        "source_language": "Optional. Source language. Auto-detected if omitted.",
    }

    def execute(self, params: dict, context: dict) -> str:
        text = params.get("text", "").strip()
        target = params.get("target_language", "").strip()

        if not text:
            return "[translate: no text provided]"
        if not target:
            return "[translate: no target_language provided]"

        llm = context.get("llm")
        if llm is None:
            return "[translate: LLM not available in context]"

        source = params.get("source_language", "").strip()
        from_clause = f" from {source}" if source else ""
        prompt = (
            f"Translate the following text{from_clause} to {target}. "
            f"Return only the translation, no explanation or commentary.\n\n{text}"
        )

        try:
            result = llm.send("", prompt)
            logger.info("Translation done", extra={"target": target, "chars": len(text)})
            return result
        except Exception as e:
            logger.error("Translation failed", extra={"error": str(e)})
            return f"[translate: error — {e}]"
