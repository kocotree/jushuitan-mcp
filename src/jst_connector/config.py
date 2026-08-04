from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import JstConfigError


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _default_token_cache_path() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "jst-connector" / "token.json"
    return Path.home() / ".cache" / "jst-connector" / "token.json"


@dataclass(frozen=True)
class HttpSettings:
    host: str = "127.0.0.1"
    port: int = 8000
    path: str = "/mcp"

    @classmethod
    def load(cls) -> "HttpSettings":
        try:
            port = int(os.getenv("JST_MCP_PORT", "8000"))
        except ValueError as exc:
            raise JstConfigError("JST_MCP_PORT 必须是整数。") from exc
        if not 1 <= port <= 65535:
            raise JstConfigError("JST_MCP_PORT 必须在 1 到 65535 之间。")
        path = os.getenv("JST_MCP_PATH", "/mcp").strip()
        if not path.startswith("/"):
            raise JstConfigError("JST_MCP_PATH 必须以 / 开头。")
        return cls(
            host=os.getenv("JST_MCP_HOST", "127.0.0.1").strip(),
            port=port,
            path=path,
        )


@dataclass(frozen=True)
class Settings:
    app_key: str
    app_secret: str
    endpoint: str = "https://openapi.jushuitan.com"
    timeout_seconds: float = 30.0
    token_cache_path: Path = _default_token_cache_path()

    @classmethod
    def load(cls, env_file: str | Path | None = None) -> "Settings":
        configured_env_file = os.getenv("JST_ENV_FILE")
        path = Path(env_file or configured_env_file or PROJECT_ROOT / ".env")
        load_dotenv(path, override=False)

        app_key = os.getenv("JST_APP_KEY", "").strip()
        app_secret = os.getenv("JST_APP_SECRET", "").strip()
        if not app_key or not app_secret:
            raise JstConfigError(
                f"缺少 JST_APP_KEY 或 JST_APP_SECRET。请在 {PROJECT_ROOT / '.env'} 中填写。"
            )

        endpoint = os.getenv("JST_ENDPOINT", "https://openapi.jushuitan.com").strip().rstrip("/")
        if not endpoint.startswith("https://"):
            raise JstConfigError("JST_ENDPOINT 必须使用 https://。")

        try:
            timeout_seconds = float(os.getenv("JST_TIMEOUT_SECONDS", "30"))
        except ValueError as exc:
            raise JstConfigError("JST_TIMEOUT_SECONDS 必须是数字。") from exc
        if timeout_seconds <= 0:
            raise JstConfigError("JST_TIMEOUT_SECONDS 必须大于 0。")

        cache_value = os.getenv("JST_TOKEN_CACHE_PATH", "").strip()
        token_cache_path = Path(cache_value) if cache_value else _default_token_cache_path()

        return cls(
            app_key=app_key,
            app_secret=app_secret,
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
            token_cache_path=token_cache_path,
        )
