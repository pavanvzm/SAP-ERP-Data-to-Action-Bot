"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # App settings
    app_name: str = "SAP/ERP Data-to-Action Bot"
    app_version: str = "1.0.0"
    debug: bool = False
    is_development: bool = True
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # API Keys (set in production)
    openai_api_key: str = ""
    approval_webhook_secret: str = "dev-secret-change-in-production"
    
    # Database
    database_url: str = ":memory:"
    
    # Rate limiting
    rate_limit_per_minute: int = 100
    rate_limit_per_hour: int = 1000


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
