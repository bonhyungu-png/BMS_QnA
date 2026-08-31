import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.aggregate import aggregate_structure_grade, aggregate_bridge_grade

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"

STRUCTURE_TYPE = "거더교량 > 일반 거더교 > 일반"
ALL_MEMBERS = {
    "콘크리트 바닥판": "a", "철근콘크리트 거더": "a", "콘크리트 가로보": "a",
    "교대": "a", "기초": "a", "교량받침": "a", "신축이음": "a",
    "아스팔트 콘크리트 교면포장": "a", "배수시설": "a", "난간 및 연석": "a",
}


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_all_grade_a_yields_structure_grade_a(conn):
    # 10개 부재(탄산화/염화물/월류 제외)의 가중치 합계 110이므로, 전 부재 a등급(지수 0.10)이면
    # 환산 결함도 점수 = 0.10, 표1.33 A범위(0<=X<0.13) 안에 든다.
    result = aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, ALL_MEMBERS)
    assert result["converted_score"] == pytest.approx(0.10, abs=1e-6)
    assert result["grade"] == "A"


def test_one_bad_member_drags_score_into_c_range(conn):
    # 기초(가중치 21) 하나만 e등급(지수 1.00), 나머지 9개는 a(지수 0.10):
    # (89*0.10 + 21*1.00) / 110 = 29.9 / 110 = 0.2718... -> 표1.33 C범위(0.26<=X<0.49)
    grades = dict(ALL_MEMBERS)
    grades["기초"] = "e"
    result = aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, grades)
    assert result["converted_score"] == pytest.approx(29.9 / 110, abs=1e-6)
    assert result["grade"] == "C"


def test_critical_defect_overrides_weighted_average(conn):
    grades = dict(ALL_MEMBERS)
    grades["기초"] = "e"
    result = aggregate_structure_grade(
        conn, 2026, STRUCTURE_TYPE, grades, critical_defect_member="기초",
    )
    assert result["grade"] == "e"  # 가중평균(C)보다 중대결함 부재의 e가 더 나쁘므로 그대로 채택
    assert "중대한 결함" in result["reason"]


def test_unknown_member_name_raises_clear_error(conn):
    with pytest.raises(ValueError, match="알 수 없는 부재명"):
        aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, {"없는부재": "a"})


def test_critical_defect_member_not_in_member_grades_raises_clear_error(conn):
    with pytest.raises(ValueError, match="critical_defect_member"):
        aggregate_structure_grade(
            conn, 2026, STRUCTURE_TYPE, ALL_MEMBERS, critical_defect_member="없는부재",
        )


def test_invalid_grade_letter_raises_clear_error(conn):
    grades = dict(ALL_MEMBERS)
    grades["기초"] = "z"
    with pytest.raises(ValueError, match="유효한 등급"):
        aggregate_structure_grade(conn, 2026, STRUCTURE_TYPE, grades)


def test_unknown_structure_type_raises_clear_error(conn):
    with pytest.raises(ValueError, match="알 수 없는 구조형식"):
        aggregate_structure_grade(conn, 2026, "존재하지않는구조형식", ALL_MEMBERS)


def test_aggregate_bridge_grade_weights_by_span_ratio(conn):
    structure_results = {
        "강거더교_구간": {"grade": "A", "converted_score": 0.10},
        "PSC거더교_구간": {"grade": "C", "converted_score": 0.30},
    }
    span_ratios = {"강거더교_구간": 300.0, "PSC거더교_구간": 100.0}  # 연장(m) 비율
    result = aggregate_bridge_grade(conn, 2026, structure_results, span_ratios)

    expected_score = (0.10 * 300 + 0.30 * 100) / 400  # = 0.15
    assert result["converted_score"] == pytest.approx(expected_score, abs=1e-6)
    assert result["grade"] == "B"  # 표1.33: 0.13<=X<0.26


def test_critical_defect_structure_overrides_bridge_average(conn):
    structure_results = {
        "강거더교_구간": {"grade": "A", "converted_score": 0.10},
        "PSC거더교_구간": {"grade": "E", "converted_score": 1.00},
    }
    span_ratios = {"강거더교_구간": 300.0, "PSC거더교_구간": 100.0}
    result = aggregate_bridge_grade(
        conn, 2026, structure_results, span_ratios, critical_defect_structure="PSC거더교_구간",
    )
    assert result["grade"] == "E"
    assert "중대한 결함" in result["reason"]
