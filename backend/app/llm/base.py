from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResult:
    """What a provider returns for one successful call."""

    text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def redact(text: str, *secrets: str) -> str:
    """Remove secrets (API keys) from a message before it is raised or logged."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


class LLMProvider(ABC):
    """One LLM vendor. Implementations translate SDK errors into app.llm.errors types."""

    name: str  # "groq", "gemini", ...

    def __init__(
        self,
        model: str,
        input_price_per_m: float = 0.0,
        output_price_per_m: float = 0.0,
    ) -> None:
        self.model = model
        self.input_price_per_m = input_price_per_m
        self.output_price_per_m = output_price_per_m

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """True if an API key and model name are set."""

    @abstractmethod
    def generate(
        self,
        system: str,
        user: str,
        json_mode: bool,
        temperature: float,
        timeout: float,
    ) -> LLMResult:
        """Make ONE call (no retries). Raise only errors from app.llm.errors."""
