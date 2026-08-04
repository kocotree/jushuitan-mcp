from __future__ import annotations

import hashlib
from collections.abc import Mapping


def sign_params(params: Mapping[str, object], app_secret: str) -> str:
    """按聚水潭新版 OpenAPI 规则生成 MD5 签名。"""
    source = app_secret + "".join(
        f"{key}{params[key]}" for key in sorted(params)
    )
    return hashlib.md5(source.encode("utf-8")).hexdigest()  # noqa: S324 - 平台协议要求 MD5
