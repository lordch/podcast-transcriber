import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Notion Configuration
    notion_api_key: str = ""
    notion_database_id: str = ""

    # OpenAI Configuration (for Whisper API)
    openai_api_key: str = ""

    # Optional: Webhook secret for validation
    webhook_secret: str = ""

    # Server Configuration
    port: int = 8000
    host: str = "0.0.0.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
