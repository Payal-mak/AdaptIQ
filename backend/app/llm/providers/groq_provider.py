import groq
from groq import Groq

from app.llm.base import LLMProvider, LLMResult, redact
from app.llm.errors import (
    AuthError,
    BadRequestError,
    InvalidOutputError,
    RateLimitError,
    TransientError,
)


def _retry_after_seconds(exc: groq.APIStatusError) -> float | None:
    """Read the Retry-After header (seconds) if the provider sent one."""
    value = exc.response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str,
        input_price_per_m: float = 0.0,
        output_price_per_m: float = 0.0,
    ) -> None:
        super().__init__(model, input_price_per_m, output_price_per_m)
        self._api_key = api_key
        self._client: Groq | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self.model)

    def _get_client(self) -> Groq:
        if self._client is None:
            # max_retries=0: OUR wrapper owns the retry logic, so attempts are counted and logged.
            self._client = Groq(api_key=self._api_key, max_retries=0)
        return self._client

    def generate(
        self, system: str, user: str, json_mode: bool, temperature: float, timeout: float
    ) -> LLMResult:
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                timeout=timeout,
                **({"response_format": {"type": "json_object"}} if json_mode else {}),
            )
        except groq.RateLimitError as exc:
            raise RateLimitError(self._msg("rate limit reached", exc), _retry_after_seconds(exc)) from None
        except (groq.APITimeoutError, groq.APIConnectionError) as exc:
            raise TransientError(self._msg("timeout or connection problem", exc)) from None
        except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
            raise AuthError(self._msg("Groq rejected the API key or permission", exc)) from None
        except groq.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 409):
                raise TransientError(self._msg(f"server error {exc.status_code}", exc), _retry_after_seconds(exc)) from None
            if "json_validate_failed" in str(exc):
                # Groq's JSON mode itself failed to produce valid JSON: treat like invalid output.
                raise InvalidOutputError("Groq could not produce valid JSON") from None
            raise BadRequestError(self._msg(f"request rejected ({exc.status_code})", exc)) from None

        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage
        return LLMResult(
            text=text,
            model=self.model,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )

    def _msg(self, summary: str, exc: Exception) -> str:
        return f"Groq: {summary}: {redact(str(exc), self._api_key)[:300]}"
