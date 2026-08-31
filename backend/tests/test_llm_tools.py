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
