"""LLM 도구호출 오케스트레이션. 등급 판정/구간 비교는 도구(파이썬 함수)가 계산하고
LLM은 도구 결과를 인용해 자연어로 설명만 한다."""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.grading import grade_lookup
from app.compare import compare_years


def _get_conn():
    from app.main import get_conn
    return get_conn()


def _get_searcher(year: int):
    from app.main import get_searcher
    return get_searcher(year)


@tool
def grade_lookup_tool(member: str, item: str, subitem: str | None, measures: dict[str, float], year: int = 2026) -> dict:
    """부재/평가항목/세부항목과 측정값(예: 균열폭, 균열률)으로 상태평가 등급을 판정한다."""
    return grade_lookup(_get_conn(), member, item, subitem, measures, year)


@tool
def compare_years_tool(member: str, item: str, subitem: str | None, years: list[int]) -> dict:
    """같은 부재/평가항목/세부항목의 판정기준이 연도별로 어떻게 다른지 비교한다."""
    return compare_years(_get_conn(), member, item, subitem, years)


@tool
def search_text_tool(query: str, section: str = "", year: int = 2026) -> list:
    """지침서 서술형 본문(정의, 절차, 설명)을 검색한다. 표 기반 등급판정은 grade_lookup_tool을 쓴다."""
    return _get_searcher(year).search(query, section or None)


TOOLS = [grade_lookup_tool, compare_years_tool, search_text_tool]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYSTEM_PROMPT = (
    "당신은 「시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편」에 정통한 전문가입니다. "
    "등급 판정이나 구간 비교가 필요하면 반드시 도구를 호출하고, 직접 숫자를 비교해 등급을 판단하지 마세요. "
    "도구가 'needs_judgment'를 반환하면 이는 정성적 판단이 필요하다는 뜻이므로 최종 등급을 단정하지 말고 "
    "후보와 근거를 제시한 뒤 점검자의 판단이 필요하다고 안내하세요. 항상 표 번호와 면수를 출처로 인용하세요."
)


MAX_TOOL_ITERATIONS = 8
TOOL_LIMIT_MESSAGE = "죄송합니다. 도구 호출 횟수 제한에 도달했습니다. 질문을 더 구체적으로 다시 시도해주세요."


def run_chat(llm, message: str) -> str:
    llm_with_tools = llm.bind_tools(TOOLS)
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=message)]
    response = llm_with_tools.invoke(messages)
    messages.append(response)

    iterations = 0
    while response.tool_calls:
        if iterations >= MAX_TOOL_ITERATIONS:
            return TOOL_LIMIT_MESSAGE
        for call in response.tool_calls:
            if call["name"] not in TOOLS_BY_NAME:
                error_msg = f"오류: 알 수 없는 도구 '{call['name']}'"
                messages.append(ToolMessage(content=error_msg, tool_call_id=call["id"]))
            else:
                result = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
                messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        iterations += 1

    return response.content
