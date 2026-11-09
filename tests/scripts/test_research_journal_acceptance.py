import json

from scripts.research_journal_live_acceptance import DEFAULT_CONFIG, validate_config


def test_checked_in_scenario_accepts_server_model_defaults():
    config = json.loads(DEFAULT_CONFIG.read_text())
    assert config["llm"] == {"provider": "sglang"}
    validate_config(config)


def test_preflight_checks_the_server_selected_model_with_its_credential(monkeypatch):
    import httpx

    from scripts import research_journal_live_acceptance as acceptance
    from src.ai import model_factory
    from src.config import Settings

    settings = Settings(sglang_base_url="http://example.invalid/v1", sglang_model="custom", sglang_api_key="test")
    monkeypatch.setattr(model_factory, "get_settings", lambda: settings)

    def get(url, *, headers, timeout, follow_redirects):
        assert url == "http://example.invalid/v1/models"
        assert headers == {"Authorization": "Bearer test"}
        assert not follow_redirects
        return httpx.Response(200, json={"data": [{"id": "custom"}]}, request=httpx.Request("GET", url))

    monkeypatch.setattr(acceptance.httpx, "get", get)
    report = {"checks": []}
    acceptance.check_local_llm({"llm": {"provider": "sglang"}}, report)
    assert report["checks"][0]["model"] == "custom"
