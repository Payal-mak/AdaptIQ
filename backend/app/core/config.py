from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The .env file lives in the project root (adaptiq/), three levels above this file.
ENV_FILE: Path = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / the .env file."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = ""
    gemini_api_key: str = ""
    gemini_model: str = ""
    jwt_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    """Create the settings once and reuse them."""
    return Settings()  # type: ignore[call-arg]
