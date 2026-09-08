from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn
    agno_database_url: PostgresDsn
    litellm_base_url: str = "http://localhost:4000"
    litellm_master_key: str
    litellm_model: str = "careeract-default"
    web_origin: str = "http://localhost:3000"


settings = Settings()  # type: ignore[call-arg]  # Values are validated from the environment.
