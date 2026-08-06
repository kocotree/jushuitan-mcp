from pathlib import Path

import pytest

from jst_connector.config import HttpSettings, Settings
from jst_connector.errors import JstConfigError
from jst_connector.oauth import OAuthSettings


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


def test_oauth_settings_loads_feishu_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JST_MCP_PUBLIC_URL", "https://jushuitan-mcp.kktree.cn")
    monkeypatch.setenv("JST_MCP_PATH", "/mcp")
    monkeypatch.setenv("JST_MCP_OAUTH_DB_PATH", str(tmp_path / "oauth.db"))
    monkeypatch.setenv("FEISHU_APP_ID", "cli_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret")
    monkeypatch.setenv("FEISHU_ALLOWED_TENANT_KEY", "tenant-key")

    settings = OAuthSettings.load(tmp_path / "missing.env")

    assert settings.issuer_url == "https://jushuitan-mcp.kktree.cn"
    assert settings.resource_url == "https://jushuitan-mcp.kktree.cn/mcp"
    assert settings.feishu_redirect_uri == (
        "https://jushuitan-mcp.kktree.cn/oauth/feishu/callback"
    )
    assert settings.database_path == tmp_path / "oauth.db"


def test_oauth_settings_rejects_missing_feishu_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JST_MCP_PUBLIC_URL", "https://jushuitan-mcp.kktree.cn")
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv("FEISHU_ALLOWED_TENANT_KEY", raising=False)

    with pytest.raises(JstConfigError, match="FEISHU_APP_ID"):
        OAuthSettings.load(tmp_path / "missing.env")
