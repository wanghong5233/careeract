from pathlib import Path

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    worker_api_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:43111")
    worker_api_key_file: Path | None = None
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "careeract"


settings = Settings()
