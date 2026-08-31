"""api_key.txt에서 provider/model/key를 읽는다. QA/qna.py의 로직을 그대로 이식했다."""
from __future__ import annotations

from pathlib import Path

API_KEY_FILE = Path(__file__).resolve().parent.parent / "api_key.txt"

KEY_PREFIX_MAP = [("sk-ant-", "anthropic"), ("nvapi-", "nvidia"), ("sk-", "openai")]
DEFAULT_MODEL_BY_PROVIDER = {
    "anthropic": "claude-opus-5",
    "nvidia": "nvidia/nemotron-3-nano-30b-a3b",
    "openai": "gpt-4o",
}


def detect_provider(key: str) -> str:
    for prefix, provider in KEY_PREFIX_MAP:
        if key.startswith(prefix):
            return provider
    raise ValueError(f"API 키 형식으로 provider를 자동 판별하지 못했습니다: '{key[:8]}...'")


def load_config() -> dict:
    if not API_KEY_FILE.exists():
        raise FileNotFoundError(f"{API_KEY_FILE} 파일이 없습니다.")

    config: dict = {"key": None, "provider": None, "model": None}
    for raw_line in API_KEY_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line and line.split("=", 1)[0].strip().lower() in ("provider", "model", "key"):
            field, value = line.split("=", 1)
            config[field.strip().lower()] = value.strip()
        elif config["key"] is None:
            config["key"] = line

    if not config["key"] or "여기에" in config["key"]:
        raise ValueError(f"{API_KEY_FILE} 파일에 실제 API 키를 입력해야 합니다.")
    if not config["provider"]:
        config["provider"] = detect_provider(config["key"])
    if not config["model"]:
        config["model"] = DEFAULT_MODEL_BY_PROVIDER.get(config["provider"])
    return config


def build_llm(config: dict):
    provider = config["provider"]
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config["model"], api_key=config["key"], max_tokens=2048)
    elif provider == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA
        return ChatNVIDIA(model=config["model"], api_key=config["key"], timeout=120)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=config["model"], api_key=config["key"])
    raise ValueError(f"지원하지 않는 provider입니다: {provider}")
