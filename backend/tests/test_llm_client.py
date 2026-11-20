"""LLMClient tests. They use ONLY the fake provider (no network) and log into adaptiq_test."""

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.llm.call_log import default_session_factory
from app.llm.client import LLMClient
from app.llm.errors import (
    AuthError,
    BadRequestError,
    InvalidOutputError,
    RateLimitError,
    TransientError,
)
from app.llm.providers.fake_provider import FakeProvider
from app.models.llm_call import LlmCall

GOOD = '{"answer": "Paris"}'


class Answer(BaseModel):
    answer: str


def make_client(
    primary: FakeProvider,
    fallback: FakeProvider | None,
    factory: sessionmaker[Session],
    sleeps: list[float] | None = None,
    **kwargs: object,
) -> LLMClient:
    """A client whose sleep is recorded (not performed) and whose jitter is zero."""
    recorded = sleeps if sleeps is not None else []
    return LLMClient(
        primary,
        fallback,
        session_factory=factory,
        max_retries=2,
        max_retry_wait_seconds=20,
        sleep=recorded.append,
        rng=lambda: 0.0,
        **kwargs,  # type: ignore[arg-type]
    )


def rows(factory: sessionmaker[Session]) -> list[LlmCall]:
    with factory() as session:
        return list(session.scalars(select(LlmCall).order_by(LlmCall.id)))


def call_json(client: LLMClient) -> Answer:
    return client.generate_json("test_purpose", "sys", "user", Answer)


# ---------------------------------------------------------------- success and logging


def test_success_first_try_is_logged_once_with_tokens_and_latency(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    clock_values = iter([10.0, 10.25])  # start, end of the single attempt -> 250 ms
    client = make_client(
        FakeProvider([GOOD], name="groq"), None, llm_log_factory, clock=lambda: next(clock_values)
    )
    assert call_json(client) == Answer(answer="Paris")

    (row,) = rows(llm_log_factory)
    assert (row.purpose, row.provider, row.model) == ("test_purpose", "groq", "fake-model")
    assert row.success is True and row.error_type is None
    assert row.attempt == 1 and row.fallback_used is False
    assert (row.input_tokens, row.output_tokens) == (10, 5)
    assert row.latency_ms == 250


def test_generate_text_works_and_is_logged(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider(["hello there"])
    client = make_client(provider, None, llm_log_factory)
    assert client.generate_text("greet", "sys", "user") == "hello there"
    assert provider.calls[0].json_mode is False
    assert [r.purpose for r in rows(llm_log_factory)] == ["greet"]


def test_json_mode_is_requested_and_schema_is_in_the_prompt(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider([GOOD])
    call_json(make_client(provider, None, llm_log_factory))
    assert provider.calls[0].json_mode is True
    assert '"answer"' in provider.calls[0].system  # the JSON schema is described to the model


def test_json_wrapped_in_code_fences_is_accepted(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    client = make_client(FakeProvider(["```json\n" + GOOD + "\n```"]), None, llm_log_factory)
    assert call_json(client).answer == "Paris"


def test_estimated_cost_uses_price_per_million_tokens(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider([GOOD], input_price_per_m=1.0, output_price_per_m=2.0)
    call_json(make_client(provider, None, llm_log_factory))
    (row,) = rows(llm_log_factory)
    assert row.estimated_cost_usd == pytest.approx((10 * 1.0 + 5 * 2.0) / 1_000_000)


# ---------------------------------------------------------------- retries and backoff


def test_rate_limit_twice_then_success_logs_three_attempts_with_backoff(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    sleeps: list[float] = []
    provider = FakeProvider([RateLimitError("429"), RateLimitError("429"), GOOD])
    client = make_client(provider, None, llm_log_factory, sleeps)
    assert call_json(client).answer == "Paris"

    assert sleeps == [1.0, 2.0]  # exponential: 1s then 2s (jitter patched to 0)
    log = rows(llm_log_factory)
    assert [r.attempt for r in log] == [1, 2, 3]
    assert [r.success for r in log] == [False, False, True]
    assert [r.error_type for r in log] == ["rate_limit", "rate_limit", None]
    assert not any(r.fallback_used for r in log)


def test_jitter_adds_extra_wait(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    sleeps: list[float] = []
    client = LLMClient(
        FakeProvider([TransientError("503"), GOOD]),
        None,
        session_factory=llm_log_factory,
        sleep=sleeps.append,
        rng=lambda: 1.0,  # maximum jitter: +50%
    )
    call_json(client)
    assert sleeps == [1.5]


def test_retry_after_header_is_respected(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    sleeps: list[float] = []
    provider = FakeProvider([RateLimitError("429", retry_after=7.0), GOOD])
    call_json(make_client(provider, None, llm_log_factory, sleeps))
    assert sleeps == [7.0]


def test_very_long_retry_after_skips_waiting_and_uses_fallback(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    sleeps: list[float] = []
    primary = FakeProvider([RateLimitError("daily limit", retry_after=300.0)], name="groq")
    fallback = FakeProvider([GOOD], name="gemini")
    assert call_json(make_client(primary, fallback, llm_log_factory, sleeps)).answer == "Paris"
    assert sleeps == []  # did not sleep 5 minutes inside a student's interview
    assert len(primary.calls) == 1


def test_transient_errors_are_retried(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider([TransientError("timeout"), GOOD])
    call_json(make_client(provider, None, llm_log_factory))
    assert [r.error_type for r in rows(llm_log_factory)] == ["transient", None]


# ---------------------------------------------------------------- fallback


def test_primary_keeps_failing_then_fallback_is_used(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider([RateLimitError("429")] * 3, name="groq")  # 1 try + 2 retries
    fallback = FakeProvider([GOOD], name="gemini")
    assert call_json(make_client(primary, fallback, llm_log_factory)).answer == "Paris"

    log = rows(llm_log_factory)
    assert [(r.provider, r.attempt, r.success, r.fallback_used) for r in log] == [
        ("groq", 1, False, False),
        ("groq", 2, False, False),
        ("groq", 3, False, False),
        ("gemini", 1, True, True),
    ]


def test_fallback_also_failing_raises_last_error(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider([TransientError("p")] * 3, name="groq")
    fallback = FakeProvider([RateLimitError("f")] * 3, name="gemini")
    with pytest.raises(RateLimitError):
        call_json(make_client(primary, fallback, llm_log_factory))
    assert len(primary.calls) == 3 and len(fallback.calls) == 3


def test_fallback_without_api_key_is_skipped(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider([TransientError("down")] * 3, name="groq")
    fallback = FakeProvider([GOOD], name="gemini", configured=False)
    with pytest.raises(TransientError):
        call_json(make_client(primary, fallback, llm_log_factory))
    assert fallback.calls == []


def test_fallback_same_as_primary_is_not_used(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider([TransientError("down")] * 3, name="groq")
    twin = FakeProvider([GOOD], name="groq")
    with pytest.raises(TransientError):
        call_json(make_client(primary, twin, llm_log_factory))
    assert twin.calls == []


# ---------------------------------------------------------------- errors that must not retry


def test_auth_error_no_retry_no_fallback_clear_message(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    sleeps: list[float] = []
    primary = FakeProvider([AuthError("Groq rejected the API key")], name="groq")
    fallback = FakeProvider([GOOD], name="gemini")
    with pytest.raises(AuthError, match="Groq rejected the API key"):
        call_json(make_client(primary, fallback, llm_log_factory, sleeps))
    assert len(primary.calls) == 1 and fallback.calls == [] and sleeps == []
    (row,) = rows(llm_log_factory)
    assert row.success is False and row.error_type == "auth"


def test_bad_request_no_retry_no_fallback(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider([BadRequestError("unknown model")], name="groq")
    fallback = FakeProvider([GOOD], name="gemini")
    with pytest.raises(BadRequestError):
        call_json(make_client(primary, fallback, llm_log_factory))
    assert len(primary.calls) == 1 and fallback.calls == []


def test_unconfigured_primary_gives_clear_error_without_calling(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider([GOOD], name="groq", configured=False)
    with pytest.raises(AuthError, match="groq.*not set"):
        call_json(make_client(primary, None, llm_log_factory))
    assert primary.calls == []


# ---------------------------------------------------------------- invalid JSON


def test_invalid_json_then_valid_after_repair(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider(["this is not json", GOOD])
    assert call_json(make_client(provider, None, llm_log_factory)).answer == "Paris"

    assert len(provider.calls) == 2
    repair_prompt = provider.calls[1].user
    assert "invalid" in repair_prompt and "this is not json" in repair_prompt  # error is shown to the model
    log = rows(llm_log_factory)
    assert [(r.attempt, r.success, r.error_type) for r in log] == [(1, False, "invalid_output"), (2, True, None)]


def test_schema_mismatch_triggers_repair_too(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider(['{"wrong_field": 1}', GOOD])
    assert call_json(make_client(provider, None, llm_log_factory)).answer == "Paris"


def test_invalid_json_twice_raises_invalid_output_error(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    provider = FakeProvider(["nope", "still nope"])
    with pytest.raises(InvalidOutputError):
        call_json(make_client(provider, None, llm_log_factory))
    assert len(provider.calls) == 2  # original + exactly ONE repair


def test_invalid_output_on_primary_falls_back_with_its_own_repair(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider(["bad", "still bad"], name="groq")
    fallback = FakeProvider(["bad too", GOOD], name="gemini")  # fallback needs a repair as well
    assert call_json(make_client(primary, fallback, llm_log_factory)).answer == "Paris"

    assert len(primary.calls) == 2 and len(fallback.calls) == 2
    log = rows(llm_log_factory)
    assert [(r.provider, r.attempt, r.success, r.fallback_used) for r in log] == [
        ("groq", 1, False, False),
        ("groq", 2, False, False),
        ("gemini", 1, False, True),
        ("gemini", 2, True, True),
    ]


def test_invalid_output_everywhere_raises(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    primary = FakeProvider(["bad", "bad"], name="groq")
    fallback = FakeProvider(["bad", "bad"], name="gemini")
    with pytest.raises(InvalidOutputError):
        call_json(make_client(primary, fallback, llm_log_factory))
    assert len(primary.calls) == 2 and len(fallback.calls) == 2


def test_provider_side_invalid_output_is_repaired(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    """e.g. Groq's JSON mode failing server-side: raised as InvalidOutputError by the provider."""
    provider = FakeProvider([InvalidOutputError("provider JSON mode failed"), GOOD])
    assert call_json(make_client(provider, None, llm_log_factory)).answer == "Paris"


# ---------------------------------------------------------------- logging safety


def test_failure_while_writing_log_does_not_break_the_call() -> None:
    def broken_factory() -> Session:
        raise RuntimeError("database is down")

    client = LLMClient(FakeProvider([GOOD]), None, session_factory=broken_factory)  # type: ignore[arg-type]
    assert call_json(client).answer == "Paris"


def test_payload_columns_empty_by_default(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    call_json(make_client(FakeProvider([GOOD]), None, llm_log_factory))
    (row,) = rows(llm_log_factory)
    assert row.prompt_text is None and row.response_text is None


def test_payload_columns_filled_only_when_enabled(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    call_json(make_client(FakeProvider([GOOD]), None, llm_log_factory, log_payloads=True))
    (row,) = rows(llm_log_factory)
    assert row.response_text == GOOD
    assert row.prompt_text is not None and "USER:\nuser" in row.prompt_text


# ---------------------------------------------------------------- never touch the main database


def test_no_rows_are_written_to_the_main_database(llm_log_factory) -> None:  # type: ignore[no-untyped-def]
    main_engine = create_engine(get_settings().database_url)
    try:
        with main_engine.connect() as conn:
            if conn.execute(text("SELECT to_regclass('public.llm_calls')")).scalar() is None:
                pytest.skip("main database has no llm_calls table yet (run: alembic upgrade head)")
            before = conn.execute(text("SELECT count(*) FROM llm_calls")).scalar()

        provider = FakeProvider([RateLimitError("429"), GOOD])
        call_json(make_client(provider, None, llm_log_factory))
        assert len(rows(llm_log_factory)) == 2  # the rows went to adaptiq_test...

        with main_engine.connect() as conn:
            after = conn.execute(text("SELECT count(*) FROM llm_calls")).scalar()
        assert after == before  # ...and the main database did not change
    finally:
        main_engine.dispose()


def test_default_session_factory_is_blocked_in_tests() -> None:
    """The autouse guard turns any accidental use of the real DB into a loud failure."""
    from app.llm import client as client_module

    assert client_module.default_session_factory is not default_session_factory
    with pytest.raises(RuntimeError, match="adaptiq_test"):
        LLMClient.from_settings()
