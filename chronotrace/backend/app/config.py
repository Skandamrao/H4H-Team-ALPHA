"""
ChronoTrace AI — Application Configuration
All settings are loaded from environment variables / .env file.
Never hard-code API keys.
"""
from __future__ import annotations

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Provider: "gemini" or "openai"
    llm_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Database
    database_url: str = "sqlite+aiosqlite:///./chronotrace.db"

    # App
    debug: bool = True
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

