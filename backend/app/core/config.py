from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file lives in the project root (adaptiq/), three levels above this file.
ENV_FILE: Path = Path(__file__).resolve().parents[3] / ".env"

MIN_JWT_SECRET_LENGTH = 32
PLACEHOLDER_PREFIX = "change-me"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / the .env file."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = ""
    llm_fallback_provider: str = "gemini"
    llm_timeout_seconds: float = 30
    llm_max_retries: int = 2  # retries after the first try, per provider
    llm_max_retry_wait_seconds: float = 20
    llm_log_payloads: bool = False
    # USD per 1 million tokens; 0 = free tier.
    groq_input_price_per_m: float = 0
    groq_output_price_per_m: float = 0
    gemini_input_price_per_m: float = 0
    gemini_output_price_per_m: float = 0
    jwt_secret: str = ""
    access_token_expire_minutes: int = 120
    # Empty = any email domain may self-register. Example: "college.edu".
    allowed_email_domain: str = ""


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them."""
    return Settings()  # type: ignore[call-arg]


def validate_jwt_secret(secret: str) -> None:
    """Refuse weak secrets. Called when the app starts."""
    if not secret.strip():
        raise RuntimeError("JWT_SECRET is empty. Set a long random value in .env.")
    if secret.startswith(PLACEHOLDER_PREFIX):
        raise RuntimeError("JWT_SECRET is still the placeholder from .env.example. Generate a real one.")
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET is too short (need at least {MIN_JWT_SECRET_LENGTH} characters).")
