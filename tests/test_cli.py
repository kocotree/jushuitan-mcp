from __future__ import annotations

from typing import Any

import pytest

from jst_connector import cli


class RecordingClient:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]], error: Exception | None = None):
        self.calls = calls
        self.error = error

    def __enter__(self) -> "RecordingClient":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def __getattr__(self, name: str):
        def call(**kwargs: Any) -> dict[str, Any]:
            if self.error:
                raise self.error
            self.calls.append((name, kwargs))
            return {"code": 0}

        return call


def test_cli_does_not_expose_shops_command() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["shops"])


@pytest.mark.parametrize(
    ("argv", "expected_name", "expected_values"),
    [
        (
            [
                "purchase-inbound",
                "--io-id",
                "2001",
                "--status",
                "Confirmed",
                "--date-type",
                "2",
                "--seller-id",
                "3001",
                "--owner-co-id",
                "4001",
                "--wms-co-id",
                "5001",
            ],
            "purchase_inbound",
            {
                "io_ids": [2001],
                "statuss": ["Confirmed"],
                "date_type": 2,
                "seller_ids": [3001],
                "owner_co_id": 4001,
                "wms_co_id": 5001,
            },
        ),
        (
            [
                "product-skus",
                "--exact-name",
                "椰椰小岛两栖泳衣三件套",
                "--brand",
                "品牌A",
                "--i-id",
                "STYLE001",
                "--sku-code",
                "BARCODE001",
                "--label",
                "夏季",
                "--not-label",
                "停用",
                "--load-sku-bin",
                "--field",
                "purchase_price",
                "--field",
                "pics",
            ],
            "product_skus",
            {
                "exactly_name": "椰椰小岛两栖泳衣三件套",
                "brand": ["品牌A"],
                "i_ids": ["STYLE001"],
                "sku_codes": "BARCODE001",
                "labels": ["夏季"],
                "not_labels": ["停用"],
                "load_sku_bin": True,
                "flds": "purchase_price,pics",
            },
        ),
        (
            [
                "product-styles",
                "--i-id",
                "STYLE001",
                "--only-item",
                "--item-field",
                "brand",
                "--sku-field",
                "pics",
            ],
            "product_styles",
            {
                "i_ids": ["STYLE001"],
                "only_item": True,
                "item_flds": ["brand"],
                "itemsku_flds": ["pics"],
            },
        ),
    ],
)
def test_cli_executes_new_read_only_commands(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expected_name: str,
    expected_values: dict[str, Any],
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli.Settings, "load", lambda: object())
    monkeypatch.setattr(cli, "JstClient", lambda _: RecordingClient(calls))

    assert cli.main(argv) == 0
    assert calls[0][0] == expected_name
    for key, value in expected_values.items():
        assert calls[0][1][key] == value


def test_cli_reports_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.Settings, "load", lambda: object())
    monkeypatch.setattr(
        cli,
        "JstClient",
        lambda _: RecordingClient([], ValueError("测试校验失败")),
    )

    assert cli.main(["inventory", "--sku", "SKU001"]) == 1
    assert "错误：测试校验失败" in capsys.readouterr().err
