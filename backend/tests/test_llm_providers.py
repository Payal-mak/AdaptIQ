"""Check that SDK errors are translated into our error types. No network: the SDK client is stubbed."""

from types import SimpleNamespace

import groq
import httpx
import pytest
from google.genai import errors as genai_errors

from app.llm.base import redact
from app.llm.errors import (
    AuthError,
    BadRequestError,
    InvalidOutputError,
    RateLimitError,
    TransientError,
)
from app.llm.providers.gemini_provider import GeminiProvider
from app.llm.providers.groq_provider import GroqProvider

KEY = "sk-secret-key-123"


def _groq_error(cls: type[groq.APIStatusError], status: int, headers: dict[str, str] | None = None, body: object = None):  # type: ignore[no-untyped-def]
    response = httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", "https://example.test"))
    return cls(f"Error code: {status} - key was {KEY}", response=response, body=body)


def _groq_provider_raising(exc: Exception) -> GroqProvider:
    provider = GroqProvider(KEY, "some-model")

    def create(**_: object) -> None:
        raise exc

    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))  # type: ignore[assignment]
    return provider


def _call_groq(exc: Exception) -> None:
    _groq_provider_raising(exc).generate("s", "u", True, 0.2, 5.0)


def test_groq_429_becomes_rate_limit_with_retry_after() -> None:
    with pytest.raises(RateLimitError) as info:
        _call_groq(_groq_error(groq.RateLimitError, 429, {"retry-after": "3"}))
    assert info.value.retry_after == 3.0


def test_groq_429_without_header_has_no_retry_after() -> None:
    with pytest.raises(RateLimitError) as info:
        _call_groq(_groq_error(groq.RateLimitError, 429))
    assert info.value.retry_after is None


def test_groq_401_becomes_auth_error() -> None:
    with pytest.raises(AuthError, match="Groq rejected the API key"):
        _call_groq(_groq_error(groq.AuthenticationError, 401))


def test_groq_5xx_becomes_transient() -> None:
    with pytest.raises(TransientError):
        _call_groq(_groq_error(groq.InternalServerError, 503))


def test_groq_timeout_and_connection_errors_become_transient() -> None:
    request = httpx.Request("POST", "https://example.test")
    with pytest.raises(TransientError):
        _call_groq(groq.APITimeoutError(request=request))
    with pytest.raises(TransientError):
        _call_groq(groq.APIConnectionError(request=request))


def test_groq_400_and_404_become_bad_request() -> None:
    with pytest.raises(BadRequestError):
        _call_groq(_groq_error(groq.BadRequestError, 400))
    with pytest.raises(BadRequestError):
        _call_groq(_groq_error(groq.NotFoundError, 404))  # e.g. wrong model name


def test_groq_json_validate_failed_becomes_invalid_output() -> None:
    exc = _groq_error(groq.BadRequestError, 400, body={"error": {"code": "json_validate_failed"}})
    exc.args = ("Error code: 400 - json_validate_failed",)
    exc.message = "json_validate_failed"
    with pytest.raises(InvalidOutputError):
        _call_groq(exc)


def test_api_key_never_appears_in_error_messages() -> None:
    with pytest.raises(AuthError) as info:
        _call_groq(_groq_error(groq.AuthenticationError, 401))
    assert KEY not in str(info.value)


def test_groq_success_returns_text_and_token_counts() -> None:
    provider = GroqProvider(KEY, "some-model")
    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=7),
    )
    provider._client = SimpleNamespace(  # type: ignore[assignment]
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: reply))
    )
    result = provider.generate("s", "u", True, 0.0, 5.0)
    assert (result.text, result.input_tokens, result.output_tokens) == ('{"ok": true}', 12, 7)


def test_groq_without_key_is_not_configured() -> None:
    assert GroqProvider("", "model").is_configured is False
    assert GroqProvider("key", "").is_configured is False
    assert GroqProvider("key", "model").is_configured is True


# ---------------------------------------------------------------- Gemini


def _call_gemini(exc: Exception) -> None:
    provider = GeminiProvider(KEY, "some-model")

    def generate_content(**_: object) -> None:
        raise exc

    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))  # type: ignore[assignment]
    provider.generate("s", "u", True, 0.2, 5.0)


def _client_error(code: int, message: str = "boom", status: str = "") -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"code": code, "message": message, "status": status}})


def test_gemini_429_becomes_rate_limit() -> None:
    with pytest.raises(RateLimitError):
        _call_gemini(_client_error(429, "quota exceeded"))


def test_gemini_429_retry_delay_is_read() -> None:
    exc = genai_errors.ClientError(
        429,
        {"error": {"code": 429, "message": "quota", "details": [{"retryDelay": "12s"}]}},
    )
    with pytest.raises(RateLimitError) as info:
        _call_gemini(exc)
    assert info.value.retry_after == 12.0


def test_gemini_invalid_key_reported_as_400_becomes_auth_error() -> None:
    with pytest.raises(AuthError, match="Gemini rejected the API key"):
        _call_gemini(_client_error(400, "API key not valid. Please pass a valid API key."))


def test_gemini_403_becomes_auth_error() -> None:
    with pytest.raises(AuthError):
        _call_gemini(_client_error(403, "permission denied"))


def test_gemini_other_400_and_404_become_bad_request() -> None:
    with pytest.raises(BadRequestError):
        _call_gemini(_client_error(400, "invalid argument"))
    with pytest.raises(BadRequestError):
        _call_gemini(_client_error(404, "model not found"))


def test_gemini_5xx_becomes_transient() -> None:
    with pytest.raises(TransientError):
        _call_gemini(genai_errors.ServerError(503, {"error": {"code": 503, "message": "overloaded"}}))


def test_gemini_timeout_becomes_transient() -> None:
    with pytest.raises(TransientError):
        _call_gemini(httpx.ReadTimeout("timed out"))


def test_gemini_success_counts_thinking_tokens_as_output() -> None:
    provider = GeminiProvider(KEY, "some-model")
    reply = SimpleNamespace(
        text='{"ok": true}',
        usage_metadata=SimpleNamespace(prompt_token_count=20, candidates_token_count=5, thoughts_token_count=30),
    )
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: reply))  # type: ignore[assignment]
    result = provider.generate("s", "u", True, 0.0, 5.0)
    assert (result.input_tokens, result.output_tokens) == (20, 35)


def test_gemini_empty_reply_is_invalid_output() -> None:
    provider = GeminiProvider(KEY, "some-model")
    reply = SimpleNamespace(text=None, usage_metadata=None)
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_: reply))  # type: ignore[assignment]
    with pytest.raises(InvalidOutputError):
        provider.generate("s", "u", True, 0.0, 5.0)


def test_redact_hides_secrets() -> None:
    assert redact("bad key sk-abc used", "sk-abc") == "bad key *** used"
    assert redact("nothing to hide", "") == "nothing to hide"
