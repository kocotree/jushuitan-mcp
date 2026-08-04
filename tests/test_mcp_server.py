import asyncio

from jst_connector.mcp_server import mcp


def test_mcp_exposes_only_read_only_tools() -> None:
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "jst_shops",
        "jst_inventory",
        "jst_orders",
        "jst_purchase",
    }
