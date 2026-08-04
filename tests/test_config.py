from pathlib import Path

import pytest

from jst_connector.config import Settings
from jst_connector.errors import JstConfigError


def test_settings_loads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JST_APP_KEY", raising=False)
    monkeypatch.delenv("JST_APP_SECRET", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JST_APP_KEY=app-key\nJST_APP_SECRET=app-secret\nJST_ENDPOINT=https://example.test\n",
        encoding="utf-8",
    )
    settings = Settings.load(env_file)
    assert settings.app_key == "app-key"
    assert settings.app_secret == "app-secret"
    assert settings.endpoint == "https://example.test"


def test_settings_rejects_missing_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JST_APP_KEY", raising=False)
    monkeypatch.delenv("JST_APP_SECRET", raising=False)
    with pytest.raises(JstConfigError):
        Settings.load(tmp_path / "missing.env")
