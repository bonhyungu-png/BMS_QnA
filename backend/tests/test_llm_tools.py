from langchain_core.messages import AIMessage

from app.llm_tools import run_chat, TOOLS_BY_NAME


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
