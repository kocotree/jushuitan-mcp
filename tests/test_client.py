from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

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


def test_purchase_inbound_queries_official_read_only_endpoint(tmp_path: Path) -> None:
    business_requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_requests.append((request.url.path, json.loads(form["biz"])))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.purchase_inbound(
        modified_begin="2026-08-04 00:00:00",
        modified_end="2026-08-04 23:59:59",
        po_ids=[1001],
        io_ids=[2001],
        statuss=["Confirmed"],
        so_ids=["EXT001"],
        date_type=2,
        seller_ids=[3001],
        owner_co_id=4001,
        wms_co_id=5001,
        page_size=10,
    )

    assert business_requests == [
        (
            "/open/webapi/wmsapi/purchasein/purchaseinquery",
            {
                "page_index": 1,
                "page_size": 10,
                "modified_begin": "2026-08-04 00:00:00",
                "modified_end": "2026-08-04 23:59:59",
                "po_ids": [1001],
                "io_ids": [2001],
                "statuss": ["Confirmed"],
                "so_ids": ["EXT001"],
                "date_type": 2,
                "seller_ids": [3001],
                "owner_co_id": 4001,
                "wms_co_id": 5001,
            },
        )
    ]


def test_product_skus_queries_official_read_only_endpoint(tmp_path: Path) -> None:
    business_requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_requests.append((request.url.path, json.loads(form["biz"])))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.product_skus(
        sku_ids="SKU001,SKU002",
        date_field="modified",
        flds="purchase_price,pics",
        page_size=20,
    )

    assert business_requests == [
        (
            "/open/sku/query",
            {
                "page_index": 1,
                "page_size": 20,
                "sku_ids": "SKU001,SKU002",
                "date_field": "modified",
                "flds": "purchase_price,pics",
            },
        )
    ]


def test_purchase_inbound_start_ts_uses_incremental_mode(tmp_path: Path) -> None:
    business_biz: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_biz.append(json.loads(form["biz"]))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.purchase_inbound(start_ts=123456)

    assert business_biz == [
        {
            "page_index": 1,
            "page_size": 30,
            "start_ts": 123456,
            "is_get_total": False,
        }
    ]


def test_purchase_inbound_rejects_start_ts_with_other_filters(tmp_path: Path) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    try:
        client.purchase_inbound(
            start_ts=123456,
            modified_begin="2026-08-04 00:00:00",
            modified_end="2026-08-04 01:00:00",
        )
    except ValueError as exc:
        assert "start_ts" in str(exc)
    else:
        raise AssertionError("start_ts incremental mode must reject other filters")


def test_purchase_inbound_rejects_total_count_in_incremental_mode(tmp_path: Path) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    with pytest.raises(ValueError, match="is_get_total"):
        client.purchase_inbound(start_ts=123456, is_get_total=True)


@pytest.mark.parametrize(
    "filters",
    [
        {"status": "Unknown"},
        {"statuss": ["Confirmed", "Unknown"]},
    ],
)
def test_purchase_rejects_unsupported_statuses(
    tmp_path: Path,
    filters: dict[str, object],
) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    with pytest.raises(ValueError, match="status"):
        client.purchase(po_ids=["PO001"], **filters)


@pytest.mark.parametrize(
    "method_name",
    ["inventory", "purchase", "purchase_inbound", "product_skus", "product_styles"],
)
def test_core_queries_reject_time_ranges_over_seven_days(
    tmp_path: Path,
    method_name: str,
) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    method = getattr(client, method_name)
    with pytest.raises(ValueError, match="七天"):
        method(
            modified_begin="2026-08-01 00:00:00",
            modified_end="2026-08-08 00:00:01",
        )


@pytest.mark.parametrize(
    ("method_name", "max_size", "filters"),
    [
        ("inventory", 100, {"sku_ids": "SKU001"}),
        ("purchase", 50, {"po_ids": ["1001"]}),
        ("purchase_inbound", 50, {"io_ids": [2001]}),
        ("product_skus", 100, {"sku_ids": "SKU001"}),
        ("product_styles", 50, {"i_ids": ["STYLE001"]}),
    ],
)
def test_core_queries_enforce_official_page_size_limits(
    tmp_path: Path,
    method_name: str,
    max_size: int,
    filters: dict[str, object],
) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    with pytest.raises(ValueError, match="page_size"):
        getattr(client, method_name)(page_size=max_size + 1, **filters)


@pytest.mark.parametrize(
    ("method_name", "filters"),
    [
        ("inventory", {"sku_ids": ",".join(f"SKU{i}" for i in range(101))}),
        ("purchase_inbound", {"po_ids": list(range(31))}),
        ("purchase_inbound", {"io_ids": list(range(31))}),
        ("product_skus", {"sku_ids": ",".join(f"SKU{i}" for i in range(21))}),
        ("product_styles", {"i_ids": [f"STYLE{i}" for i in range(21)]}),
    ],
)
def test_core_queries_enforce_official_identifier_limits(
    tmp_path: Path,
    method_name: str,
    filters: dict[str, object],
) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    with pytest.raises(ValueError, match="最多"):
        getattr(client, method_name)(**filters)


@pytest.mark.parametrize(
    ("method_name", "filters", "message"),
    [
        ("product_skus", {"sku_ids": "SKU001", "date_field": "bad"}, "date_field"),
        ("product_styles", {"i_ids": ["STYLE001"], "date_field": "bad"}, "date_field"),
        ("purchase_inbound", {"io_ids": [2001], "date_type": 1}, "date_type"),
    ],
)
def test_core_queries_reject_unsupported_date_modes(
    tmp_path: Path,
    method_name: str,
    filters: dict[str, object],
    message: str,
) -> None:
    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(lambda _: None)),
    )

    with pytest.raises(ValueError, match=message):
        getattr(client, method_name)(**filters)


def test_product_styles_queries_official_read_only_endpoint(tmp_path: Path) -> None:
    business_requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_requests.append((request.url.path, json.loads(form["biz"])))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.product_styles(
        i_ids=["STYLE001", "STYLE002"],
        only_item=False,
        date_field="modified",
        page_size=10,
    )

    assert business_requests == [
        (
            "/open/mall/item/query",
            {
                "page_index": 1,
                "page_size": 10,
                "i_ids": ["STYLE001", "STYLE002"],
                "only_item": False,
                "date_field": "modified",
            },
        )
    ]


def test_purchase_passes_official_status_filters(tmp_path: Path) -> None:
    business_biz: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_biz.append(json.loads(form["biz"]))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.purchase(
        po_ids=["PO001"],
        is_lock="1",
        status="Confirmed",
        statuss=["Confirmed", "WaitDeliver"],
    )

    assert business_biz == [
        {
            "page_index": 1,
            "page_size": 30,
            "po_ids": ["PO001"],
            "is_lock": "1",
            "status": "Confirmed",
            "statuss": ["Confirmed", "WaitDeliver"],
        }
    ]


def test_product_skus_passes_official_product_filters(tmp_path: Path) -> None:
    business_biz: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_biz.append(json.loads(form["biz"]))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.product_skus(
        exactly_name="椰椰小岛两栖泳衣三件套",
        name="泳衣",
        brand=["品牌A"],
        i_ids=["STYLE001"],
        sku_codes="BARCODE001,BARCODE002",
        labels=["夏季"],
        not_labels=["停用"],
        load_sku_bin=True,
    )

    assert business_biz == [
        {
            "page_index": 1,
            "page_size": 30,
            "date_field": "modified",
            "exactly_name": "椰椰小岛两栖泳衣三件套",
            "name": "泳衣",
            "brand": ["品牌A"],
            "i_ids": ["STYLE001"],
            "sku_codes": "BARCODE001,BARCODE002",
            "labels": ["夏季"],
            "not_labels": ["停用"],
            "loadSkuBin": True,
        }
    ]


def test_product_styles_passes_requested_response_fields(tmp_path: Path) -> None:
    business_biz: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path == "/openWeb/auth/getInitToken":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-value",
                        "refresh_token": "refresh-value",
                        "expires_in": 864000,
                    },
                },
            )
        business_biz.append(json.loads(form["biz"]))
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    client = JstClient(
        _settings(tmp_path),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.product_styles(
        i_ids=["STYLE001"],
        item_flds=["brand", "category"],
        itemsku_flds=["purchase_price", "pics"],
    )

    assert business_biz == [
        {
            "page_index": 1,
            "page_size": 30,
            "i_ids": ["STYLE001"],
            "date_field": "modified",
            "item_flds": ["brand", "category"],
            "itemsku_flds": ["purchase_price", "pics"],
        }
    ]
