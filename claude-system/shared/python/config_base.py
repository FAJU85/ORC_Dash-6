"""Config base مشترك — انسخه لكل مشروع."""
from pydantic_settings import BaseSettings
from functools import lru_cache

class BaseConfig(BaseSettings):
    debug: bool = False
    app_name: str = "My App"
    version: str = "1.0.0"
    anthropic_api_key: str = ""
    bot_token: str = ""
    admin_id: int = 0
    allowed_users: list[int] = []
    database_url: str = "sqlite+aiosqlite:///app.db"
    secret_key: str = "change-in-production"

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache
def get_settings() -> BaseConfig:
    return BaseConfig()
