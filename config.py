"""
Configuration management for CoolDL project using Pydantic Settings.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from functools import lru_cache


class DatabaseSettings(BaseModel):
    """Database configuration settings."""
    
    path: str = Field(default="cooldl.db", env="DATABASE")
    connection_timeout: int = Field(default=20, env="DB_CONNECTION_TIMEOUT")
    busy_timeout: int = Field(default=20000, env="DB_BUSY_TIMEOUT")
    journal_mode: str = Field(default="WAL", env="DB_JOURNAL_MODE")
    
    @property
    def absolute_path(self) -> str:
        """Get absolute database path."""
        return os.path.abspath(self.path)


class BotSettings(BaseModel):
    """Telegram bot configuration settings."""
    
    token: str = Field(default="dummy_token_for_development", env="BOT_TOKEN")
    channel_id: int = Field(default=0, env="CHANNEL_ID")
    log_channel_id: int = Field(default=0, env="LOG_CHANNEL_ID")
    caption: str = Field(default="", env="CAPTION")
    
    @validator("log_channel_id")
    def validate_log_channel_id(cls, v, values):
        """Use CHANNEL_ID as fallback if LOG_CHANNEL_ID is not set."""
        if v == 0 and "channel_id" in values and values["channel_id"] != 0:
            return values["channel_id"]
        return v


class RateLimitSettings(BaseModel):
    """Rate limiting and resource management settings."""
    
    max_file_size_mb: int = Field(default=500, env="MAX_FILE_SIZE")
    max_concurrent: int = Field(default=3, env="MAX_CONCURRENT")
    max_downloads_per_hour: int = Field(default=10, env="MAX_DOWNLOADS_PER_HOUR")
    file_retention_days: int = Field(default=7, env="FILE_RETENTION_DAYS")
    
    @property
    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024


class DownloadSettings(BaseModel):
    """Download configuration settings."""
    
    timeout_seconds: int = Field(default=300, env="DOWNLOAD_TIMEOUT")
    cookies_file: str = Field(default="", env="COOKIES_FILE")
    download_dir: str = Field(default="downloads", env="DOWNLOAD_DIR")
    retries: int = Field(default=5, env="DOWNLOAD_RETRIES")
    fragment_retries: int = Field(default=15, env="FRAGMENT_RETRIES")
    concurrent_fragments: int = Field(default=4, env="CONCURRENT_FRAGMENTS")
    socket_timeout: int = Field(default=30, env="SOCKET_TIMEOUT")
    
    @property
    def download_dir_path(self) -> Path:
        """Get download directory as Path object."""
        path = Path(self.download_dir)
        path.mkdir(exist_ok=True, parents=True)
        return path


class WebSettings(BaseModel):
    """Web dashboard configuration settings."""
    
    session_secret: str = Field(default="secret-fahad-strong-key", env="SESSION_SECRET")
    items_per_page: int = Field(default=50, env="ITEMS_PER_PAGE")
    restart_endpoint: str = Field(default="http://localhost:7070/restart", env="RESTART_ENDPOINT")
    
    # Admin credentials
    admin_username: str = Field(default="Fahad", env="ADMIN_USERNAME")
    admin_password: str = Field(default="213325@Fx9", env="ADMIN_PASSWORD")


class TelegramSettings(BaseModel):
    """Telegram-specific settings."""
    
    request_connect_timeout: int = Field(default=20, env="TELEGRAM_CONNECT_TIMEOUT")
    request_read_timeout: int = Field(default=180, env="TELEGRAM_READ_TIMEOUT")
    polling_max_retries: int = Field(default=3, env="POLLING_MAX_RETRIES")
    polling_conflict_wait_base: int = Field(default=30, env="POLLING_CONFLICT_WAIT_BASE")
    
    # HTTP headers for downloads
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        env="USER_AGENT"
    )
    
    # Platform-specific headers
    youtube_referer: str = Field(
        default="https://www.youtube.com/shorts/",
        env="YOUTUBE_REFERER"
    )
    
    tiktok_referer: str = Field(
        default="https://www.tiktok.com/",
        env="TIKTOK_REFERER"
    )
    
    accept_header: str = Field(
        default="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        env="ACCEPT_HEADER"
    )


class Settings(BaseModel):
    """Main settings class that combines all configuration sections."""
    
    # Environment
    environment: str = Field(default="production", env="ENVIRONMENT")
    
    # Component settings
    database: DatabaseSettings = DatabaseSettings()
    bot: BotSettings = BotSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    download: DownloadSettings = DownloadSettings()
    web: WebSettings = WebSettings()
    telegram: TelegramSettings = TelegramSettings()
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Timezone
    timezone: str = Field(default="Asia/Riyadh", env="TIMEZONE")
    
    # Random ID generation
    random_id_length: int = Field(default=5, env="RANDOM_ID_LENGTH")
    
    # File cleanup
    cleanup_enabled: bool = Field(default=False, env="CLEANUP_ENABLED")
    cleanup_interval_hours: int = Field(default=24, env="CLEANUP_INTERVAL_HOURS")
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of {allowed_levels}")
        return v.upper()
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        
        # Allow nested field names like DATABASE_PATH
        fields = {
            "database": {"env": "DATABASE"},
        }


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to avoid reloading settings on every access.
    """
    return Settings()


# Create a global settings instance for easy access
settings = get_settings()