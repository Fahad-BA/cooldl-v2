"""
Configuration management for CoolDL project using Pydantic Settings.
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from functools import lru_cache


class DatabaseSettings(BaseModel):
    """Database configuration settings."""
    
    path: str = Field(default="cooldl.db")
    connection_timeout: int = Field(default=20)
    busy_timeout: int = Field(default=20000)
    journal_mode: str = Field(default="WAL")
    
    @property
    def absolute_path(self) -> str:
        """Get absolute database path."""
        return os.path.abspath(self.path)


class BotSettings(BaseModel):
    """Telegram bot configuration settings."""
    
    token: str = Field(default="dummy_token_for_development")
    channel_id: int = Field(default=0)
    log_channel_id: int = Field(default=0)
    caption: str = Field(default="")
    
    @field_validator('log_channel_id')
    @classmethod
    def validate_log_channel_id(cls, v, info):
        """Use CHANNEL_ID as fallback if LOG_CHANNEL_ID is not set."""
        if v == 0 and hasattr(info.data, 'channel_id') and info.data['channel_id'] != 0:
            return info.data['channel_id']
        return v


class RateLimitSettings(BaseModel):
    """Rate limiting and resource management settings."""
    
    max_file_size_mb: int = Field(default=500)
    max_concurrent: int = Field(default=3)
    max_downloads_per_hour: int = Field(default=10)
    file_retention_days: int = Field(default=7)
    
    @property
    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.max_file_size_mb * 1024 * 1024


class DownloadSettings(BaseModel):
    """Download configuration settings."""
    
    timeout_seconds: int = Field(default=300)
    cookies_file: str = Field(default="")
    download_dir: str = Field(default="downloads")
    retries: int = Field(default=5)
    fragment_retries: int = Field(default=15)
    concurrent_fragments: int = Field(default=4)
    socket_timeout: int = Field(default=30)
    
    @property
    def download_dir_path(self) -> Path:
        """Get download directory as Path object."""
        path = Path(self.download_dir)
        path.mkdir(exist_ok=True, parents=True)
        return path


class WebSettings(BaseModel):
    """Web dashboard configuration settings."""
    
    session_secret: str = Field(default="secret-fahad-strong-key")
    items_per_page: int = Field(default=50)
    restart_endpoint: str = Field(default="http://localhost:7070/restart")
    
    # Admin credentials
    admin_username: str = Field(default="Fahad")
    admin_password: str = Field(default="213325@Fx9")


class TelegramSettings(BaseModel):
    """Telegram-specific settings."""
    
    request_connect_timeout: int = Field(default=20)
    request_read_timeout: int = Field(default=180)
    polling_max_retries: int = Field(default=3)
    polling_conflict_wait_base: int = Field(default=30)
    
    # HTTP headers for downloads
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    
    # Platform-specific headers
    youtube_referer: str = Field(
        default="https://www.youtube.com/shorts/"
    )
    
    tiktok_referer: str = Field(
        default="https://www.tiktok.com/"
    )
    
    accept_header: str = Field(
        default="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    )


class Settings(BaseModel):
    """Main settings class that combines all configuration sections."""
    
    # Environment
    environment: str = Field(default="production")
    
    # Component settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    bot: BotSettings = Field(default_factory=BotSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    download: DownloadSettings = Field(default_factory=DownloadSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    
    # Logging
    log_level: str = Field(default="INFO")
    
    # Timezone
    timezone: str = Field(default="Asia/Riyadh")
    
    # Random ID generation
    random_id_length: int = Field(default=5)
    
    # File cleanup
    cleanup_enabled: bool = Field(default=False)
    cleanup_interval_hours: int = Field(default=24)
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed_levels:
            raise ValueError(f"Log level must be one of {allowed_levels}")
        return v.upper()


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Uses lru_cache to avoid reloading settings on every access.
    """
    from dotenv import load_dotenv
    load_dotenv()
    
    # Create settings with environment variables
    return Settings(
        environment=os.getenv("ENVIRONMENT", "production"),
        database=DatabaseSettings(
            path=os.getenv("DATABASE", "cooldl.db"),
            connection_timeout=int(os.getenv("DB_CONNECTION_TIMEOUT", "20")),
            busy_timeout=int(os.getenv("DB_BUSY_TIMEOUT", "20000")),
            journal_mode=os.getenv("DB_JOURNAL_MODE", "WAL")
        ),
        bot=BotSettings(
            token=os.getenv("BOT_TOKEN", "dummy_token_for_development"),
            channel_id=int(os.getenv("CHANNEL_ID", "0")),
            log_channel_id=int(os.getenv("LOG_CHANNEL_ID", "0")),
            caption=os.getenv("CAPTION", "")
        ),
        rate_limit=RateLimitSettings(
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE", "500")),
            max_concurrent=int(os.getenv("MAX_CONCURRENT", "3")),
            max_downloads_per_hour=int(os.getenv("MAX_DOWNLOADS_PER_HOUR", "10")),
            file_retention_days=int(os.getenv("FILE_RETENTION_DAYS", "7"))
        ),
        download=DownloadSettings(
            timeout_seconds=int(os.getenv("DOWNLOAD_TIMEOUT", "300")),
            cookies_file=os.getenv("COOKIES_FILE", ""),
            download_dir=os.getenv("DOWNLOAD_DIR", "downloads"),
            retries=int(os.getenv("DOWNLOAD_RETRIES", "5")),
            fragment_retries=int(os.getenv("FRAGMENT_RETRIES", "15")),
            concurrent_fragments=int(os.getenv("CONCURRENT_FRAGMENTS", "4")),
            socket_timeout=int(os.getenv("SOCKET_TIMEOUT", "30"))
        ),
        web=WebSettings(
            session_secret=os.getenv("SESSION_SECRET", "secret-fahad-strong-key"),
            items_per_page=int(os.getenv("ITEMS_PER_PAGE", "50")),
            restart_endpoint=os.getenv("RESTART_ENDPOINT", "http://localhost:7070/restart"),
            admin_username=os.getenv("ADMIN_USERNAME", "Fahad"),
            admin_password=os.getenv("ADMIN_PASSWORD", "213325@Fx9")
        ),
        telegram=TelegramSettings(
            request_connect_timeout=int(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "20")),
            request_read_timeout=int(os.getenv("TELEGRAM_READ_TIMEOUT", "180")),
            polling_max_retries=int(os.getenv("POLLING_MAX_RETRIES", "3")),
            polling_conflict_wait_base=int(os.getenv("POLLING_CONFLICT_WAIT_BASE", "30")),
            user_agent=os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            youtube_referer=os.getenv("YOUTUBE_REFERER", "https://www.youtube.com/shorts/"),
            tiktok_referer=os.getenv("TIKTOK_REFERER", "https://www.tiktok.com/"),
            accept_header=os.getenv("ACCEPT_HEADER", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=os.getenv("TIMEZONE", "Asia/Riyadh"),
        random_id_length=int(os.getenv("RANDOM_ID_LENGTH", "5")),
        cleanup_enabled=os.getenv("CLEANUP_ENABLED", "False").lower() == "true",
        cleanup_interval_hours=int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))
    )


# Create a global settings instance for easy access
settings = get_settings()