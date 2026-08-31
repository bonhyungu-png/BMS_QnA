from app.llm_config import load_config


def test_load_config_prefers_env_var_over_file(monkeypatch):
    monkeypatch.setenv("BRIDGE_QNA_API_KEY", "sk-ant-fake-key-for-test")
    monkeypatch.delenv("BRIDGE_QNA_PROVIDER", raising=False)
    monkeypatch.delenv("BRIDGE_QNA_MODEL", raising=False)

    config = load_config()

    assert config["key"] == "sk-ant-fake-key-for-test"
    assert config["provider"] == "anthropic"
    assert config["model"] == "claude-opus-5"


def test_load_config_env_var_respects_explicit_provider_and_model(monkeypatch):
    monkeypatch.setenv("BRIDGE_QNA_API_KEY", "sk-ant-fake-key-for-test")
    monkeypatch.setenv("BRIDGE_QNA_PROVIDER", "anthropic")
    monkeypatch.setenv("BRIDGE_QNA_MODEL", "claude-sonnet-5")

    config = load_config()

    assert config["provider"] == "anthropic"
    assert config["model"] == "claude-sonnet-5"
