import logging
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine
from app.models.llm_call import LlmCall

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def default_session_factory() -> SessionFactory:
    """Sessions for the real database. Tests inject their own factory instead of using this."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


class CallLogger:
    """Writes one llm_calls row per attempt, in its own short-lived session.

    A failure here is swallowed: logging must never break an LLM call."""

    def __init__(self, session_factory: SessionFactory, log_payloads: bool = False) -> None:
        self._session_factory = session_factory
        self._log_payloads = log_payloads

    def record(
        self,
        *,
        purpose: str,
        provider: str,
        model: str,
        success: bool,
        error_type: str | None,
        attempt: int,
        fallback_used: bool,
        input_tokens: int | None,
        output_tokens: int | None,
        latency_ms: int,
        estimated_cost_usd: float,
        prompt_text: str | None = None,
        response_text: str | None = None,
    ) -> None:
        try:
            with self._session_factory() as session:
                session.add(
                    LlmCall(
                        purpose=purpose,
                        provider=provider,
                        model=model,
                        success=success,
                        error_type=error_type,
                        attempt=attempt,
                        fallback_used=fallback_used,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        estimated_cost_usd=estimated_cost_usd,
                        # Payloads are dropped unless explicitly enabled.
                        prompt_text=prompt_text if self._log_payloads else None,
                        response_text=response_text if self._log_payloads else None,
                    )
                )
                session.commit()
        except Exception as exc:  # noqa: BLE001 - logging must never break the call
            logger.warning("Could not write llm_calls row (%s)", type(exc).__name__)
