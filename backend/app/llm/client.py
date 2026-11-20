"""LLMClient: the ONLY thing the rest of the app imports to talk to an LLM.

Rules (see CLAUDE.md "LLM wrapper"):
- retry RateLimitError / TransientError with exponential backoff + jitter, up to `max_retries` retries
- never retry AuthError / BadRequestError
- if the primary provider still fails (rate limit, transient, or invalid output), try the fallback once
- every attempt is logged to llm_calls
"""

import json
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider, LLMResult
from app.llm.call_log import CallLogger, SessionFactory, default_session_factory
from app.llm.errors import (
    AuthError,
    BadRequestError,
    InvalidOutputError,
    LLMError,
    RateLimitError,
    TransientError,
)
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.groq_provider import GroqProvider

T = TypeVar("T", bound=BaseModel)

BACKOFF_BASE_SECONDS = 1.0
JITTER_FRACTION = 0.5  # up to +50% random extra wait
MAX_ECHO_CHARS = 1500  # how much of a bad reply / error goes into the repair prompt


@dataclass
class _Attempts:
    """Counts the attempts made against one provider during one client call."""

    count: int = 0

    def next(self) -> int:
        self.count += 1
        return self.count


@dataclass
class _Reply:
    """A successful provider call: the result plus which attempt it was and how long it took."""

    result: LLMResult
    attempt: int
    latency_ms: int


def build_provider(name: str, settings: Settings) -> LLMProvider:
    """Create a provider by name, reading keys, models and prices from settings (.env)."""
    if name == "groq":
        return GroqProvider(
            settings.groq_api_key, settings.groq_model, settings.groq_input_price_per_m, settings.groq_output_price_per_m
        )
    if name == "gemini":
        return GeminiProvider(
            settings.gemini_api_key,
            settings.gemini_model,
            settings.gemini_input_price_per_m,
            settings.gemini_output_price_per_m,
        )
    raise ValueError(f"Unknown LLM provider '{name}' (use 'groq' or 'gemini')")


def _strip_code_fences(text: str) -> str:
    """Models sometimes wrap JSON in ```json ... ```; remove that."""
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    return match.group(1) if match else stripped


class LLMClient:
    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        *,
        session_factory: SessionFactory,
        max_retries: int = 2,
        max_retry_wait_seconds: float = 20.0,
        timeout_seconds: float = 30.0,
        log_payloads: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.max_retries = max_retries
        self.max_retry_wait_seconds = max_retry_wait_seconds
        self.timeout_seconds = timeout_seconds
        self._log = CallLogger(session_factory, log_payloads)
        self._sleep = sleep  # injectable so tests don't really wait
        self._rng = rng  # injectable so tests get predictable jitter
        self._clock = clock

    @classmethod
    def from_settings(
        cls, settings: Settings | None = None, session_factory: SessionFactory | None = None
    ) -> "LLMClient":
        settings = settings or get_settings()
        fallback_name = settings.llm_fallback_provider.strip().lower()
        return cls(
            primary=build_provider(settings.llm_provider.strip().lower(), settings),
            fallback=build_provider(fallback_name, settings) if fallback_name else None,
            session_factory=session_factory or default_session_factory(),
            max_retries=settings.llm_max_retries,
            max_retry_wait_seconds=settings.llm_max_retry_wait_seconds,
            timeout_seconds=settings.llm_timeout_seconds,
            log_payloads=settings.llm_log_payloads,
        )

    # ------------------------------------------------------------------ public API

    def generate_text(self, purpose: str, system: str, user: str, temperature: float = 0.2) -> str:
        """Plain-text answer."""

        def attempt(provider: LLMProvider, is_fallback: bool) -> str:
            reply = self._call_with_retries(
                provider, purpose, system, user, False, temperature, is_fallback, _Attempts()
            )
            self._record_reply(purpose, provider, is_fallback, reply, True, None, system, user)
            return reply.result.text

        return self._run_with_fallback(attempt)

    def generate_json(
        self, purpose: str, system: str, user: str, schema: type[T], temperature: float = 0.2
    ) -> T:
        """JSON answer, validated against `schema`. One repair try per provider, then fallback."""
        full_system = (
            f"{system}\n\nRespond with ONE JSON object only (no markdown, no commentary) "
            f"that matches this JSON Schema:\n{json.dumps(schema.model_json_schema())}"
        )

        def attempt(provider: LLMProvider, is_fallback: bool) -> T:
            attempts = _Attempts()
            try:
                return self._call_and_parse(
                    provider, purpose, full_system, user, schema, temperature, is_fallback, attempts
                )
            except InvalidOutputError as first_error:
                repair_user = (
                    f"{user}\n\nYour previous reply was invalid.\n"
                    f"Previous reply: {(first_error.raw_text or '')[:MAX_ECHO_CHARS]}\n"
                    f"Problem: {str(first_error)[:MAX_ECHO_CHARS]}\n"
                    "Reply again with ONLY the corrected JSON object."
                )
                return self._call_and_parse(
                    provider, purpose, full_system, repair_user, schema, temperature, is_fallback, attempts
                )

        return self._run_with_fallback(attempt)

    # ------------------------------------------------------------------ internals

    def _run_with_fallback(self, attempt: Callable[[LLMProvider, bool], T]) -> T:  # type: ignore[type-var]
        if not self.primary.is_configured:
            raise AuthError(f"{self.primary.name}: API key or model name is not set in .env")

        candidates: list[tuple[LLMProvider, bool]] = [(self.primary, False)]
        if (
            self.fallback is not None
            and self.fallback.is_configured  # no key -> skip the fallback
            and self.fallback.name != self.primary.name
        ):
            candidates.append((self.fallback, True))

        last_error: LLMError | None = None
        for provider, is_fallback in candidates:
            try:
                return attempt(provider, is_fallback)
            except (RateLimitError, TransientError, InvalidOutputError) as exc:
                last_error = exc  # these are the failures where trying another provider can help
        assert last_error is not None
        raise last_error

    def _call_and_parse(
        self,
        provider: LLMProvider,
        purpose: str,
        system: str,
        user: str,
        schema: type[T],
        temperature: float,
        is_fallback: bool,
        attempts: _Attempts,
    ) -> T:
        """One call (with its retries) plus validation. Raises InvalidOutputError if the JSON is bad."""
        reply = self._call_with_retries(
            provider, purpose, system, user, True, temperature, is_fallback, attempts
        )
        try:
            parsed = schema.model_validate_json(_strip_code_fences(reply.result.text))
        except (ValidationError, ValueError) as exc:
            self._record_reply(
                purpose, provider, is_fallback, reply, False, InvalidOutputError.error_type, system, user
            )
            raise InvalidOutputError(
                f"Reply did not match the schema: {exc}", raw_text=reply.result.text
            ) from None
        self._record_reply(purpose, provider, is_fallback, reply, True, None, system, user)
        return parsed

    def _call_with_retries(
        self,
        provider: LLMProvider,
        purpose: str,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        is_fallback: bool,
        attempts: _Attempts,
    ) -> _Reply:
        """Call the provider, retrying rate-limit/transient errors. Logs every FAILED attempt here;
        the successful attempt is logged by the caller once it knows the reply is usable."""
        retries_used = 0
        while True:
            attempt_no = attempts.next()
            started = self._clock()
            try:
                result = provider.generate(system, user, json_mode, temperature, self.timeout_seconds)
                return _Reply(result, attempt_no, self._ms_since(started))
            except (RateLimitError, TransientError) as exc:
                self._record_failure(purpose, provider, is_fallback, attempt_no, exc, started, (system, user))
                if retries_used >= self.max_retries:
                    raise
                delay = self._wait_time(exc, retries_used + 1)
                if delay is None:
                    raise  # asked to wait too long: give up on this provider (fallback may still run)
                self._sleep(delay)
                retries_used += 1
            except LLMError as exc:  # AuthError, BadRequestError, InvalidOutputError from the provider
                self._record_failure(purpose, provider, is_fallback, attempt_no, exc, started, (system, user))
                raise

    def _wait_time(self, exc: RateLimitError | TransientError, retry_number: int) -> float | None:
        """Exponential backoff with jitter; at least Retry-After. None = too long to wait."""
        backoff = BACKOFF_BASE_SECONDS * (2 ** (retry_number - 1))
        backoff += backoff * JITTER_FRACTION * self._rng()
        delay = max(backoff, exc.retry_after or 0.0)
        if (exc.retry_after or 0.0) > self.max_retry_wait_seconds or delay > self.max_retry_wait_seconds:
            return None
        return delay

    # ------------------------------------------------------------------ logging helpers

    def _ms_since(self, started: float) -> int:
        return int((self._clock() - started) * 1000)

    def _cost(self, provider: LLMProvider, result: LLMResult) -> float:
        """estimated cost in USD = tokens x price per million tokens."""
        return (
            (result.input_tokens or 0) * provider.input_price_per_m
            + (result.output_tokens or 0) * provider.output_price_per_m
        ) / 1_000_000

    def _record_reply(
        self,
        purpose: str,
        provider: LLMProvider,
        is_fallback: bool,
        reply: _Reply,
        success: bool,
        error_type: str | None,
        system: str,
        user: str,
    ) -> None:
        """Log an attempt that got a reply (usable or not). Tokens were spent either way."""
        result = reply.result
        self._log.record(
            purpose=purpose,
            provider=provider.name,
            model=result.model,
            success=success,
            error_type=error_type,
            attempt=reply.attempt,
            fallback_used=is_fallback,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=reply.latency_ms,
            estimated_cost_usd=self._cost(provider, result),
            prompt_text=f"SYSTEM:\n{system}\n\nUSER:\n{user}",
            response_text=result.text,
        )

    def _record_failure(
        self,
        purpose: str,
        provider: LLMProvider,
        is_fallback: bool,
        attempt_no: int,
        exc: LLMError,
        started: float,
        prompt: tuple[str, str],
    ) -> None:
        self._log.record(
            purpose=purpose,
            provider=provider.name,
            model=provider.model,
            success=False,
            error_type=exc.error_type,
            attempt=attempt_no,
            fallback_used=is_fallback,
            input_tokens=None,
            output_tokens=None,
            latency_ms=self._ms_since(started),
            estimated_cost_usd=0.0,
            prompt_text=f"SYSTEM:\n{prompt[0]}\n\nUSER:\n{prompt[1]}",
            response_text=None,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    """The shared client used by agents. Built once from .env settings."""
    return LLMClient.from_settings()
