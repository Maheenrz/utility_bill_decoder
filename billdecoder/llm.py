"""One thin wrapper around Gemini: structured output + retry on transient API errors."""
import logging
import random
import time
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from . import config

log = logging.getLogger("billdecoder")
T = TypeVar("T", bound=BaseModel)
_RETRYABLE = {429, 500, 502, 503, 504}
_client = None


class LLMError(RuntimeError):
    pass


def _get_client():
    global _client
    if _client is None:
        if not config.API_KEY:
            raise LLMError("GEMINI_API_KEY is missing. Copy .env.example to .env and set it.")
        _client = genai.Client(api_key=config.API_KEY)
    return _client


def ensure_ready() -> None:
    """Fail fast, once, with a clear message (instead of failing on every bill)."""
    _get_client()


def generate(contents: list, schema: type[T], model: str | None = None) -> T:
    """Call the model, force it to return `schema`, retry on rate-limit / server errors."""
    model = model or config.MODEL_NAME
    last: Exception | None = None
    for attempt in range(config.MAX_API_RETRIES):
        try:
            resp = _get_client().models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
            if not resp.text:
                raise LLMError("empty model response")
            return schema.model_validate_json(resp.text)
        except errors.APIError as exc:
            last = exc
            if getattr(exc, "code", None) not in _RETRYABLE:
                raise LLMError(f"API error {getattr(exc, 'code', '?')}: {exc}") from exc
            wait = 2 ** attempt + random.random()
            log.warning("API error %s, retry %d/%d in %.1fs", exc.code, attempt + 1, config.MAX_API_RETRIES, wait)
            time.sleep(wait)
        except ValueError as exc:      # pydantic validation of the model output
            last = exc
            log.warning("model output failed validation (%s), retry %d", exc, attempt + 1)
    raise LLMError(f"model call failed after {config.MAX_API_RETRIES} attempts: {last}")
