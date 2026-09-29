from pathlib import Path

import pytest
from pydantic import PostgresDsn, ValidationError

from scripts.manage_model_key import KeyManagementError, load_key
from services.api.app.settings import DatabaseSettings, Settings


def test_runtime_does_not_fall_back_to_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_MASTER_KEY", "unused-test-management-key")
    with pytest.raises(ValidationError) as captured:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "litellm_api_key" in {error["loc"][0] for error in captured.value.errors()}
    assert "unused-test-management-key" not in str(captured.value)


def test_migrations_only_need_database_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LITELLM_API_KEY", "LITELLM_MASTER_KEY", "AUTH_ISSUER", "AUTH_AUDIENCE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/test")
    settings = DatabaseSettings(database_url=PostgresDsn("postgresql+asyncpg://localhost/test"))
    assert str(settings.database_url) == "postgresql+asyncpg://localhost/test"
    assert set(DatabaseSettings.model_fields) == {"database_url"}


def test_key_preparation_preserves_existing_secret(tmp_path: Path) -> None:
    path = tmp_path / ".env.litellm"
    initial = load_key(path, create=True)
    assert load_key(path, create=True) == initial
    with pytest.raises(KeyManagementError):
        load_key(tmp_path / "tracked.env", create=True)
    assert not (tmp_path / "tracked.env").exists()
