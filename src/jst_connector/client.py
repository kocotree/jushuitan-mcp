from __future__ import annotations

import json
import secrets
import time
from collections.abc import Mapping
from typing import Any

import httpx

from .config import Settings
from .errors import JstApiError
from .signing import sign_params
from .token_cache import CachedToken, TokenCache


READ_ONLY_PATHS = {
    "shops": "/open/shops/query",
    "inventory": "/open/inventory/query",
    "orders": "/open/orders/single/query",
    "purchase": "/open/purchase/query",
}


def _without_none(params: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


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

    def shops(
        self,
        *,
        page_index: int = 1,
        page_size: int = 100,
        shop_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        return self._business_request(
            "shops",
            {"page_index": page_index, "page_size": page_size, "shop_ids": shop_ids},
        )

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
        if bool(modified_begin) != bool(modified_end):
            raise ValueError("modified_begin 和 modified_end 必须同时提供。")
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
        if bool(modified_begin) != bool(modified_end):
            raise ValueError("modified_begin 和 modified_end 必须同时提供。")
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
    ) -> dict[str, Any]:
        if bool(modified_begin) != bool(modified_end):
            raise ValueError("modified_begin 和 modified_end 必须同时提供。")
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
