import asyncio
import json
from typing import Any

from starlette.testclient import TestClient

from jst_connector import mcp_server


mcp = mcp_server.mcp


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


def test_http_main_runs_streamable_http_from_environment(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setenv("JST_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("JST_MCP_PORT", "8080")
    monkeypatch.setenv("JST_MCP_PATH", "/internal/mcp")
    monkeypatch.setattr(
        mcp_server.mcp,
        "run",
        lambda transport, **kwargs: calls.append((transport, kwargs)),
    )

    mcp_server.http_main()

    assert calls == [
        (
            "streamable-http",
            {
                "host": "0.0.0.0",
                "port": 8080,
                "streamable_http_path": "/internal/mcp",
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
