from pathlib import Path

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    steel_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:3001")
    steel_cdp_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:9223")
    viewer_public_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:43110")
    browser_database_url: SecretStr | None = None
    browser_command_public_key_file: Path | None = None
    browser_profile_key_file: Path | None = None


settings = Settings()
