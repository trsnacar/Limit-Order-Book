"""Configuration management for production deployment."""

import os
from dataclasses import dataclass
from typing import Any

try:
    from pydantic_settings import BaseSettings
except ImportError:
    # Fallback for older pydantic versions
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text

    # Performance
    max_order_book_size: int = 100000
    enable_metrics: bool = True
    metrics_port: int = 9090

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_per_second: int = 1000

    # WebSocket
    ws_max_connections: int = 1000
    ws_ping_interval: int = 20

    # Order book
    enable_size_cache: bool = True
    cache_ttl_seconds: float = 0.1

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()

