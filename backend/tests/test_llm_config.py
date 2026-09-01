from app.llm_config import DEFAULT_OLLAMA_BASE_URL, load_config


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


def test_load_config_ollama_needs_no_api_key(monkeypatch):
    monkeypatch.setenv("BRIDGE_QNA_PROVIDER", "ollama")
    monkeypatch.delenv("BRIDGE_QNA_API_KEY", raising=False)
    monkeypatch.delenv("BRIDGE_QNA_MODEL", raising=False)
    monkeypatch.delenv("BRIDGE_QNA_OLLAMA_BASE_URL", raising=False)

    config = load_config()

    assert config["provider"] == "ollama"
    assert config["key"] is None
    assert config["model"] == "qwen2.5:7b"
    assert config["base_url"] == DEFAULT_OLLAMA_BASE_URL


def test_load_config_ollama_respects_explicit_model_and_base_url(monkeypatch):
    monkeypatch.setenv("BRIDGE_QNA_PROVIDER", "ollama")
    monkeypatch.setenv("BRIDGE_QNA_MODEL", "llama3.1:8b")
    monkeypatch.setenv("BRIDGE_QNA_OLLAMA_BASE_URL", "https://example.ngrok.app")

    config = load_config()

    assert config["model"] == "llama3.1:8b"
    assert config["base_url"] == "https://example.ngrok.app"


def test_load_config_ollama_takes_priority_over_api_key_env_var(monkeypatch):
    # BRIDGE_QNA_PROVIDER=ollama가 설정되어 있으면 실수로 BRIDGE_QNA_API_KEY가
    # 함께 남아있어도 ollama 경로가 우선한다(ollama는 키가 필요 없으므로).
    monkeypatch.setenv("BRIDGE_QNA_PROVIDER", "ollama")
    monkeypatch.setenv("BRIDGE_QNA_API_KEY", "sk-ant-should-be-ignored")
    monkeypatch.delenv("BRIDGE_QNA_MODEL", raising=False)

    config = load_config()

    assert config["provider"] == "ollama"
    assert config["key"] is None
