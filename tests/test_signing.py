from jst_connector.signing import sign_params


def test_sign_params_sorts_keys_and_prefixes_secret() -> None:
    params = {"timestamp": "100", "app_key": "app", "charset": "utf-8"}
    assert sign_params(params, "secret") == "706427ca94e342781ac36d501151cb10"
