from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from jst_connector.client import JstClient
from jst_connector.config import Settings
from jst_connector.signing import sign_params


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app_key="test-app",
        app_secret="test-secret",
        endpoint="https://example.test",
        token_cache_path=tmp_path / "token.json",
    )


def test_shops_initializes_token_signs_request_and_reuses_cache(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        unsigned = {key: value for key, value in form.items() if key != "sign"}
        assert form["sign"] == sign_params(unsigned, "test-secret")
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "ok",
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                        "scope": "all",
                    },
                },
            )
        assert request.url.path == "/open/shops/query"
        assert form["access_token"] == "access-value"
        assert json.loads(form["biz"]) == {"page_index": 1, "page_size": 100}
        return httpx.Response(200, json={"code": 0, "shops": [{"shop_id": 1}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = JstClient(_settings(tmp_path), http=http)
    assert client.shops()["shops"][0]["shop_id"] == 1
    assert client.shops()["shops"][0]["shop_id"] == 1
    assert [request.url.path for request in requests] == [
        "/openWeb/auth/getInitToken",
        "/open/shops/query",
        "/open/shops/query",
    ]


def test_inventory_requires_a_filter(tmp_path: Path) -> None:
    client = JstClient(_settings(tmp_path), http=httpx.Client(transport=httpx.MockTransport(lambda _: None)))
    try:
        client.inventory()
    except ValueError as exc:
        assert "至少提供" in str(exc)
    else:
        raise AssertionError("inventory() should reject an unbounded query")
