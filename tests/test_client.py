from __future__ import annotations

import json
from collections.abc import Iterator
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


BusinessRequest = tuple[str, dict[str, object]]


@pytest.fixture
def recording_client(tmp_path: Path) -> Iterator[tuple[JstClient, list[BusinessRequest]]]:
    business_requests: list[BusinessRequest] = []

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

    http = httpx.Client(transport=httpx.MockTransport(handler))
    yield JstClient(_settings(tmp_path), http=http), business_requests
    http.close()


@pytest.fixture
def validation_client(tmp_path: Path) -> Iterator[JstClient]:
    def unexpected_request(_: httpx.Request) -> httpx.Response:
        raise AssertionError("validation should fail before making an HTTP request")

    http = httpx.Client(transport=httpx.MockTransport(unexpected_request))
    yield JstClient(_settings(tmp_path), http=http)
    http.close()


def test_inventory_initializes_token_signs_request_and_reuses_cache(tmp_path: Path) -> None:
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
        assert request.url.path == "/open/inventory/query"
        assert form["access_token"] == "access-value"
        assert json.loads(form["biz"]) == {
            "page_index": 1,
            "page_size": 30,
            "sku_ids": "SKU001",
        }
        return httpx.Response(200, json={"code": 0, "data": {"datas": []}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = JstClient(_settings(tmp_path), http=http)
    assert client.inventory(sku_ids="SKU001")["code"] == 0
    assert client.inventory(sku_ids="SKU001")["code"] == 0
    assert [request.url.path for request in requests] == [
        "/openWeb/auth/getInitToken",
        "/open/inventory/query",
        "/open/inventory/query",
    ]


def test_client_does_not_expose_shops_query() -> None:
    assert not hasattr(JstClient, "shops")


def test_inventory_requires_a_filter(validation_client: JstClient) -> None:
    try:
        validation_client.inventory()
    except ValueError as exc:
        assert "至少提供" in str(exc)
    else:
        raise AssertionError("inventory() should reject an unbounded query")


def test_purchase_inbound_queries_official_read_only_endpoint(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
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


def test_product_skus_queries_official_read_only_endpoint(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
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


def test_purchase_inbound_start_ts_uses_incremental_mode(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
    client.purchase_inbound(start_ts=123456)

    assert [biz for _, biz in business_requests] == [
        {
            "page_index": 1,
            "page_size": 30,
            "start_ts": 123456,
            "is_get_total": False,
        }
    ]


def test_purchase_inbound_rejects_start_ts_with_other_filters(
    validation_client: JstClient,
) -> None:
    try:
        validation_client.purchase_inbound(
            start_ts=123456,
            modified_begin="2026-08-04 00:00:00",
            modified_end="2026-08-04 01:00:00",
        )
    except ValueError as exc:
        assert "start_ts" in str(exc)
    else:
        raise AssertionError("start_ts incremental mode must reject other filters")


def test_purchase_inbound_rejects_total_count_in_incremental_mode(
    validation_client: JstClient,
) -> None:
    with pytest.raises(ValueError, match="is_get_total"):
        validation_client.purchase_inbound(start_ts=123456, is_get_total=True)


@pytest.mark.parametrize(
    "filters",
    [
        {"status": "Unknown"},
        {"statuss": ["Confirmed", "Unknown"]},
    ],
)
def test_purchase_rejects_unsupported_statuses(
    validation_client: JstClient,
    filters: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="status"):
        validation_client.purchase(po_ids=["PO001"], **filters)


@pytest.mark.parametrize(
    "method_name",
    ["inventory", "purchase", "purchase_inbound", "product_skus", "product_styles"],
)
def test_core_queries_reject_time_ranges_over_seven_days(
    validation_client: JstClient,
    method_name: str,
) -> None:
    method = getattr(validation_client, method_name)
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
    validation_client: JstClient,
    method_name: str,
    max_size: int,
    filters: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="page_size"):
        getattr(validation_client, method_name)(page_size=max_size + 1, **filters)


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
    validation_client: JstClient,
    method_name: str,
    filters: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="最多"):
        getattr(validation_client, method_name)(**filters)


@pytest.mark.parametrize(
    ("method_name", "filters", "message"),
    [
        ("product_skus", {"sku_ids": "SKU001", "date_field": "bad"}, "date_field"),
        ("product_styles", {"i_ids": ["STYLE001"], "date_field": "bad"}, "date_field"),
        ("purchase_inbound", {"io_ids": [2001], "date_type": 1}, "date_type"),
    ],
)
def test_core_queries_reject_unsupported_date_modes(
    validation_client: JstClient,
    method_name: str,
    filters: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        getattr(validation_client, method_name)(**filters)


def test_product_styles_queries_official_read_only_endpoint(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
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


def test_purchase_passes_official_status_filters(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
    client.purchase(
        po_ids=["PO001"],
        is_lock="1",
        status="Confirmed",
        statuss=["Confirmed", "WaitDeliver"],
    )

    assert [biz for _, biz in business_requests] == [
        {
            "page_index": 1,
            "page_size": 30,
            "po_ids": ["PO001"],
            "is_lock": "1",
            "status": "Confirmed",
            "statuss": ["Confirmed", "WaitDeliver"],
        }
    ]


def test_product_skus_passes_official_product_filters(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
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

    assert [biz for _, biz in business_requests] == [
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


def test_product_styles_passes_requested_response_fields(
    recording_client: tuple[JstClient, list[BusinessRequest]],
) -> None:
    client, business_requests = recording_client
    client.product_styles(
        i_ids=["STYLE001"],
        item_flds=["brand", "category"],
        itemsku_flds=["purchase_price", "pics"],
    )

    assert [biz for _, biz in business_requests] == [
        {
            "page_index": 1,
            "page_size": 30,
            "i_ids": ["STYLE001"],
            "date_field": "modified",
            "item_flds": ["brand", "category"],
            "itemsku_flds": ["purchase_price", "pics"],
        }
    ]
