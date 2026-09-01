"""LLM 도구호출 오케스트레이션. 등급 판정/구간 비교는 도구(파이썬 함수)가 계산하고
LLM은 도구 결과를 인용해 자연어로 설명만 한다."""
from __future__ import annotations

import contextlib

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

from app.conn import get_conn, get_searcher
from app.grading import grade_lookup
from app.compare import compare_years


def _get_conn():
    return get_conn()


def _get_searcher(year: int):
    return get_searcher(year)


_DEFAULT_YEAR = 2026


def _year_or_default(year: int | str | None) -> int:
    # 일부 모델(특히 작은 로컬 모델)은 선택 인자를 생략하는 대신 명시적으로
    # null이나 빈 문자열을 채워 넣는다. 그러면 함수 기본값(=2026)이 아예
    # 적용되지 않고 그 값이 그대로 전달되어 실패하므로, 여기서 한 번 더
    # 방어한다(2026-09-01 llama3.1:8b 실측: year=''를 반복 전송).
    if year is None or year == "":
        return _DEFAULT_YEAR
    return int(year)


@tool
def list_criteria_tool(member_query: str = "", year: int | str | None = None) -> list[dict]:
    """grade_lookup_tool을 호출하기 전에 정확한 (member, item, subitem) 문자열을
    찾을 때 쓴다. DB에 저장된 부재/평가항목/세부항목은 지침서 원문 그대로라
    "균열1)"처럼 괄호가 붙어 있거나 "1방향 균열"처럼 접미사가 붙는 등 짐작으로는
    맞히기 어렵다. member_query(부분 문자열, 비워두면 전체)로 후보를 찾은 뒤
    정확한 값을 grade_lookup_tool/compare_years_tool에 그대로 복사해서 쓴다."""
    year = _year_or_default(year)
    with contextlib.closing(_get_conn()) as conn:
        cur = conn.execute(
            "SELECT DISTINCT member, item, subitem FROM criteria "
            "WHERE year=? AND member LIKE ? ORDER BY member, item, subitem",
            (year, f"%{member_query}%"),
        )
        return [dict(r) for r in cur.fetchall()]


@tool
def grade_lookup_tool(
    member: str, item: str, subitem: str | None, measures: dict[str, float], year: int | str | None = None,
) -> dict:
    """부재/평가항목/세부항목과 측정값(예: 균열폭, 균열률)으로 상태평가 등급을 판정한다.
    member/item/subitem은 반드시 list_criteria_tool로 확인한 정확한 문자열을 써야 한다
    (짐작한 문자열을 넣으면 'not_found'가 반환된다)."""
    year = _year_or_default(year)
    with contextlib.closing(_get_conn()) as conn:
        return grade_lookup(conn, member, item, subitem, measures, year)


@tool
def compare_years_tool(member: str, item: str, subitem: str | None, years: list[int]) -> dict:
    """같은 부재/평가항목/세부항목의 판정기준이 연도별로 어떻게 다른지 비교한다."""
    with contextlib.closing(_get_conn()) as conn:
        return compare_years(conn, member, item, subitem, years)


@tool
def search_text_tool(query: str, section: str = "", year: int | str | None = None) -> list:
    """지침서 서술형 본문(정의, 절차, 설명)을 검색한다. 표 기반 등급판정은 grade_lookup_tool을 쓴다."""
    return _get_searcher(_year_or_default(year)).search(query, section or None)


TOOLS = [list_criteria_tool, grade_lookup_tool, compare_years_tool, search_text_tool]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

SYSTEM_PROMPT = (
    "당신은 「시설물의 안전 및 유지관리 실시 세부지침(안전점검·진단 편) 교량편」에 정통한 전문가입니다. "
    "등급 판정이나 구간 비교가 필요하면 반드시 도구를 호출하고, 직접 숫자를 비교해 등급을 판단하지 마세요. "
    "grade_lookup_tool/compare_years_tool의 member/item/subitem은 짐작해서 채우지 말고, "
    "정확한 값이 확실하지 않으면 먼저 list_criteria_tool로 실제 문자열을 확인한 뒤 그대로 복사해서 쓰세요 "
    "(grade_lookup_tool이 'not_found'를 반환하면 이름을 잘못 짐작한 것이니 list_criteria_tool로 다시 확인하세요). "
    "도구가 'needs_judgment'를 반환하면 이는 정성적 판단이 필요하다는 뜻이므로 최종 등급을 단정하지 말고 "
    "후보와 근거를 제시한 뒤 점검자의 판단이 필요하다고 안내하세요. 항상 표 번호와 면수를 출처로 인용하세요."
)


MAX_TOOL_ITERATIONS = 8
TOOL_LIMIT_MESSAGE = "죄송합니다. 도구 호출 횟수 제한에 도달했습니다. 질문을 더 구체적으로 다시 시도해주세요."


def run_chat(llm, message: str) -> str:
    # SYSTEM_PROMPT를 SystemMessage로 분리하지 않고 HumanMessage에 합친다.
    # 실측 결과 Ollama(예: qwen2.5:7b)는 도구 정의를 system 슬롯에 자체 주입하는
    # 템플릿을 쓰는데, 여기에 커스텀 SystemMessage를 넣으면 그 슬롯을 덮어써서
    # 모델이 구조화된 tool_calls 대신 "<tool_call>..." 원문 텍스트를 그대로
    # content로 흘려보내는 회귀가 발생했다(2026-09-01 실측 확인). Anthropic/NVIDIA는
    # 이 방식으로도 정상 동작하는 것을 확인했으므로, 모든 provider에 안전한
    # HumanMessage 결합 방식으로 통일한다.
    llm_with_tools = llm.bind_tools(TOOLS)
    messages = [HumanMessage(content=f"{SYSTEM_PROMPT}\n\n질문: {message}")]
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
                continue
            try:
                result = TOOLS_BY_NAME[call["name"]].invoke(call["args"])
                content = str(result)
            except Exception as e:  # noqa: BLE001 - 도구 인자가 잘못된 경우(특히 작은
                # 로컬 모델이 스키마와 다른 타입을 채워 넣는 경우) 루프 전체를 죽이는
                # 대신 오류를 LLM에게 돌려줘서 다시 시도하거나 사용자에게 안내하게 한다.
                content = f"오류: 도구 '{call['name']}' 실행 실패 - {e}"
            messages.append(ToolMessage(content=content, tool_call_id=call["id"]))
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        iterations += 1

    return response.content
