from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedToken:
    app_key: str
    access_token: str
    refresh_token: str
    access_expires_at: float
    refresh_expires_at: float

    def access_is_valid(self, now: float | None = None) -> bool:
        return bool(self.access_token) and (now or time.time()) < self.access_expires_at

    def refresh_is_valid(self, now: float | None = None) -> bool:
        return bool(self.refresh_token) and (now or time.time()) < self.refresh_expires_at


class TokenCache:
    def __init__(self, path: Path):
        self.path = path

    def load(self, app_key: str) -> CachedToken | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            token = CachedToken(**payload)
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
            return None
        return token if token.app_key == app_key else None

    def save(self, token: CachedToken) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(asdict(token), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temp_path.replace(self.path)
