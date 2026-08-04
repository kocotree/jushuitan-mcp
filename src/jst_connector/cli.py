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

    shops = subparsers.add_parser("shops", help="查询店铺")
    _add_page_args(shops, 100, 100)
    shops.add_argument("--shop-id", type=int, action="append", dest="shop_ids")

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
    return parser


def _execute(args: argparse.Namespace) -> dict[str, Any]:
    with JstClient(Settings.load()) as client:
        if args.command == "shops":
            return client.shops(page_index=args.page, page_size=args.page_size, shop_ids=args.shop_ids)
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
        return client.purchase(
            page_index=args.page,
            page_size=args.page_size,
            modified_begin=args.modified_begin,
            modified_end=args.modified_end,
            so_ids=args.so_ids,
            po_ids=args.po_ids,
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
