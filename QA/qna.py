"""
정밀안전점검·진단(교량편) 지침서 기반 QnA 시스템
- LangChain FewShotPromptTemplate 사용
- data/안전점검진단_교량편 아래 문서를 근거로 답변
"""
import glob
import sys
from pathlib import Path

# Windows 콘솔 기본 코드페이지(cp949)로는 지침서 원문에 포함된 일부 특수문자를
# 출력하지 못해 프로그램이 죽을 수 있으므로 표준출력을 UTF-8로 강제한다.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data" / "안전점검진단_교량편"
API_KEY_FILE = BASE_DIR / "api_key.txt"
TARGET_YEAR = "2026"  # 사용할 지침서 판본 연도
TOP_K = 4  # 질문 하나당 참고할 문서 조각 수


# 키 접두사로 provider를 자동 판별한다. (필요하면 api_key.txt에 provider=... 로 직접 지정 가능)
KEY_PREFIX_MAP = [
    ("sk-ant-", "anthropic"),
    ("nvapi-", "nvidia"),
    ("sk-", "openai"),
]

# provider별 기본 모델 (api_key.txt에 model=... 을 적으면 이 값 대신 사용된다)
# nvidia 기본값은 무료 엔드포인트에서 빠르고 안정적으로 응답하는 모델로 선택했다.
# kimi-k3, nemotron-3-ultra-550b-a55b 같은 초대형 모델은 무료 엔드포인트에서
# 응답 지연/일시적 과부하(503)가 잦아 model=... 로 명시했을 때만 쓰는 것을 권장한다.
DEFAULT_MODEL_BY_PROVIDER = {
    "anthropic": "claude-opus-5",
    "nvidia": "nvidia/nemotron-3-nano-30b-a3b",
    "openai": "gpt-4o",
}


def detect_provider(key: str) -> str:
    for prefix, provider in KEY_PREFIX_MAP:
        if key.startswith(prefix):
            return provider
    raise ValueError(
        f"API 키 형식으로 provider를 자동 판별하지 못했습니다: '{key[:8]}...'. "
        f"{API_KEY_FILE} 에 'provider=anthropic' (또는 nvidia/openai) 줄을 추가해 직접 지정하세요."
    )


def load_config() -> dict:
    """
    api_key.txt 형식:
        <API 키 한 줄>
        provider=anthropic   # 선택. 없으면 키 접두사로 자동 판별
        model=claude-opus-5  # 선택. 없으면 provider별 기본 모델 사용
        # 로 시작하는 줄은 주석으로 무시
    """
    if not API_KEY_FILE.exists():
        raise FileNotFoundError(
            f"{API_KEY_FILE} 파일이 없습니다. 이 텍스트 파일에 API 키를 입력하세요."
        )

    config = {"key": None, "provider": None, "model": None}
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


def load_documents(year: str = TARGET_YEAR):
    pattern = str(DATA_DIR / "**" / year / "*.md")
    docs = []
    for path in glob.glob(pattern, recursive=True):
        content = Path(path).read_text(encoding="utf-8")
        docs.append({"source": path, "content": content})
    if not docs:
        raise FileNotFoundError(f"{DATA_DIR} 아래에서 {year} 판본 문서를 찾지 못했습니다.")
    return docs


class DocumentRetriever:
    """TF-IDF 코사인 유사도로 질문과 관련된 문서 조각을 찾는다."""

    def __init__(self, docs, top_k: int = TOP_K):
        self.docs = docs
        self.top_k = top_k
        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform([d["content"] for d in docs])

    def retrieve(self, query: str):
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.matrix)[0]
        top_idx = sims.argsort()[::-1][: self.top_k]
        return [self.docs[i] for i in top_idx if sims[i] > 0]


# Few-shot 예시: 정밀안전점검_교량편에 대한 질문-답변 스타일을 모델에 시연
FEW_SHOT_EXAMPLES = [
    {
        "question": "교량의 특수교(特殊橋)는 어떤 교량을 말하나요?",
        "answer": "교량 상부구조형식이 현수교, 사장교, 아치교, 트러스교인 교량을 특수교라고 합니다.",
    },
    {
        "question": "정밀안전점검 대상이 되는 제1종시설물 도로교량의 기준은 무엇인가요?",
        "answer": "상부구조형식이 현수교·사장교·아치교·트러스교인 교량, 최대 경간장 50m 이상인 교량(한 경간 교량 제외), 연장 500m 이상인 교량 등이 해당합니다.",
    },
    {
        "question": "교량 정밀안전점검 시 상부구조에서 점검하는 부재는 무엇인가요?",
        "answer": "상부구조는 바닥판과 거더를 대상으로 정기안전점검·정밀안전점검·정밀안전진단을 모두 실시합니다.",
    },
]

EXAMPLE_PROMPT = PromptTemplate(
    input_variables=["question", "answer"],
    template="질문: {question}\n답변: {answer}",
)

PREFIX = (
    "당신은 「시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편」에 정통한 전문가입니다.\n"
    "반드시 아래 [참고 문서]에 있는 내용만 근거로 답변하고, 문서에 없는 내용은 추측하지 말고 "
    "\"문서에서 확인되지 않습니다\"라고 답하세요.\n"
    "다음은 질문과 답변 형식의 예시입니다."
)

SUFFIX = (
    "\n[참고 문서]\n{context}\n\n"
    "이제 위와 같은 형식으로 아래 질문에 간결하고 정확하게 한국어로 답변하세요.\n\n"
    "질문: {question}\n답변:"
)

FEW_SHOT_PROMPT = FewShotPromptTemplate(
    examples=FEW_SHOT_EXAMPLES,
    example_prompt=EXAMPLE_PROMPT,
    prefix=PREFIX,
    suffix=SUFFIX,
    input_variables=["context", "question"],
)


def build_llm(config: dict):
    provider = config["provider"]
    model = config["model"]
    api_key = config["key"]

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=api_key,
            max_tokens=2048,
            thinking={"type": "adaptive"},
        )
    elif provider == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(model=model, api_key=api_key, timeout=120)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=api_key)
    else:
        raise ValueError(f"지원하지 않는 provider입니다: {provider}")


def format_context(docs) -> str:
    parts = []
    for d in docs:
        rel_path = Path(d["source"]).relative_to(DATA_DIR)
        parts.append(f"[출처: {rel_path}]\n{d['content']}")
    return "\n\n---\n\n".join(parts)


def _is_transient_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("503", "overloaded", "timed out", "timeout", "temporarily unavailable", "429")
    )


@retry(
    retry=retry_if_exception(_is_transient_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    reraise=True,
)
def _invoke_with_retry(llm, prompt: str):
    return llm.invoke(prompt)


def answer_question(question: str, retriever: DocumentRetriever, llm) -> str:
    docs = retriever.retrieve(question)
    context = format_context(docs) if docs else "(관련 문서를 찾지 못했습니다.)"
    prompt = FEW_SHOT_PROMPT.format(context=context, question=question)
    response = _invoke_with_retry(llm, prompt)
    return response.content


def main():
    config = load_config()
    print(f"provider: {config['provider']}, model: {config['model']}")

    print("교량편 지침서 문서를 불러오는 중입니다...")
    docs = load_documents()
    print(f"{len(docs)}개의 문서를 불러왔습니다. (판본: {TARGET_YEAR})")
    retriever = DocumentRetriever(docs)
    llm = build_llm(config)

    print("\n정밀안전점검_교량편 QnA 시스템입니다. 종료하려면 'exit' 또는 'quit'을 입력하세요.\n")
    while True:
        question = input("질문> ").strip()
        if question.lower() in ("exit", "quit"):
            break
        if not question:
            continue
        try:
            answer = answer_question(question, retriever, llm)
        except Exception as e:
            print(f"[오류] {e}")
            continue
        print(f"답변> {answer}\n")


if __name__ == "__main__":
    main()
