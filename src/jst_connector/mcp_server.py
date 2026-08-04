from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from .client import JstClient
from .config import Settings


mcp = MCPServer(
    "Jushuitan Read Only",
    instructions="只读查询聚水潭的店铺、库存、订单和采购单；不提供任何写操作。",
)


def _client() -> JstClient:
    return JstClient(Settings.load())


@mcp.tool()
def jst_shops(page: int = 1, page_size: int = 100, shop_ids: list[int] | None = None) -> dict[str, Any]:
    """只读查询聚水潭店铺列表。"""
    with _client() as client:
        return client.shops(page_index=page, page_size=page_size, shop_ids=shop_ids)


@mcp.tool()
def jst_inventory(
    modified_begin: str | None = None,
    modified_end: str | None = None,
    sku_ids: str | None = None,
    i_ids: str | None = None,
    names: str | None = None,
    ts: int | None = None,
    wms_co_id: int | None = None,
    has_lock_qty: bool | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """只读查询库存。时间范围须成对提供且最长七天；也可按 SKU、款式、名称或 ts 查询。"""
    with _client() as client:
        return client.inventory(
            page_index=page,
            page_size=page_size,
            wms_co_id=wms_co_id,
            modified_begin=modified_begin,
            modified_end=modified_end,
            sku_ids=sku_ids,
            i_ids=i_ids,
            names=names,
            has_lock_qty=has_lock_qty,
            ts=ts,
        )


@mcp.tool()
def jst_orders(
    modified_begin: str | None = None,
    modified_end: str | None = None,
    so_ids: list[str] | None = None,
    o_ids: list[int] | None = None,
    start_ts: int | None = None,
    shop_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """只读查询订单。至少按时间范围、线上单号、内部单号或 start_ts 之一过滤。"""
    with _client() as client:
        return client.orders(
            page_index=page,
            page_size=page_size,
            shop_id=shop_id,
            so_ids=so_ids,
            o_ids=o_ids,
            modified_begin=modified_begin,
            modified_end=modified_end,
            status=status,
            start_ts=start_ts,
        )


@mcp.tool()
def jst_purchase(
    modified_begin: str | None = None,
    modified_end: str | None = None,
    so_ids: list[str] | None = None,
    po_ids: list[str] | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """只读查询采购单。至少按时间范围、外部单号或采购单号之一过滤。"""
    with _client() as client:
        return client.purchase(
            page_index=page,
            page_size=page_size,
            modified_begin=modified_begin,
            modified_end=modified_end,
            so_ids=so_ids,
            po_ids=po_ids,
        )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
