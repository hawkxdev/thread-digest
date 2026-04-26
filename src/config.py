"""Application configuration."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """App settings."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )

    # === Telegram Bot ===
    BOT_TOKEN: str = Field(..., description='Telegram bot token')
    ADMIN_USER_ID: int = Field(..., description='Admin user ID')
    ADMIN_CHAT_ID: int = Field(..., description='Chat ID for error alerts')

    # === DeepSeek AI ===
    DEEPSEEK_API_KEY: str = Field(..., description='DeepSeek API key')
    DEEPSEEK_BASE_URL: str = Field(
        default='https://api.deepseek.com',
        description='DeepSeek API base URL',
    )
    DEEPSEEK_MODEL: str = Field(
        default='deepseek-chat', description='DeepSeek model name'
    )
    DEEPSEEK_MAX_TOKENS: int = Field(
        default=4000, description='Max tokens per completion'
    )
    DEEPSEEK_TEMPERATURE: float = Field(
        default=0.3, description='Sampling temperature 0.0 to 1.0'
    )

    # === Reddit ===
    REDDIT_USER_AGENT: str = Field(
        ...,
        description='User Agent for Reddit API',
    )
    REDDIT_RATE_LIMIT_QPM: int = Field(
        default=5,
        description='Self limit QPM up to 10',
    )
    REDDIT_FETCH_TIMEOUT: float = Field(
        default=30.0, description='httpx request timeout in seconds'
    )
    REDDIT_COMMENT_LIMIT: int = Field(
        default=500, description='Max comments to parse'
    )
    REDDIT_COMMENT_DEPTH: int = Field(
        default=10, description='Max comment tree depth'
    )
    REDDIT_PROXY: str | None = Field(
        default=None,
        description='Optional proxy URL (http://user:pass@host:port)',
    )

    # === Database ===
    DATABASE_URL: str = Field(
        default='sqlite+aiosqlite:///./data/thread_digest.db',
        description='Database URL',
    )

    # === Logging ===
    log_level: str = Field(default='INFO', description='Logging level')
    debug: bool = Field(default=False, description='Debug mode')
    environment: str = Field(default='development', description='Environment')

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed:
            raise ValueError(f'Log level must be one of {allowed}')
        return v.upper()

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment."""
        allowed = ['development', 'staging', 'production']
        if v.lower() not in allowed:
            raise ValueError(f'Environment must be one of {allowed}')
        return v.lower()

    @field_validator('REDDIT_RATE_LIMIT_QPM')
    @classmethod
    def validate_qpm(cls, v: int) -> int:
        """Validate Reddit QPM."""
        if v < 1 or v > 10:
            raise ValueError('REDDIT_RATE_LIMIT_QPM must be between 1 and 10')
        return v

    @field_validator('DEEPSEEK_TEMPERATURE')
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Validate DeepSeek temperature."""
        if v < 0.0 or v > 1.0:
            raise ValueError('DEEPSEEK_TEMPERATURE must be in [0.0, 1.0]')
        return v

    @property
    def is_development(self) -> bool:
        """Development mode."""
        return self.environment == 'development'

    @property
    def is_production(self) -> bool:
        """Production mode."""
        return self.environment == 'production'


# === Singleton ===
_config: Config | None = None


def get_config() -> Config:
    """Config singleton."""
    global _config
    if _config is None:
        try:
            _config = Config()  # type: ignore[call-arg]
        except Exception as e:
            raise RuntimeError(f'Failed to initialize config: {e}') from e
    return _config
