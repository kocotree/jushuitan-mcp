from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from .config import PROJECT_ROOT
from .errors import JstConfigError


MCP_READ_SCOPE = "jushuitan:read"
FEISHU_AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"

PENDING_TTL_SECONDS = 10 * 60
AUTHORIZATION_CODE_TTL_SECONDS = 5 * 60
ACCESS_TOKEN_TTL_SECONDS = 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
REFRESH_TOKEN_REUSE_GRACE_SECONDS = 60


@dataclass(frozen=True)
class OAuthSettings:
    issuer_url: str
    resource_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_redirect_uri: str
    allowed_tenant_key: str
    database_path: Path

    @classmethod
    def load(cls, env_file: str | Path | None = None) -> "OAuthSettings":
        configured_env_file = os.getenv("JST_ENV_FILE")
        path = Path(env_file or configured_env_file or PROJECT_ROOT / ".env")
        load_dotenv(path, override=False)

        public_url = os.getenv("JST_MCP_PUBLIC_URL", "").strip().rstrip("/")
        if not public_url.startswith("https://"):
            raise JstConfigError("JST_MCP_PUBLIC_URL must be an https:// URL.")
        mcp_path = os.getenv("JST_MCP_PATH", "/mcp").strip()
        if not mcp_path.startswith("/"):
            raise JstConfigError("JST_MCP_PATH must start with /.")

        app_id = os.getenv("FEISHU_APP_ID", "").strip()
        app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
        tenant_key = os.getenv("FEISHU_ALLOWED_TENANT_KEY", "").strip()
        if not app_id or not app_secret or not tenant_key:
            raise JstConfigError(
                "FEISHU_APP_ID, FEISHU_APP_SECRET and "
                "FEISHU_ALLOWED_TENANT_KEY are required."
            )

        redirect_uri = os.getenv(
            "FEISHU_REDIRECT_URI",
            f"{public_url}/oauth/feishu/callback",
        ).strip()
        if not redirect_uri.startswith("https://"):
            raise JstConfigError("FEISHU_REDIRECT_URI must be an https:// URL.")
        database_value = os.getenv("JST_MCP_OAUTH_DB_PATH", "").strip()
        database_path = (
            Path(database_value)
            if database_value
            else PROJECT_ROOT / ".runtime" / "oauth.db"
        )
        return cls(
            issuer_url=public_url,
            resource_url=f"{public_url}{mcp_path}",
            feishu_app_id=app_id,
            feishu_app_secret=app_secret,
            feishu_redirect_uri=redirect_uri,
            allowed_tenant_key=tenant_key,
            database_path=database_path,
        )

    def to_mcp_auth_settings(self) -> AuthSettings:
        return AuthSettings(
            issuer_url=self.issuer_url,
            resource_server_url=self.resource_url,
            required_scopes=[MCP_READ_SCOPE],
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=[MCP_READ_SCOPE],
                default_scopes=[MCP_READ_SCOPE],
            ),
        )


class FeishuOAuthProvider:
    """Bridge Feishu login to persistent, opaque MCP OAuth tokens."""

    def __init__(
        self,
        settings: OAuthSettings,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.http_transport = http_transport
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        self.settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_authorizations (
                    token_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    client_state TEXT,
                    code_challenge TEXT NOT NULL,
                    redirect_uri_explicit INTEGER NOT NULL,
                    scopes TEXT NOT NULL,
                    resource TEXT,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS authorization_codes (
                    token_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    redirect_uri_explicit INTEGER NOT NULL,
                    scopes TEXT NOT NULL,
                    resource TEXT,
                    subject TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    token_hash TEXT PRIMARY KEY,
                    token_type TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    resource TEXT,
                    subject TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    session_expires_at INTEGER NOT NULL,
                    rotated_at INTEGER
                );
                """
            )
            token_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(oauth_tokens)")
            }
            if "rotated_at" not in token_columns:
                connection.execute(
                    "ALTER TABLE oauth_tokens ADD COLUMN rotated_at INTEGER"
                )
        if os.name != "nt":
            self.settings.database_path.chmod(0o600)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _new_token() -> str:
        return secrets.token_urlsafe(32)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM oauth_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row["payload"])

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO oauth_clients (client_id, payload)
                VALUES (?, ?)
                """,
                (client_info.client_id, client_info.model_dump_json()),
            )

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        feishu_state = self._new_token()
        now = int(time.time())
        scopes = params.scopes or [MCP_READ_SCOPE]
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pending_authorizations (
                    token_hash, client_id, redirect_uri, client_state,
                    code_challenge, redirect_uri_explicit, scopes, resource,
                    expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._hash_token(feishu_state),
                    client.client_id,
                    str(params.redirect_uri),
                    params.state,
                    params.code_challenge,
                    int(params.redirect_uri_provided_explicitly),
                    json.dumps(scopes),
                    params.resource or self.settings.resource_url,
                    now + PENDING_TTL_SECONDS,
                ),
            )
        query = urlencode(
            {
                "client_id": self.settings.feishu_app_id,
                "response_type": "code",
                "redirect_uri": self.settings.feishu_redirect_uri,
                "state": feishu_state,
            }
        )
        return f"{FEISHU_AUTHORIZE_URL}?{query}"

    async def handle_feishu_callback(self, request: Request) -> Response:
        state = request.query_params.get("state")
        if not state:
            return JSONResponse({"error": "missing_state"}, status_code=400)
        pending = self._consume_pending_authorization(state)
        if pending is None:
            return JSONResponse({"error": "invalid_or_expired_state"}, status_code=400)

        upstream_error = request.query_params.get("error")
        code = request.query_params.get("code")
        if upstream_error or not code:
            return self._redirect_client_error(pending, "access_denied")

        try:
            identity = await self._get_feishu_identity(code)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return self._redirect_client_error(pending, "server_error")

        if identity.get("tenant_key") != self.settings.allowed_tenant_key:
            return self._redirect_client_error(pending, "access_denied")
        subject = identity.get("open_id")
        if not isinstance(subject, str) or not subject:
            return self._redirect_client_error(pending, "server_error")

        authorization_code = self._new_token()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO authorization_codes (
                    token_hash, client_id, redirect_uri, code_challenge,
                    redirect_uri_explicit, scopes, resource, subject, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._hash_token(authorization_code),
                    pending["client_id"],
                    pending["redirect_uri"],
                    pending["code_challenge"],
                    pending["redirect_uri_explicit"],
                    pending["scopes"],
                    pending["resource"],
                    subject,
                    int(time.time()) + AUTHORIZATION_CODE_TTL_SECONDS,
                ),
            )
        query: dict[str, str] = {"code": authorization_code}
        if pending["client_state"]:
            query["state"] = pending["client_state"]
        return RedirectResponse(self._append_query(pending["redirect_uri"], query))

    def _consume_pending_authorization(self, state: str) -> sqlite3.Row | None:
        token_hash = self._hash_token(state)
        with self._connect() as connection:
            row = connection.execute(
                "DELETE FROM pending_authorizations WHERE token_hash = ? RETURNING *",
                (token_hash,),
            ).fetchone()
        if row is None or row["expires_at"] <= int(time.time()):
            return None
        return row

    def _redirect_client_error(
        self,
        pending: sqlite3.Row,
        error: str,
    ) -> RedirectResponse:
        query = {"error": error}
        if pending["client_state"]:
            query["state"] = pending["client_state"]
        return RedirectResponse(self._append_query(pending["redirect_uri"], query))

    @staticmethod
    def _append_query(url: str, values: dict[str, str]) -> str:
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query.extend(values.items())
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    async def _get_feishu_identity(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            transport=self.http_transport,
            timeout=10,
        ) as client:
            token_response = await client.post(
                FEISHU_TOKEN_URL,
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={
                    "grant_type": "authorization_code",
                    "client_id": self.settings.feishu_app_id,
                    "client_secret": self.settings.feishu_app_secret,
                    "code": code,
                    "redirect_uri": self.settings.feishu_redirect_uri,
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            if token_payload.get("code") not in (None, 0):
                raise ValueError("Feishu token request was rejected")
            access_token = token_payload["access_token"]
            user_response = await client.get(
                FEISHU_USER_INFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
            user_response.raise_for_status()
            payload = user_response.json()
        if payload.get("code") != 0:
            raise ValueError("Feishu user info request was rejected")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("Feishu user info response has no data object")
        return data

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM authorization_codes WHERE token_hash = ?",
                (self._hash_token(authorization_code),),
            ).fetchone()
        if (
            row is None
            or row["client_id"] != client.client_id
            or row["expires_at"] <= int(time.time())
        ):
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=json.loads(row["scopes"]),
            expires_at=row["expires_at"],
            client_id=row["client_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=row["redirect_uri"],
            redirect_uri_provided_explicitly=bool(row["redirect_uri_explicit"]),
            resource=row["resource"],
            subject=row["subject"],
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        with self._connect() as connection:
            deleted = connection.execute(
                "DELETE FROM authorization_codes WHERE token_hash = ? AND client_id = ?",
                (self._hash_token(authorization_code.code), client.client_id),
            ).rowcount
        if deleted != 1:
            raise TokenError("invalid_grant", "Authorization code was already used")
        return self._issue_token_pair(
            client.client_id,
            authorization_code.scopes,
            authorization_code.resource or self.settings.resource_url,
            authorization_code.subject or "",
        )

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        row = self._load_token(refresh_token, "refresh")
        if row is None or row["client_id"] != client.client_id:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=json.loads(row["scopes"]),
            expires_at=row["expires_at"],
            subject=row["subject"],
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        now = int(time.time())
        token_hash = self._hash_token(refresh_token.token)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT client_id, resource, expires_at, session_expires_at, rotated_at
                FROM oauth_tokens
                WHERE token_hash = ? AND token_type = 'refresh'
                """,
                (token_hash,),
            ).fetchone()
            if (
                row is None
                or row["client_id"] != client.client_id
                or row["expires_at"] <= now
                or row["session_expires_at"] <= now
            ):
                raise TokenError("invalid_grant", "Refresh token is invalid or expired")

            rotated_at = row["rotated_at"]
            if rotated_at is None:
                connection.execute(
                    """
                    UPDATE oauth_tokens
                    SET rotated_at = ?, expires_at = MIN(expires_at, ?)
                    WHERE token_hash = ? AND token_type = 'refresh'
                    """,
                    (
                        now,
                        now + REFRESH_TOKEN_REUSE_GRACE_SECONDS,
                        token_hash,
                    ),
                )
            elif rotated_at + REFRESH_TOKEN_REUSE_GRACE_SECONDS <= now:
                raise TokenError("invalid_grant", "Refresh token reuse window expired")

        return self._issue_token_pair(
            client.client_id,
            scopes,
            row["resource"] or self.settings.resource_url,
            refresh_token.subject or "",
            session_expires_at=row["session_expires_at"],
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = self._load_token(token, "access")
        if row is None:
            return None
        return AccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=json.loads(row["scopes"]),
            expires_at=row["expires_at"],
            resource=row["resource"],
            subject=row["subject"],
        )

    def _load_token(self, token: str, token_type: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_tokens WHERE token_hash = ? AND token_type = ?",
                (self._hash_token(token), token_type),
            ).fetchone()
        if row is None or row["expires_at"] <= int(time.time()):
            return None
        return row

    def _issue_token_pair(
        self,
        client_id: str,
        scopes: list[str],
        resource: str,
        subject: str,
        *,
        session_expires_at: int | None = None,
    ) -> OAuthToken:
        access_token = self._new_token()
        refresh_token = self._new_token()
        now = int(time.time())
        session_expires_at = session_expires_at or now + SESSION_TTL_SECONDS
        access_expires_at = min(now + ACCESS_TOKEN_TTL_SECONDS, session_expires_at)
        refresh_expires_at = min(
            now + REFRESH_TOKEN_TTL_SECONDS,
            session_expires_at,
        )
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO oauth_tokens (
                    token_hash, token_type, client_id, scopes, resource,
                    subject, expires_at, session_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        self._hash_token(access_token),
                        "access",
                        client_id,
                        json.dumps(scopes),
                        resource,
                        subject,
                        access_expires_at,
                        session_expires_at,
                    ),
                    (
                        self._hash_token(refresh_token),
                        "refresh",
                        client_id,
                        json.dumps(scopes),
                        resource,
                        subject,
                        refresh_expires_at,
                        session_expires_at,
                    ),
                ),
            )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=access_expires_at - now,
            scope=" ".join(scopes),
            refresh_token=refresh_token,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        raw_token = token.token
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM oauth_tokens WHERE token_hash = ?",
                (self._hash_token(raw_token),),
            )
