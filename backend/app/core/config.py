from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "Sleepy Apply"
    environment: str = "development"
    frontend_url: str = "http://localhost:3000"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "sleepy_apply"

    # Discord OAuth & Bot
    discord_client_id: str = "dev_discord_client_id"
    discord_client_secret: str = "dev_discord_client_secret"
    discord_redirect_uri: str = "http://localhost:3000/auth/callback"
    discord_bot_token: str = "dev_discord_bot_token"
    discord_webhook_url: str | None = None
    admin_emails: list[str] = ["knishant113@gmail.com"]
    admin_discord_ids: list[str] = []

    # Security
    jwt_secret: str = "dev_jwt_secret_change_me_in_production_key_12345"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30
    credential_encryption_key: str = "6GMqsdNUgmTmjL83IWDFHjpuFaMRA5NLlts_5WGWL9A="

    # Internal API
    internal_api_secret: str = "change-me-in-production"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
