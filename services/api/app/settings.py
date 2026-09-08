from functools import lru_cache

from pydantic import AnyHttpUrl, PositiveFloat, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: PostgresDsn
    agno_database_url: PostgresDsn
    agno_database_schema: str = "agno"
    auth_jwks_url: AnyHttpUrl
    auth_issuer: str
    auth_audience: str
    auth_jwt_algorithms: tuple[str, ...] = ("EdDSA",)
    auth_jwks_timeout_seconds: PositiveFloat = 5.0
    litellm_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:4000")
    litellm_master_key: SecretStr
    litellm_model: str = "careeract-default"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
