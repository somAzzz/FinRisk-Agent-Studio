from unittest.mock import MagicMock, patch

from scripts.real_data_acceptance import ApiClient


def test_api_client_sends_configured_key_without_mutating_payload() -> None:
    response = MagicMock()
    response.read.return_value = b'{"status":"ok"}'
    response.__enter__.return_value = response
    payload = {"demo_mode": False}

    with patch("scripts.real_data_acceptance.urlopen", return_value=response) as open_url:
        result = ApiClient(
            "http://127.0.0.1:8000",
            timeout_s=5,
            api_key="local-secret",
        ).post("/workflows/finrisk/run", payload)

    request = open_url.call_args.args[0]
    assert request.get_header("X-api-key") == "local-secret"
    assert payload == {"demo_mode": False}
    assert result == {"status": "ok"}
