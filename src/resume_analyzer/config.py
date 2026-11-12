"""Application settings, loaded from environment variables (and an optional .env file)."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All tunable limits live here so they are easy to find and to override in tests."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    max_upload_mb: float = 5
    max_pdf_pages: int = 10
    max_text_chars: int = 50_000
    max_jd_chars: int = 20_000
    llm_timeout_seconds: float = 20
    # Extra attempts after the first one when the LLM returns invalid JSON.
    llm_max_retries: int = 2
    # Deployment. PORT is set by hosts such as Render; rate limits protect a public demo.
    port: int = 8000
    rate_limit_max: int = 20  # analyses per window per client; 0 turns the limit off
    rate_limit_window_seconds: int = 600
    trust_proxy: bool = False  # believe X-Forwarded-For (only behind a proxy you control)
    cors_origins: str = ""  # comma-separated origins; empty = CORS disabled (same-origin only)

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value: object) -> object:
        # `.env.example` ships with `GEMINI_API_KEY=` (empty); treat that as "not configured".
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        """`cors_origins` as a clean list; empty when CORS is disabled."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        """Upload size limit in bytes."""
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def llm_configured(self) -> bool:
        """True when an API key is available, so the LLM layer can run."""
        return self.gemini_api_key is not None


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings (cached so .env is read once)."""
    return Settings()
