from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, PositiveFloat, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: PostgresDsn


class Settings(DatabaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.litellm"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    agno_database_url: PostgresDsn
    agno_database_schema: str = "agno"
    auth_jwks_url: AnyHttpUrl
    auth_issuer: str
    auth_audience: str
    auth_jwt_algorithms: tuple[str, ...] = ("EdDSA",)
    auth_jwks_timeout_seconds: PositiveFloat = 5.0
    litellm_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:4000")
    litellm_api_key: SecretStr
    litellm_model: str = "careeract-default"
    litellm_config_path: Path = Path(__file__).resolve().parents[3] / "infra/litellm/config.yaml"
    synthetic_materials_enabled: bool = False

    @field_validator("litellm_api_key")
    @classmethod
    def require_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("LITELLM_API_KEY is required; initialize a restricted service key")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
