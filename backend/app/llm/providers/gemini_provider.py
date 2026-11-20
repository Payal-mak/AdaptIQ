import re

import httpx
from google import genai
from google.genai import errors, types

from app.llm.base import LLMProvider, LLMResult, redact
from app.llm.errors import (
    AuthError,
    BadRequestError,
    InvalidOutputError,
    RateLimitError,
    TransientError,
)

_RETRY_DELAY = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")


def _retry_after_seconds(exc: errors.APIError) -> float | None:
    """Best effort: Gemini puts a 'retryDelay' like '12s' in the error details."""
    match = _RETRY_DELAY.search(str(exc))
    return float(match.group(1)) if match else None


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        input_price_per_m: float = 0.0,
        output_price_per_m: float = 0.0,
    ) -> None:
        super().__init__(model, input_price_per_m, output_price_per_m)
        self._api_key = api_key
        self._client: genai.Client | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self.model)

    def _get_client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(
        self, system: str, user: str, json_mode: bool, temperature: float, timeout: float
    ) -> LLMResult:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
            http_options=types.HttpOptions(
                timeout=int(timeout * 1000),  # milliseconds
                # attempts=1: no hidden SDK retries; OUR wrapper owns retry logic.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        try:
            response = self._get_client().models.generate_content(
                model=self.model, contents=user, config=config
            )
        except errors.APIError as exc:
            raise self._translate(exc) from None
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientError(self._msg("timeout or connection problem", exc)) from None

        text = response.text or ""
        if not text:
            raise InvalidOutputError("Gemini returned an empty response (possibly blocked)")
        usage = response.usage_metadata
        output_tokens = None
        if usage is not None and usage.candidates_token_count is not None:
            # Thinking tokens are billed as output, so count them too.
            output_tokens = usage.candidates_token_count + (usage.thoughts_token_count or 0)
        return LLMResult(
            text=text,
            model=self.model,
            input_tokens=usage.prompt_token_count if usage is not None else None,
            output_tokens=output_tokens,
        )

    def _translate(self, exc: errors.APIError) -> Exception:
        code = exc.code or 0
        text = str(exc)
        # Gemini reports an invalid API key as HTTP 400, not 401.
        if code in (401, 403) or "API key not valid" in text or "API_KEY_INVALID" in text:
            return AuthError(self._msg("Gemini rejected the API key or permission", exc))
        if code == 429:
            return RateLimitError(self._msg("rate limit reached", exc), _retry_after_seconds(exc))
        if code >= 500 or code == 408:
            return TransientError(self._msg(f"server error {code}", exc), _retry_after_seconds(exc))
        return BadRequestError(self._msg(f"request rejected ({code})", exc))

    def _msg(self, summary: str, exc: Exception) -> str:
        return f"Gemini: {summary}: {redact(str(exc), self._api_key)[:300]}"
