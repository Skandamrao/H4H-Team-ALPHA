"""Application configuration via environment variables."""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI Provider Keys
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # App
    app_env: str = "development"
    app_debug: bool = True
    app_secret_key: str = "changeme"

    # Database
    database_url: str = "sqlite:///./chronograph.db"

    # File upload
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 50

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # CORS — stored as a comma-separated string in .env
    allowed_origins_raw: str = "http://localhost:5173,http://localhost:3000"

    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/chronograph.log"

    @property
    def allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins_raw.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()

