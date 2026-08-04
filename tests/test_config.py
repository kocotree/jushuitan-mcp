from pathlib import Path

import pytest

from jst_connector.config import HttpSettings, Settings
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


def test_http_settings_loads_server_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JST_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("JST_MCP_PORT", "8080")
    monkeypatch.setenv("JST_MCP_PATH", "/internal/mcp")

    settings = HttpSettings.load()

    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.path == "/internal/mcp"


def test_http_settings_rejects_invalid_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JST_MCP_PORT", "70000")

    with pytest.raises(JstConfigError, match="JST_MCP_PORT"):
        HttpSettings.load()


def test_http_settings_rejects_path_without_leading_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JST_MCP_PATH", "mcp")

    with pytest.raises(JstConfigError, match="JST_MCP_PATH"):
        HttpSettings.load()
