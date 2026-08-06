from __future__ import annotations

from typing import Any

import httpx
import uvicorn
from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.applications import Starlette

from .client import JstClient
from .config import HttpSettings, Settings
from .oauth import FeishuOAuthProvider, OAuthSettings


mcp = MCPServer(
    "Jushuitan Read Only",
    instructions="只读查询聚水潭的库存、订单、采购单、采购入库和普通商品资料；不提供任何写操作。",
)


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(_: Request) -> Response:
    return JSONResponse({"status": "ok", "service": "jushuitan-mcp"})


def create_http_app(
    *,
    streamable_http_path: str = "/mcp",
    host: str = "127.0.0.1",
    oauth_settings: OAuthSettings | None = None,
    oauth_http_transport: httpx.AsyncBaseTransport | None = None,
) -> Starlette:
    server = (
        _create_protected_server(oauth_settings, oauth_http_transport)
        if oauth_settings
        else mcp
    )
    return server.streamable_http_app(
        streamable_http_path=streamable_http_path,
        host=host,
    )


def _client() -> JstClient:
    return JstClient(Settings.load())


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
    is_lock: str | None = None,
    status: str | None = None,
    statuss: list[str] | None = None,
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
            is_lock=is_lock,
            status=status,
            statuss=statuss,
        )


@mcp.tool()
def jst_purchase_inbound(
    modified_begin: str | None = None,
    modified_end: str | None = None,
    po_ids: list[int] | None = None,
    io_ids: list[int] | None = None,
    statuss: list[str] | None = None,
    so_ids: list[str] | None = None,
    start_ts: int | None = None,
    is_get_total: bool | None = None,
    date_type: int | None = None,
    seller_ids: list[int] | None = None,
    owner_co_id: int | None = None,
    wms_co_id: int | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """只读查询采购入库单及商品明细。date_type=0 按修改时间，2 按入库时间。"""
    with _client() as client:
        return client.purchase_inbound(
            page_index=page,
            page_size=page_size,
            modified_begin=modified_begin,
            modified_end=modified_end,
            po_ids=po_ids,
            io_ids=io_ids,
            statuss=statuss,
            so_ids=so_ids,
            start_ts=start_ts,
            is_get_total=is_get_total,
            date_type=date_type,
            seller_ids=seller_ids,
            owner_co_id=owner_co_id,
            wms_co_id=wms_co_id,
        )


@mcp.tool()
def jst_product_skus(
    modified_begin: str | None = None,
    modified_end: str | None = None,
    sku_ids: str | None = None,
    exactly_name: str | None = None,
    name: str | None = None,
    brand: list[str] | None = None,
    i_ids: list[str] | None = None,
    date_field: str = "modified",
    flds: str | None = None,
    sku_codes: str | None = None,
    labels: list[str] | None = None,
    not_labels: list[str] | None = None,
    load_sku_bin: bool | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """只读按 SKU 查询普通商品资料，可按编码、名称、品牌、款式或标签筛选。"""
    with _client() as client:
        return client.product_skus(
            page_index=page,
            page_size=page_size,
            modified_begin=modified_begin,
            modified_end=modified_end,
            sku_ids=sku_ids,
            date_field=date_field,
            flds=flds,
            exactly_name=exactly_name,
            name=name,
            brand=brand,
            i_ids=i_ids,
            sku_codes=sku_codes,
            labels=labels,
            not_labels=not_labels,
            load_sku_bin=load_sku_bin,
        )


@mcp.tool()
def jst_product_styles(
    modified_begin: str | None = None,
    modified_end: str | None = None,
    i_ids: list[str] | None = None,
    only_item: bool | None = None,
    date_field: str = "modified",
    item_flds: list[str] | None = None,
    itemsku_flds: list[str] | None = None,
    page: int = 1,
    page_size: int = 30,
) -> dict[str, Any]:
    """只读按款式查询普通商品资料，可返回款式及其 SKU 明细。"""
    with _client() as client:
        return client.product_styles(
            page_index=page,
            page_size=page_size,
            modified_begin=modified_begin,
            modified_end=modified_end,
            i_ids=i_ids,
            only_item=only_item,
            date_field=date_field,
            item_flds=item_flds,
            itemsku_flds=itemsku_flds,
        )


def _create_protected_server(
    oauth_settings: OAuthSettings,
    oauth_http_transport: httpx.AsyncBaseTransport | None = None,
) -> MCPServer:
    provider = FeishuOAuthProvider(
        oauth_settings,
        http_transport=oauth_http_transport,
    )
    server = MCPServer(
        "Jushuitan Read Only",
        instructions=mcp.instructions,
        auth_server_provider=provider,
        auth=oauth_settings.to_mcp_auth_settings(),
    )
    server.custom_route("/health", methods=["GET"], include_in_schema=False)(health_check)
    server.custom_route(
        "/oauth/feishu/callback",
        methods=["GET"],
        include_in_schema=False,
    )(provider.handle_feishu_callback)
    for tool_function in (
        jst_inventory,
        jst_orders,
        jst_purchase,
        jst_purchase_inbound,
        jst_product_skus,
        jst_product_styles,
    ):
        server.tool()(tool_function)
    return server


def main() -> None:
    mcp.run(transport="stdio")


def http_main() -> None:
    settings = HttpSettings.load()
    oauth_settings = OAuthSettings.load()
    protected_server = _create_protected_server(oauth_settings)
    app = protected_server.streamable_http_app(
        host=settings.host,
        streamable_http_path=settings.path,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
