from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmCall(Base):
    """One row per LLM attempt (including failed ones). No prompts/responses unless LLM_LOG_PAYLOADS=true."""

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_created_at", "created_at"), Index("ix_llm_calls_purpose", "purpose"))

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purpose: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    success: Mapped[bool]
    error_type: Mapped[str | None] = mapped_column(String(30))
    attempt: Mapped[int] = mapped_column(Integer)
    fallback_used: Mapped[bool] = mapped_column(default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    # Only filled when LLM_LOG_PAYLOADS=true (they can contain student answers).
    prompt_text: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
