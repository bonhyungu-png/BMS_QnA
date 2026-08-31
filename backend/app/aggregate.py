"""부재별 등급 -> 구조형식별/본교별/전체 시설물 등급 산정 (1.4절 본문 5단계 절차).

① 부재별 상태평가 -> ② 가중치 적용 환산 결함도 점수(표1.31/32) ->
③ 결함도 점수 범위(표1.33)로 구조형식별 등급 -> ④ 연장비 가중합으로 본교 등급 ->
⑤ 본교/램프교/접속교 연장비 가중합으로 전체 등급.
중대한 결함이 발생한 경우, 해당 부재/구조형식의 등급이 가중평균보다 나쁘면 그 등급을 그대로 채택한다.
"""
from __future__ import annotations

import sqlite3

# 표1.10/1.31 부재명 -> 표1.31 '결함도 평가항목' 매핑.
# 새 부재가 추가되면(예: 케이블부재, 강 거더 등 특수교/강교 부재) 이 표를 함께 갱신해야 한다.
MEMBER_TO_DEFECT_ITEM: dict[str, str] = {
    "콘크리트 바닥판": "바닥판", "강 바닥판": "바닥판", "프리스트레스 콘크리트 바닥판": "바닥판",
    "철근콘크리트 거더": "주 형", "프리스트레스 콘크리트 거더": "주 형",
    "콘크리트 가로보": "2차부재", "강 가로보와 세로보": "2차부재",
    "교대": "교대/교각", "콘크리트 교각": "교대/교각", "강 교각(강 주탑)": "교대/교각",
    "기초": "기초",
    "교량받침": "교량받침",
    "신축이음": "신축이음",
    "아스팔트 콘크리트 교면포장": "교면포장", "시멘트 콘크리트 교면포장": "교면포장",
    "배수시설": "배수시설",
    "난간 및 연석": "난간/연석",
}

_GRADE_TO_LETTER_KEY = str.upper


def _defect_index_for_grade(conn: sqlite3.Connection, year: int, grade: str) -> float | None:
    row = conn.execute(
        "SELECT index_value FROM defect_score WHERE year=? AND grade=?",
        (year, _GRADE_TO_LETTER_KEY(grade)),
    ).fetchone()
    return row["index_value"] if row else None


def _grade_for_score(conn: sqlite3.Connection, year: int, score: float) -> str | None:
    row = conn.execute(
        "SELECT grade FROM defect_score WHERE year=? "
        "AND (range_min IS NULL OR ? >= range_min) "
        "AND (range_max IS NULL OR ? < range_max)",
        (year, score, score),
    ).fetchone()
    return row["grade"] if row else None


def aggregate_structure_grade(
    conn: sqlite3.Connection,
    year: int,
    structure_type: str,
    member_grades: dict[str, str],
    critical_defect_member: str | None = None,
) -> dict:
    # 구조형식 존재 여부 검증 (Finding 3)
    exists = conn.execute(
        "SELECT 1 FROM weight_tables WHERE year=? AND structure_type=? LIMIT 1",
        (year, structure_type),
    ).fetchone()
    if exists is None:
        raise ValueError(f"알 수 없는 구조형식입니다: {structure_type!r} (year={year})")

    # critical_defect_member이 member_grades에 있는지 검증 (Finding 1)
    if critical_defect_member and critical_defect_member not in member_grades:
        raise ValueError(f"critical_defect_member이 member_grades에 없습니다: {critical_defect_member!r}")

    total_weight = 0.0
    weighted_index_sum = 0.0
    contributions = []

    for member, grade in member_grades.items():
        defect_item = MEMBER_TO_DEFECT_ITEM.get(member)
        if defect_item is None:
            raise ValueError(f"알 수 없는 부재명입니다: {member!r} (MEMBER_TO_DEFECT_ITEM에 등록되지 않음)")
        weight_row = conn.execute(
            "SELECT weight FROM weight_tables WHERE year=? AND defect_item=? AND structure_type=?",
            (year, defect_item, structure_type),
        ).fetchone()
        if weight_row is None or weight_row["weight"] is None:
            continue
        idx = _defect_index_for_grade(conn, year, grade)
        # 유효한 등급인지 검증 (Finding 2)
        if idx is None:
            raise ValueError(f"'{member}'의 등급 '{grade}'이 유효한 등급(a~e)이 아닙니다.")
        weighted_index_sum += weight_row["weight"] * idx
        total_weight += weight_row["weight"]
        contributions.append({"member": member, "grade": grade, "weight": weight_row["weight"]})

    converted_score = weighted_index_sum / total_weight if total_weight else None
    computed_grade = _grade_for_score(conn, year, converted_score) if converted_score is not None else None
    result = {"grade": computed_grade, "converted_score": converted_score, "contributions": contributions}

    if critical_defect_member:
        critical_grade = member_grades[critical_defect_member]
        critical_index = _defect_index_for_grade(conn, year, critical_grade)
        if critical_index is not None and (converted_score is None or critical_index > converted_score):
            result["grade"] = critical_grade
            result["reason"] = f"중대한 결함 부재({critical_defect_member})의 등급을 우선 적용"

    return result


def aggregate_bridge_grade(
    conn: sqlite3.Connection,
    year: int,
    structure_results: dict[str, dict],
    span_ratios: dict[str, float],
    critical_defect_structure: str | None = None,
) -> dict:
    """본교(또는 램프교/접속교/전체 시설물)의 등급을 연장비 가중합으로 산정한다.
    같은 함수로 ④단계(구조형식들 -> 본교)와 ⑤단계(본교/램프교/접속교 -> 전체)를 모두 처리한다."""
    total_ratio = sum(span_ratios.values())
    weighted_sum = sum(
        structure_results[name]["converted_score"] * ratio
        for name, ratio in span_ratios.items()
        if structure_results[name]["converted_score"] is not None
    )
    converted_score = weighted_sum / total_ratio if total_ratio else None
    computed_grade = _grade_for_score(conn, year, converted_score) if converted_score is not None else None
    result = {"grade": computed_grade, "converted_score": converted_score}

    if critical_defect_structure:
        critical = structure_results[critical_defect_structure]
        if critical["converted_score"] is not None and (
            converted_score is None or critical["converted_score"] > converted_score
        ):
            result["grade"] = critical["grade"]
            result["converted_score"] = critical["converted_score"]
            result["reason"] = f"중대한 결함 구조형식({critical_defect_structure})의 등급을 우선 적용"

    return result
