"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Supabase
    supabase_url: str = "https://lnytnxmmemdzwqburtgf.supabase.co"
    supabase_anon_key: str = ""
    supabase_service_key: str = ""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080  # Default for production (Fly.io)
    debug: bool = False  # Default to production-safe

    # CORS - allow localhost and Tailnet (100.x.x.x) access
    cors_origins: list[str] = [
        "http://localhost:5174",
        "http://localhost:3000",
        "http://100.106.248.91:5174",  # Tailnet
    ]
    cors_allow_all: bool = False  # Set via env var for dev

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
