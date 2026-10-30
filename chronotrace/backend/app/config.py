"""
ChronoTrace AI — Application Configuration
All settings are loaded from environment variables / .env file.
Never hard-code API keys.
"""
from __future__ import annotations

from typing import Literal, Any
from pydantic import field_validator
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

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes", "on", "debug"):
                return True
            if v.lower() in ("false", "0", "no", "off", "release", "prod", "production"):
                return False
        return bool(v)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

