import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import uvicorn
from starlette.testclient import TestClient

from jst_connector import mcp_server
from jst_connector.oauth import OAuthSettings


mcp = mcp_server.mcp


def _oauth_settings(tmp_path: Path) -> OAuthSettings:
    return OAuthSettings(
        issuer_url="https://jushuitan-mcp.kktree.cn",
        resource_url="https://jushuitan-mcp.kktree.cn/mcp",
        feishu_app_id="cli_test",
        feishu_app_secret="test-secret",
        feishu_redirect_uri="https://jushuitan-mcp.kktree.cn/oauth/feishu/callback",
        allowed_tenant_key="tenant-test",
        database_path=tmp_path / "oauth.db",
    )


def test_mcp_exposes_only_read_only_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "jst_inventory",
        "jst_orders",
        "jst_purchase",
        "jst_purchase_inbound",
        "jst_product_skus",
        "jst_product_styles",
    }


def test_http_health_check_reports_service_ready() -> None:
    with TestClient(mcp_server.create_http_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jushuitan-mcp"}


def test_http_mcp_requires_bearer_token_when_oauth_is_enabled(tmp_path: Path) -> None:
    app = mcp_server.create_http_app(oauth_settings=_oauth_settings(tmp_path))
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=payload,
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1:80",
            },
        )

    assert response.status_code == 401
    authenticate = response.headers["www-authenticate"]
    assert authenticate.startswith("Bearer ")
    assert (
        'resource_metadata="https://jushuitan-mcp.kktree.cn/'
        '.well-known/oauth-protected-resource/mcp"'
    ) in authenticate


def test_oauth_client_can_register_and_is_advertised(tmp_path: Path) -> None:
    app = mcp_server.create_http_app(oauth_settings=_oauth_settings(tmp_path))

    with TestClient(app) as client:
        metadata_response = client.get("/.well-known/oauth-authorization-server")
        registration_response = client.post(
            "/register",
            json={
                "client_name": "pytest MCP client",
                "redirect_uris": ["http://127.0.0.1:33418/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )

    assert metadata_response.status_code == 200
    assert metadata_response.json()["registration_endpoint"] == (
        "https://jushuitan-mcp.kktree.cn/register"
    )
    assert registration_response.status_code == 201
    registered = registration_response.json()
    assert registered["client_id"]
    assert registered.get("client_secret") is None
    assert registered["redirect_uris"] == ["http://127.0.0.1:33418/callback"]


def test_feishu_login_issues_mcp_token_for_allowed_tenant(tmp_path: Path) -> None:
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()

    async def feishu_api(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(200, json={"access_token": "feishu-user-token"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            assert request.headers["authorization"] == "Bearer feishu-user-token"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "open_id": "ou_allowed",
                        "tenant_key": "tenant-test",
                    },
                },
            )
        raise AssertionError(f"unexpected Feishu request: {request.url}")

    app = mcp_server.create_http_app(
        oauth_settings=_oauth_settings(tmp_path),
        oauth_http_transport=httpx.MockTransport(feishu_api),
    )

    with TestClient(app, follow_redirects=False) as client:
        registered = client.post(
            "/register",
            json={
                "client_name": "pytest MCP client",
                "redirect_uris": ["http://127.0.0.1:33418/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        ).json()
        authorize_response = client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": registered["client_id"],
                "redirect_uri": "http://127.0.0.1:33418/callback",
                "scope": "jushuitan:read",
                "state": "mcp-client-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://jushuitan-mcp.kktree.cn/mcp",
            },
        )
        feishu_location = authorize_response.headers["location"]
        feishu_state = parse_qs(urlparse(feishu_location).query)["state"][0]
        callback_response = client.get(
            "/oauth/feishu/callback",
            params={"code": "feishu-code", "state": feishu_state},
        )
        callback_query = parse_qs(urlparse(callback_response.headers["location"]).query)
        token_response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "client_id": registered["client_id"],
                "code": callback_query["code"][0],
                "redirect_uri": "http://127.0.0.1:33418/callback",
                "code_verifier": verifier,
                "resource": "https://jushuitan-mcp.kktree.cn/mcp",
            },
        )
        token_payload = token_response.json()
        mcp_response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            },
            headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token_payload['access_token']}",
                "Host": "127.0.0.1:80",
            },
        )
        refresh_response = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "client_id": registered["client_id"],
                "refresh_token": token_payload["refresh_token"],
                "scope": "jushuitan:read",
            },
        )
        reused_refresh_response = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "client_id": registered["client_id"],
                "refresh_token": token_payload["refresh_token"],
                "scope": "jushuitan:read",
            },
        )

    assert authorize_response.status_code in {302, 303, 307}
    assert urlparse(feishu_location).netloc == "accounts.feishu.cn"
    assert callback_response.status_code in {302, 303, 307}
    assert callback_query["state"] == ["mcp-client-state"]
    assert token_response.status_code == 200
    assert token_payload["access_token"] != "feishu-user-token"
    assert token_payload["token_type"] == "Bearer"
    assert token_payload["refresh_token"]
    assert mcp_response.status_code == 200
    assert refresh_response.status_code == 200
    assert refresh_response.json()["refresh_token"] != token_payload["refresh_token"]
    assert reused_refresh_response.status_code == 400
    database_bytes = (tmp_path / "oauth.db").read_bytes()
    assert token_payload["access_token"].encode() not in database_bytes
    assert token_payload["refresh_token"].encode() not in database_bytes


def test_feishu_login_rejects_other_tenant(tmp_path: Path) -> None:
    async def feishu_api(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/open-apis/authen/v2/oauth/token":
            return httpx.Response(200, json={"access_token": "feishu-user-token"})
        if request.url.path == "/open-apis/authen/v1/user_info":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "open_id": "ou_other_company",
                        "tenant_key": "other-tenant",
                    },
                },
            )
        raise AssertionError(f"unexpected Feishu request: {request.url}")

    app = mcp_server.create_http_app(
        oauth_settings=_oauth_settings(tmp_path),
        oauth_http_transport=httpx.MockTransport(feishu_api),
    )
    verifier = "b" * 43
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()

    with TestClient(app, follow_redirects=False) as client:
        registered = client.post(
            "/register",
            json={
                "client_name": "pytest MCP client",
                "redirect_uris": ["http://127.0.0.1:33418/callback"],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
            },
        ).json()
        authorize_response = client.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": registered["client_id"],
                "redirect_uri": "http://127.0.0.1:33418/callback",
                "state": "original-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        feishu_state = parse_qs(
            urlparse(authorize_response.headers["location"]).query
        )["state"][0]
        callback_response = client.get(
            "/oauth/feishu/callback",
            params={"code": "feishu-code", "state": feishu_state},
        )

    callback_query = parse_qs(urlparse(callback_response.headers["location"]).query)
    assert callback_response.status_code in {302, 303, 307}
    assert callback_query == {
        "error": ["access_denied"],
        "state": ["original-state"],
    }


def test_http_app_initializes_mcp_on_configured_path() -> None:
    app = mcp_server.create_http_app(
        streamable_http_path="/internal/mcp",
        host="127.0.0.1",
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/internal/mcp",
            json=payload,
            headers={
                "Accept": "application/json, text/event-stream",
                "Host": "127.0.0.1:80",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    data_line = next(line for line in response.text.splitlines() if line.startswith("data: "))
    result = json.loads(data_line.removeprefix("data: "))["result"]
    assert result["serverInfo"]["name"] == "Jushuitan Read Only"
    assert result["capabilities"]["tools"] == {"listChanged": False}


def test_http_main_runs_protected_streamable_http_from_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app_calls: list[dict[str, Any]] = []
    run_calls: list[tuple[object, dict[str, Any]]] = []
    oauth_settings = _oauth_settings(tmp_path)

    class FakeProtectedServer:
        def streamable_http_app(self, **kwargs: Any) -> object:
            app_calls.append(kwargs)
            return "protected-app"

    monkeypatch.setenv("JST_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("JST_MCP_PORT", "8080")
    monkeypatch.setenv("JST_MCP_PATH", "/internal/mcp")
    monkeypatch.setattr(
        mcp_server.OAuthSettings,
        "load",
        classmethod(lambda cls: oauth_settings),
    )
    monkeypatch.setattr(
        mcp_server,
        "_create_protected_server",
        lambda settings: FakeProtectedServer(),
    )
    monkeypatch.setattr(
        uvicorn,
        "run",
        lambda app, **kwargs: run_calls.append((app, kwargs)),
    )

    mcp_server.http_main()

    assert app_calls == [
        {
            "host": "0.0.0.0",
            "streamable_http_path": "/internal/mcp",
        }
    ]
    assert run_calls == [
        (
            "protected-app",
            {
                "host": "0.0.0.0",
                "port": 8080,
                "access_log": False,
            },
        )
    ]


def test_mcp_calls_purchase_inbound_client(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def purchase_inbound(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return {"code": 0, "data": {"datas": []}}

    monkeypatch.setattr(mcp_server, "_client", lambda: FakeClient())

    asyncio.run(
        mcp.call_tool(
            "jst_purchase_inbound",
            {"io_ids": [2001], "date_type": 2, "page_size": 10},
        )
    )

    assert calls == [
        {
            "page_index": 1,
            "page_size": 10,
            "modified_begin": None,
            "modified_end": None,
            "po_ids": None,
            "io_ids": [2001],
            "statuss": None,
            "so_ids": None,
            "start_ts": None,
            "is_get_total": None,
            "date_type": 2,
            "seller_ids": None,
            "owner_co_id": None,
            "wms_co_id": None,
        }
    ]
