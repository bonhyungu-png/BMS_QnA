"""api_key.txt에서 provider/model/key를 읽는다. QA/qna.py의 로직을 그대로 이식했다.

배포 환경(예: Render)에서는 api_key.txt를 git에 커밋하는 대신 환경변수로 키를
주입할 수 있다 — BRIDGE_QNA_API_KEY가 설정되어 있으면 파일보다 우선한다."""
from __future__ import annotations

import os
from pathlib import Path

API_KEY_FILE = Path(__file__).resolve().parent.parent / "api_key.txt"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

KEY_PREFIX_MAP = [("sk-ant-", "anthropic"), ("nvapi-", "nvidia"), ("sk-", "openai")]
DEFAULT_MODEL_BY_PROVIDER = {
    "anthropic": "claude-opus-5",
    "nvidia": "nvidia/nemotron-3-nano-30b-a3b",
    "openai": "gpt-4o",
    "ollama": "qwen2.5:7b",
}


def detect_provider(key: str) -> str:
    for prefix, provider in KEY_PREFIX_MAP:
        if key.startswith(prefix):
            return provider
    raise ValueError(f"API 키 형식으로 provider를 자동 판별하지 못했습니다: '{key[:8]}...'")


def load_config() -> dict:
    # ollama는 로컬(또는 터널로 노출된) 서버라 API 키가 필요 없다 -
    # BRIDGE_QNA_PROVIDER=ollama가 설정되어 있으면 키 없이 바로 구성한다.
    if os.environ.get("BRIDGE_QNA_PROVIDER") == "ollama":
        return {
            "provider": "ollama",
            "key": None,
            "model": os.environ.get("BRIDGE_QNA_MODEL") or DEFAULT_MODEL_BY_PROVIDER["ollama"],
            "base_url": os.environ.get("BRIDGE_QNA_OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
        }

    env_key = os.environ.get("BRIDGE_QNA_API_KEY")
    if env_key:
        config: dict = {
            "key": env_key,
            "provider": os.environ.get("BRIDGE_QNA_PROVIDER") or None,
            "model": os.environ.get("BRIDGE_QNA_MODEL") or None,
        }
        if not config["provider"]:
            config["provider"] = detect_provider(config["key"])
        if not config["model"]:
            config["model"] = DEFAULT_MODEL_BY_PROVIDER.get(config["provider"])
        return config

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
    """provider별 LangChain LLM 객체를 생성한다.

    nvidia/openai는 requirements.txt에 포함되지 않은 선택적(optional) 의존성이다
    (langchain/langchain-anthropic만 필수 의존성). 이 환경에는 두 패키지가 모두 설치되어
    있어 정상 동작하지만, 설치되어 있지 않은 다른 환경에서는 raw ModuleNotFoundError 대신
    무엇을 설치해야 하는지 알려주는 명확한 ValueError로 우아하게 실패(graceful degradation)한다.
    """
    provider = config["provider"]
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config["model"], api_key=config["key"], max_tokens=2048)
    elif provider == "nvidia":
        try:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA
        except ImportError as e:
            raise ValueError(
                "provider='nvidia'를 쓰려면 pip install langchain-nvidia-ai-endpoints 가 필요합니다."
            ) from e
        return ChatNVIDIA(model=config["model"], api_key=config["key"], timeout=120, max_tokens=4096)
    elif provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise ValueError(
                "provider='openai'를 쓰려면 pip install langchain-openai 가 필요합니다."
            ) from e
        return ChatOpenAI(model=config["model"], api_key=config["key"])
    elif provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as e:
            raise ValueError(
                "provider='ollama'를 쓰려면 pip install langchain-ollama 가 필요합니다."
            ) from e
        # temperature=0: 실측 결과(qwen2.5:7b) 기본 temperature에서는 도구를
        # 호출하지 않고 "~하겠습니다"라고 말로만 하고 끝내는 경우가 잦았는데,
        # 0으로 낮추니 안정적으로 실제 tool_calls를 반환했다(2026-09-01 확인).
        return ChatOllama(
            model=config["model"],
            base_url=config.get("base_url", DEFAULT_OLLAMA_BASE_URL),
            temperature=0,
        )
    raise ValueError(f"지원하지 않는 provider입니다: {provider}")
