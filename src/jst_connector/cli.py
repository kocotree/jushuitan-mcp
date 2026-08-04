from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from .client import JstClient
from .config import Settings
from .errors import JstError


def _add_page_args(parser: argparse.ArgumentParser, default_size: int, max_size: int) -> None:
    parser.add_argument("--page", type=int, default=1, help="页码，从 1 开始")
    parser.add_argument("--page-size", type=int, default=default_size, choices=range(1, max_size + 1))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jst", description="聚水潭新版 OpenAPI 只读 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="查询库存")
    _add_page_args(inventory, 30, 100)
    inventory.add_argument("--wms-co-id", type=int)
    inventory.add_argument("--modified-begin", help="YYYY-MM-DD HH:MM:SS")
    inventory.add_argument("--modified-end", help="YYYY-MM-DD HH:MM:SS")
    inventory.add_argument("--sku", action="append", dest="skus", help="可重复传入")
    inventory.add_argument("--i-id", action="append", dest="i_ids", help="可重复传入")
    inventory.add_argument("--name", action="append", dest="names", help="可重复传入")
    inventory.add_argument("--ts", type=int, help="防漏单增量时间戳")
    inventory.add_argument("--has-lock-qty", action="store_true", default=None)

    orders = subparsers.add_parser("orders", help="查询订单")
    _add_page_args(orders, 30, 100)
    orders.add_argument("--shop-id", type=int)
    orders.add_argument("--so-id", action="append", dest="so_ids", help="线上单号，可重复传入")
    orders.add_argument("--o-id", type=int, action="append", dest="o_ids", help="内部单号，可重复传入")
    orders.add_argument("--modified-begin", help="YYYY-MM-DD HH:MM:SS")
    orders.add_argument("--modified-end", help="YYYY-MM-DD HH:MM:SS")
    orders.add_argument("--status")
    orders.add_argument("--start-ts", type=int, help="防漏单增量时间戳")

    purchase = subparsers.add_parser("purchase", help="查询采购单")
    _add_page_args(purchase, 30, 50)
    purchase.add_argument("--modified-begin", help="YYYY-MM-DD HH:MM:SS")
    purchase.add_argument("--modified-end", help="YYYY-MM-DD HH:MM:SS")
    purchase.add_argument("--so-id", action="append", dest="so_ids", help="外部单号，可重复传入")
    purchase.add_argument("--po-id", action="append", dest="po_ids", help="采购单号，可重复传入")
    purchase.add_argument("--is-lock")
    purchase.add_argument("--status")
    purchase.add_argument("--statuses", action="append", dest="statuss", help="状态，可重复传入")

    purchase_inbound = subparsers.add_parser("purchase-inbound", help="查询采购入库单明细")
    _add_page_args(purchase_inbound, 30, 50)
    purchase_inbound.add_argument("--modified-begin", help="YYYY-MM-DD HH:MM:SS")
    purchase_inbound.add_argument("--modified-end", help="YYYY-MM-DD HH:MM:SS")
    purchase_inbound.add_argument("--po-id", type=int, action="append", dest="po_ids")
    purchase_inbound.add_argument("--io-id", type=int, action="append", dest="io_ids")
    purchase_inbound.add_argument("--status", action="append", dest="statuss")
    purchase_inbound.add_argument("--so-id", action="append", dest="so_ids")
    purchase_inbound.add_argument("--start-ts", type=int, help="增量查询时间戳")
    purchase_inbound.add_argument("--is-get-total", action="store_true", default=None)
    purchase_inbound.add_argument("--date-type", type=int, choices=(0, 2))
    purchase_inbound.add_argument("--seller-id", type=int, action="append", dest="seller_ids")
    purchase_inbound.add_argument("--owner-co-id", type=int)
    purchase_inbound.add_argument("--wms-co-id", type=int)

    product_skus = subparsers.add_parser("product-skus", help="按 SKU 查询普通商品资料")
    _add_page_args(product_skus, 30, 100)
    product_skus.add_argument("--modified-begin", help="YYYY-MM-DD HH:MM:SS")
    product_skus.add_argument("--modified-end", help="YYYY-MM-DD HH:MM:SS")
    product_skus.add_argument("--sku", action="append", dest="skus")
    product_skus.add_argument("--exact-name", dest="exactly_name")
    product_skus.add_argument("--name")
    product_skus.add_argument("--brand", action="append", dest="brands")
    product_skus.add_argument("--i-id", action="append", dest="i_ids")
    product_skus.add_argument("--date-field", choices=("created", "modified"), default="modified")
    product_skus.add_argument("--field", action="append", dest="fields")
    product_skus.add_argument("--sku-code", action="append", dest="sku_codes")
    product_skus.add_argument("--label", action="append", dest="labels")
    product_skus.add_argument("--not-label", action="append", dest="not_labels")
    product_skus.add_argument("--load-sku-bin", action="store_true", default=None)

    product_styles = subparsers.add_parser("product-styles", help="按款式查询普通商品资料")
    _add_page_args(product_styles, 30, 50)
    product_styles.add_argument("--modified-begin", help="YYYY-MM-DD HH:MM:SS")
    product_styles.add_argument("--modified-end", help="YYYY-MM-DD HH:MM:SS")
    product_styles.add_argument("--i-id", action="append", dest="i_ids")
    product_styles.add_argument("--only-item", action="store_true", default=None)
    product_styles.add_argument("--date-field", choices=("created", "modified"), default="modified")
    product_styles.add_argument("--item-field", action="append", dest="item_fields")
    product_styles.add_argument("--sku-field", action="append", dest="sku_fields")
    return parser


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    with JstClient(Settings.load()) as client:
        if args.command == "inventory":
            return client.inventory(
                page_index=args.page,
                page_size=args.page_size,
                wms_co_id=args.wms_co_id,
                modified_begin=args.modified_begin,
                modified_end=args.modified_end,
                sku_ids=",".join(args.skus) if args.skus else None,
                i_ids=",".join(args.i_ids) if args.i_ids else None,
                names=",".join(args.names) if args.names else None,
                has_lock_qty=args.has_lock_qty,
                ts=args.ts,
            )
        if args.command == "orders":
            return client.orders(
                page_index=args.page,
                page_size=args.page_size,
                shop_id=args.shop_id,
                so_ids=args.so_ids,
                o_ids=args.o_ids,
                modified_begin=args.modified_begin,
                modified_end=args.modified_end,
                status=args.status,
                start_ts=args.start_ts,
            )
        if args.command == "purchase":
            return client.purchase(
                page_index=args.page,
                page_size=args.page_size,
                modified_begin=args.modified_begin,
                modified_end=args.modified_end,
                so_ids=args.so_ids,
                po_ids=args.po_ids,
                is_lock=args.is_lock,
                status=args.status,
                statuss=args.statuss,
            )
        if args.command == "purchase-inbound":
            return client.purchase_inbound(
                page_index=args.page,
                page_size=args.page_size,
                modified_begin=args.modified_begin,
                modified_end=args.modified_end,
                po_ids=args.po_ids,
                io_ids=args.io_ids,
                statuss=args.statuss,
                so_ids=args.so_ids,
                start_ts=args.start_ts,
                is_get_total=args.is_get_total,
                date_type=args.date_type,
                seller_ids=args.seller_ids,
                owner_co_id=args.owner_co_id,
                wms_co_id=args.wms_co_id,
            )
        if args.command == "product-skus":
            return client.product_skus(
                page_index=args.page,
                page_size=args.page_size,
                modified_begin=args.modified_begin,
                modified_end=args.modified_end,
                sku_ids=",".join(args.skus) if args.skus else None,
                date_field=args.date_field,
                flds=",".join(args.fields) if args.fields else None,
                exactly_name=args.exactly_name,
                name=args.name,
                brand=args.brands,
                i_ids=args.i_ids,
                sku_codes=",".join(args.sku_codes) if args.sku_codes else None,
                labels=args.labels,
                not_labels=args.not_labels,
                load_sku_bin=args.load_sku_bin,
            )
        return client.product_styles(
            page_index=args.page,
            page_size=args.page_size,
            modified_begin=args.modified_begin,
            modified_end=args.modified_end,
            i_ids=args.i_ids,
            only_item=args.only_item,
            date_field=args.date_field,
            item_flds=args.item_fields,
            itemsku_flds=args.sku_fields,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = _execute(args)
    except (JstError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
