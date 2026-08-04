import asyncio
from typing import Any

from jst_connector import mcp_server


mcp = mcp_server.mcp


def test_mcp_exposes_only_read_only_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "jst_shops",
        "jst_inventory",
        "jst_orders",
        "jst_purchase",
        "jst_purchase_inbound",
        "jst_product_skus",
        "jst_product_styles",
    }


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
