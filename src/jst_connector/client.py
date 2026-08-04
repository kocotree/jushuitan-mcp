from __future__ import annotations

import json
import secrets
import time
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import httpx

from .config import Settings
from .errors import JstApiError
from .signing import sign_params
from .token_cache import CachedToken, TokenCache


READ_ONLY_PATHS = {
    "inventory": "/open/inventory/query",
    "orders": "/open/orders/single/query",
    "purchase": "/open/purchase/query",
    "purchase_inbound": "/open/webapi/wmsapi/purchasein/purchaseinquery",
    "product_skus": "/open/sku/query",
    "product_styles": "/open/mall/item/query",
}

PURCHASE_STATUSES = {
    "Creating",
    "WaitConfirm",
    "Confirmed",
    "WaitDeliver",
    "WaitReceive",
    "Finished",
    "Cancelled",
}


def _without_none(params: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _validate_time_range(begin: str | None, end: str | None) -> None:
    if bool(begin) != bool(end):
        raise ValueError("modified_begin 和 modified_end 必须同时提供。")
    if not begin or not end:
        return
    try:
        begin_at = datetime.fromisoformat(begin)
        end_at = datetime.fromisoformat(end)
    except ValueError as exc:
        raise ValueError("时间格式必须为 YYYY-MM-DD HH:MM:SS。") from exc
    if end_at < begin_at:
        raise ValueError("modified_end 不能早于 modified_begin。")
    if end_at - begin_at > timedelta(days=7):
        raise ValueError("单次查询时间范围不能超过七天。")


def _validate_page(page_index: int, page_size: int, max_size: int) -> None:
    if page_index < 1:
        raise ValueError("page_index 必须从 1 开始。")
    if not 1 <= page_size <= max_size:
        raise ValueError(f"page_size 必须在 1 到 {max_size} 之间。")


def _validate_csv_count(value: str | None, field: str, max_count: int) -> None:
    if value and len([item for item in value.split(",") if item.strip()]) > max_count:
        raise ValueError(f"{field} 最多提供 {max_count} 个。")


def _validate_list_count(value: list[Any] | None, field: str, max_count: int) -> None:
    if value and len(value) > max_count:
        raise ValueError(f"{field} 最多提供 {max_count} 个。")


class JstClient:
    """聚水潭新版 OpenAPI 客户端；仅公开白名单中的只读接口。"""

    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self._cache = TokenCache(settings.token_cache_path)
        self._owns_http = http is None
        self._http = http or httpx.Client(timeout=settings.timeout_seconds)

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "JstClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def inventory(
        self,
        *,
        page_index: int = 1,
        page_size: int = 30,
        wms_co_id: int | None = None,
        modified_begin: str | None = None,
        modified_end: str | None = None,
        sku_ids: str | None = None,
        i_ids: str | None = None,
        names: str | None = None,
        has_lock_qty: bool | None = None,
        ts: int | None = None,
    ) -> dict[str, Any]:
        _validate_page(page_index, page_size, 100)
        _validate_time_range(modified_begin, modified_end)
        _validate_csv_count(sku_ids, "sku_ids", 100)
        _validate_csv_count(names, "names", 100)
        if not any((modified_begin, sku_ids, i_ids, names, ts is not None)):
            raise ValueError("库存查询至少提供时间范围、sku_ids、i_ids、names 或 ts 之一。")
        return self._business_request(
            "inventory",
            {
                "page_index": page_index,
                "page_size": page_size,
                "wms_co_id": wms_co_id,
                "modified_begin": modified_begin,
                "modified_end": modified_end,
                "sku_ids": sku_ids,
                "i_ids": i_ids,
                "names": names,
                "has_lock_qty": has_lock_qty,
                "ts": ts,
            },
        )

    def orders(
        self,
        *,
        page_index: int = 1,
        page_size: int = 30,
        shop_id: int | None = None,
        so_ids: list[str] | None = None,
        o_ids: list[int] | None = None,
        modified_begin: str | None = None,
        modified_end: str | None = None,
        status: str | None = None,
        start_ts: int | None = None,
        is_get_total: bool | None = None,
    ) -> dict[str, Any]:
        _validate_page(page_index, page_size, 100)
        _validate_time_range(modified_begin, modified_end)
        if not any((modified_begin, so_ids, o_ids, start_ts is not None)):
            raise ValueError("订单查询至少提供时间范围、so_ids、o_ids 或 start_ts 之一。")
        if start_ts is not None and is_get_total is None:
            is_get_total = False
        return self._business_request(
            "orders",
            {
                "page_index": page_index,
                "page_size": page_size,
                "shop_id": shop_id,
                "so_ids": so_ids,
                "o_ids": o_ids,
                "modified_begin": modified_begin,
                "modified_end": modified_end,
                "status": status,
                "start_ts": start_ts,
                "is_get_total": is_get_total,
            },
        )

    def purchase(
        self,
        *,
        page_index: int = 1,
        page_size: int = 30,
        modified_begin: str | None = None,
        modified_end: str | None = None,
        so_ids: list[str] | None = None,
        po_ids: list[str] | None = None,
        is_lock: str | None = None,
        status: str | None = None,
        statuss: list[str] | None = None,
    ) -> dict[str, Any]:
        _validate_page(page_index, page_size, 50)
        _validate_time_range(modified_begin, modified_end)
        if status is not None and status not in PURCHASE_STATUSES:
            raise ValueError("status 不是聚水潭采购单支持的状态。")
        if statuss and any(value not in PURCHASE_STATUSES for value in statuss):
            raise ValueError("statuss 包含聚水潭采购单不支持的状态。")
        if not any((modified_begin, so_ids, po_ids)):
            raise ValueError("采购单查询至少提供时间范围、so_ids 或 po_ids 之一。")
        return self._business_request(
            "purchase",
            {
                "page_index": page_index,
                "page_size": page_size,
                "modified_begin": modified_begin,
                "modified_end": modified_end,
                "so_ids": so_ids,
                "po_ids": po_ids,
                "is_lock": is_lock,
                "status": status,
                "statuss": statuss,
            },
        )

    def purchase_inbound(
        self,
        *,
        page_index: int = 1,
        page_size: int = 30,
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
    ) -> dict[str, Any]:
        _validate_page(page_index, page_size, 50)
        _validate_time_range(modified_begin, modified_end)
        _validate_list_count(po_ids, "po_ids", 30)
        _validate_list_count(io_ids, "io_ids", 30)
        if date_type not in (None, 0, 2):
            raise ValueError("date_type 只允许 0（修改时间）或 2（入库时间）。")
        if not any((modified_begin, po_ids, io_ids, so_ids, start_ts is not None)):
            raise ValueError("采购入库查询至少提供时间范围、单号或 start_ts。")
        if start_ts is not None and any(
            (
                modified_begin,
                po_ids,
                io_ids,
                statuss,
                so_ids,
                date_type is not None,
                seller_ids,
                owner_co_id is not None,
                wms_co_id is not None,
            )
        ):
            raise ValueError("start_ts 增量查询不能与其他业务筛选条件同时提供。")
        if start_ts is not None and is_get_total is True:
            raise ValueError("start_ts 增量查询时 is_get_total 必须为 false。")
        if start_ts is not None and is_get_total is None:
            is_get_total = False
        return self._business_request(
            "purchase_inbound",
            {
                "page_index": page_index,
                "page_size": page_size,
                "modified_begin": modified_begin,
                "modified_end": modified_end,
                "po_ids": po_ids,
                "io_ids": io_ids,
                "statuss": statuss,
                "so_ids": so_ids,
                "start_ts": start_ts,
                "is_get_total": is_get_total,
                "date_type": date_type,
                "seller_ids": seller_ids,
                "owner_co_id": owner_co_id,
                "wms_co_id": wms_co_id,
            },
        )

    def product_skus(
        self,
        *,
        page_index: int = 1,
        page_size: int = 30,
        modified_begin: str | None = None,
        modified_end: str | None = None,
        sku_ids: str | None = None,
        date_field: str = "modified",
        flds: str | None = None,
        exactly_name: str | None = None,
        name: str | None = None,
        brand: list[str] | None = None,
        i_ids: list[str] | None = None,
        sku_codes: str | None = None,
        labels: list[str] | None = None,
        not_labels: list[str] | None = None,
        load_sku_bin: bool | None = None,
    ) -> dict[str, Any]:
        _validate_page(page_index, page_size, 100)
        _validate_time_range(modified_begin, modified_end)
        _validate_csv_count(sku_ids, "sku_ids", 20)
        _validate_list_count(i_ids, "i_ids", 20)
        if date_field not in ("created", "modified"):
            raise ValueError("date_field 只允许 created 或 modified。")
        if not any(
            (
                modified_begin,
                sku_ids,
                exactly_name,
                name,
                brand,
                i_ids,
                sku_codes,
                labels,
                not_labels,
            )
        ):
            raise ValueError("普通商品按 SKU 查询至少提供时间、编码、名称、品牌或标签筛选。")
        return self._business_request(
            "product_skus",
            {
                "page_index": page_index,
                "page_size": page_size,
                "modified_begin": modified_begin,
                "modified_end": modified_end,
                "sku_ids": sku_ids,
                "date_field": date_field,
                "flds": flds,
                "exactly_name": exactly_name,
                "name": name,
                "brand": brand,
                "i_ids": i_ids,
                "sku_codes": sku_codes,
                "labels": labels,
                "not_labels": not_labels,
                "loadSkuBin": load_sku_bin,
            },
        )

    def product_styles(
        self,
        *,
        page_index: int = 1,
        page_size: int = 30,
        modified_begin: str | None = None,
        modified_end: str | None = None,
        i_ids: list[str] | None = None,
        only_item: bool | None = None,
        date_field: str = "modified",
        item_flds: list[str] | None = None,
        itemsku_flds: list[str] | None = None,
    ) -> dict[str, Any]:
        _validate_page(page_index, page_size, 50)
        _validate_time_range(modified_begin, modified_end)
        _validate_list_count(i_ids, "i_ids", 20)
        if date_field not in ("created", "modified"):
            raise ValueError("date_field 只允许 created 或 modified。")
        if not any((modified_begin, i_ids)):
            raise ValueError("普通商品按款查询至少提供时间范围或款式编码。")
        return self._business_request(
            "product_styles",
            {
                "page_index": page_index,
                "page_size": page_size,
                "modified_begin": modified_begin,
                "modified_end": modified_end,
                "i_ids": i_ids,
                "only_item": only_item,
                "date_field": date_field,
                "item_flds": item_flds,
                "itemsku_flds": itemsku_flds,
            },
        )

    def _business_request(self, name: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if name not in READ_ONLY_PATHS:
            raise ValueError(f"不允许的接口：{name}")
        biz = json.dumps(_without_none(params), ensure_ascii=False, separators=(",", ":"))
        form: dict[str, str] = {
            "access_token": self._get_access_token(),
            "app_key": self.settings.app_key,
            "biz": biz,
            "charset": "utf-8",
            "timestamp": str(int(time.time())),
            "version": "2",
        }
        form["sign"] = sign_params(form, self.settings.app_secret)
        return self._post(READ_ONLY_PATHS[name], form)

    def _get_access_token(self) -> str:
        cached = self._cache.load(self.settings.app_key)
        if cached and cached.access_is_valid():
            return cached.access_token
        if cached and cached.refresh_is_valid():
            token_data = self._refresh_token(cached.refresh_token)
        else:
            token_data = self._init_token()
        saved = self._save_token_data(token_data)
        return saved.access_token

    def _init_token(self) -> dict[str, Any]:
        form: dict[str, str] = {
            "app_key": self.settings.app_key,
            "timestamp": str(int(time.time())),
            "grant_type": "authorization_code",
            "charset": "utf-8",
            "code": secrets.token_hex(3),
        }
        form["sign"] = sign_params(form, self.settings.app_secret)
        response = self._post("/openWeb/auth/getInitToken", form)
        return self._extract_token_data(response)

    def _refresh_token(self, refresh_token: str) -> dict[str, Any]:
        form: dict[str, str] = {
            "app_key": self.settings.app_key,
            "timestamp": str(int(time.time())),
            "grant_type": "refresh_token",
            "charset": "utf-8",
            "refresh_token": refresh_token,
            "scope": "all",
        }
        form["sign"] = sign_params(form, self.settings.app_secret)
        response = self._post("/openWeb/auth/refreshToken", form)
        return self._extract_token_data(response)

    def _save_token_data(self, data: Mapping[str, Any]) -> CachedToken:
        try:
            expires_in = int(data["expires_in"])
            access_token = str(data["access_token"])
            refresh_token = str(data["refresh_token"])
        except (KeyError, TypeError, ValueError) as exc:
            raise JstApiError("Token 响应缺少 access_token、refresh_token 或 expires_in。") from exc

        now = time.time()
        access_margin = min(24 * 3600, max(60, expires_in * 0.1))
        refresh_margin = min(12 * 3600, max(60, expires_in * 0.05))
        token = CachedToken(
            app_key=self.settings.app_key,
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=now + max(1, expires_in - access_margin),
            refresh_expires_at=now + max(1, expires_in - refresh_margin),
        )
        self._cache.save(token)
        return token

    @staticmethod
    def _extract_token_data(response: Mapping[str, Any]) -> dict[str, Any]:
        data = response.get("data")
        if not isinstance(data, dict):
            raise JstApiError("Token 响应中没有有效的 data 对象。")
        return data

    def _post(self, path: str, form: Mapping[str, str]) -> dict[str, Any]:
        try:
            response = self._http.post(f"{self.settings.endpoint}{path}", data=form)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise JstApiError(f"请求聚水潭失败：{exc.__class__.__name__}") from exc
        except ValueError as exc:
            raise JstApiError("聚水潭返回了非 JSON 响应。") from exc

        if not isinstance(payload, dict):
            raise JstApiError("聚水潭返回的 JSON 不是对象。")
        code = payload.get("code")
        if code not in (None, 0, "0") or payload.get("issuccess") is False:
            message = payload.get("msg") or payload.get("message") or "未知错误"
            raise JstApiError(f"聚水潭接口错误 code={code}: {message}")
        return payload
