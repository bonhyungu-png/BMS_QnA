from langchain_core.messages import AIMessage, HumanMessage

from app.llm_tools import run_chat, TOOLS_BY_NAME, MAX_TOOL_ITERATIONS, TOOL_LIMIT_MESSAGE


class _FakeLLMWithTools:
    """실제 API를 호출하지 않고 도구 실행 루프(run_chat)만 검증하기 위한 가짜 LLM."""

    def __init__(self, responses):
        self._responses = list(responses)

    def invoke(self, messages):
        return self._responses.pop(0)


class _FakeBoundLLM:
    def __init__(self, responses):
        self._llm = _FakeLLMWithTools(responses)

    def invoke(self, messages):
        return self._llm.invoke(messages)


class _FakeLLM:
    def __init__(self, responses):
        self._responses = responses

    def bind_tools(self, tools):
        return _FakeBoundLLM(self._responses)


def test_run_chat_executes_tool_call_then_returns_final_answer(monkeypatch):
    tool_call_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "grade_lookup_tool",
            "args": {"member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열",
                      "measures": {"균열폭": 0.35}, "year": 2026},
            "id": "call_1",
        }],
    )
    final_response = AIMessage(content="c등급입니다.", tool_calls=[])

    called_with = {}
    def fake_tool_invoke(args):
        called_with.update(args)
        return {"status": "graded", "grade": "c", "evidence": []}

    monkeypatch.setitem(TOOLS_BY_NAME, "grade_lookup_tool", type(
        "T", (), {"invoke": staticmethod(fake_tool_invoke)},
    )())

    llm = _FakeLLM([tool_call_response, final_response])
    answer = run_chat(llm, "바닥판에 0.35mm 균열이면 몇 등급인가요?")

    assert answer == "c등급입니다."
    assert called_with["member"] == "콘크리트 바닥판"


def test_run_chat_executes_multiple_tool_calls_in_one_turn(monkeypatch):
    """LLM이 한 번의 응답에서 두 개의 도구를 호출할 때, 둘 다 실행하고 결과를 모두 LLM에 전달해야 한다."""
    multi_tool_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "grade_lookup_tool",
                "args": {"member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열",
                          "measures": {"균열폭": 0.35}, "year": 2026},
                "id": "call_1",
            },
            {
                "name": "search_text_tool",
                "args": {"query": "균열 정의", "section": "3.1", "year": 2026},
                "id": "call_2",
            },
        ],
    )
    final_response = AIMessage(content="바닥판 균열은 c등급이고, 정의는 다음과 같습니다...", tool_calls=[])

    grade_call_count = {"count": 0}
    def fake_grade_invoke(args):
        grade_call_count["count"] += 1
        return {"status": "graded", "grade": "c", "evidence": []}

    search_call_count = {"count": 0}
    def fake_search_invoke(args):
        search_call_count["count"] += 1
        return [{"text": "균열: 콘크리트 표면의 균열", "page": 42}]

    monkeypatch.setitem(TOOLS_BY_NAME, "grade_lookup_tool", type(
        "T", (), {"invoke": staticmethod(fake_grade_invoke)},
    )())
    monkeypatch.setitem(TOOLS_BY_NAME, "search_text_tool", type(
        "T", (), {"invoke": staticmethod(fake_search_invoke)},
    )())

    llm = _FakeLLM([multi_tool_response, final_response])
    answer = run_chat(llm, "바닥판 균열과 그 정의는?")

    assert answer == "바닥판 균열은 c등급이고, 정의는 다음과 같습니다..."
    assert grade_call_count["count"] == 1
    assert search_call_count["count"] == 1


def test_run_chat_handles_unknown_tool_name_gracefully(monkeypatch):
    """LLM이 TOOLS_BY_NAME에 없는 도구를 호출하면, 오류 메시지를 반환하고 계속 진행해야 한다 (크래시하지 않음)."""
    unknown_tool_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "nonexistent_tool",
            "args": {"some_arg": "value"},
            "id": "call_1",
        }],
    )
    final_response = AIMessage(content="죄송하지만 해당 도구를 찾을 수 없습니다.", tool_calls=[])

    llm = _FakeLLM([unknown_tool_response, final_response])
    answer = run_chat(llm, "존재하지 않는 도구를 호출해보세요")

    assert answer == "죄송하지만 해당 도구를 찾을 수 없습니다."


def test_run_chat_handles_tool_argument_validation_error_gracefully(monkeypatch):
    """작은 로컬 모델(Ollama 등)이 스키마와 다른 타입의 인자를 채워 넣어 도구 호출이
    pydantic ValidationError를 던져도, run_chat은 크래시하지 않고 오류를 LLM에게
    돌려준 뒤 계속 진행해야 한다 (2026-09-01 Ollama qwen2.5:7b 실측에서 발견됨:
    subitem에 문자열 대신 빈 dict {}를 채워 넣어 ValidationError 발생)."""
    bad_args_response = AIMessage(
        content="",
        tool_calls=[{
            "name": "grade_lookup_tool",
            "args": {"member": "콘크리트 바닥판", "item": "균열", "subitem": {}, "measures": {}},
            "id": "call_1",
        }],
    )
    final_response = AIMessage(content="다시 시도하겠습니다.", tool_calls=[])

    llm = _FakeLLM([bad_args_response, final_response])
    answer = run_chat(llm, "콘크리트 바닥판의 균열폭 0.35mm는 몇 등급인가요?")

    assert answer == "다시 시도하겠습니다."


def test_run_chat_caps_infinite_tool_call_loop(monkeypatch):
    """모델이 tool_calls를 계속 반환해 절대 수렴하지 않아도, run_chat은 최대
    MAX_TOOL_ITERATIONS 라운드 후 안내 메시지를 반환하며 멈춰야 한다 (무한 루프 금지)."""

    def fake_search_invoke(args):
        return [{"text": "결과", "page": 1}]

    monkeypatch.setitem(TOOLS_BY_NAME, "search_text_tool", type(
        "T", (), {"invoke": staticmethod(fake_search_invoke)},
    )())

    def make_tool_call_response(i):
        return AIMessage(
            content="",
            tool_calls=[{
                "name": "search_text_tool",
                "args": {"query": f"질문{i}", "section": "", "year": 2026},
                "id": f"call_{i}",
            }],
        )

    # 테스트 프로세스 자체가 무한 루프에 빠지지 않도록, 필요한 라운드 수보다 약간만 더 준비한다.
    # run_chat이 cap을 지키지 않으면 이 목록이 바닥나 IndexError로 실패한다(무한 루프 대신).
    responses = [make_tool_call_response(i) for i in range(MAX_TOOL_ITERATIONS + 2)]

    llm = _FakeLLM(responses)
    answer = run_chat(llm, "끝나지 않는 질문")

    assert answer == TOOL_LIMIT_MESSAGE


def test_run_chat_embeds_system_prompt_in_human_message(monkeypatch):
    """SYSTEM_PROMPT는 SystemMessage로 분리하지 않고 HumanMessage에 합쳐 보내야 한다.

    Ollama(qwen2.5:7b) 실측에서 SystemMessage를 쓰면 도구 정의를 주입하는 system
    슬롯을 덮어써서 모델이 구조화된 tool_calls 대신 원문 텍스트를 흘리는 회귀가
    발생함을 확인했다(2026-09-01). 모든 provider에 안전한 방식은 HumanMessage 결합."""
    captured_messages = {}

    class _CapturingBoundLLM:
        def __init__(self, responses):
            self._responses = list(responses)

        def invoke(self, messages):
            if "first" not in captured_messages:
                captured_messages["first"] = list(messages)
            return self._responses.pop(0)

    class _CapturingLLM:
        def __init__(self, responses):
            self._responses = responses

        def bind_tools(self, tools):
            return _CapturingBoundLLM(self._responses)

    final_response = AIMessage(content="답변입니다.", tool_calls=[])
    llm = _CapturingLLM([final_response])
    answer = run_chat(llm, "질문 내용")

    assert answer == "답변입니다."
    first_messages = captured_messages["first"]
    assert len(first_messages) == 1
    assert isinstance(first_messages[0], HumanMessage)
    assert "질문 내용" in first_messages[0].content
