import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.grading import grade_lookup

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_grades_quant_criterion_within_c_range(conn):
    result = grade_lookup(
        conn, member="콘크리트 바닥판", item="균열1)", subitem="1방향 균열",
        measures={"균열폭": 0.35}, year=2026,
    )
    assert result["status"] == "graded"
    assert result["grade"] == "c"
    assert any("0.3㎜이상～0.5㎜미만" in e["criterion_raw"] for e in result["evidence"])


def test_takes_worse_grade_when_multiple_indicators_disagree(conn):
    # 균열폭은 b 구간(0.1~0.3), 균열률은 d 구간(10~20%) -> 더 나쁜 d 채택
    result = grade_lookup(
        conn, member="콘크리트 바닥판", item="균열1)", subitem="1방향 균열",
        measures={"균열폭": 0.2, "균열률": 15}, year=2026,
    )
    assert result["status"] == "graded"
    assert result["grade"] == "d"


def test_mixed_quant_and_qual_item_falls_back_to_needs_judgment_when_measures_dont_cover_quant_fields(conn):
    # 열화 및 손상/철근부식은 실제로는 혼합 항목이다:
    # - c/d등급: 정량 기준 (철근부식손상률 %)
    # - e등급: 정성 서술만 ("단면감소가 심하여...")
    # measures를 전혀 제공하지 않으면, 정량 판정이 불가능하므로
    # 정성 후보로 폴백해야 한다 (no_match 반환 금지).
    result = grade_lookup(
        conn, member="콘크리트 바닥판", item="열화 및 손상", subitem="철근부식",
        measures={}, year=2026,
    )
    assert result["status"] == "needs_judgment"
    grades = {c["grade"] for c in result["candidates"]}
    assert "e" in grades
    assert any("단면감소가 심하여" in c["criterion_raw"] for c in result["candidates"] if c["grade"] == "e")


def test_returns_not_found_for_unknown_member(conn):
    result = grade_lookup(conn, member="존재하지않는부재", item="x", subitem="", measures={})
    assert result["status"] == "not_found"


def test_quant_value_in_gap_falls_back_to_needs_judgment_when_qual_exists(conn):
    """When a measure value falls in a gap between defined quant ranges,
    and qual candidates exist, fall back to needs_judgment instead of no_match.

    This tests a real information-loss bug: if a value doesn't match any quant range
    but qual rows are available, we should surface those as judgment candidates
    rather than silently dropping them with no_match.
    """
    cur = conn.cursor()

    try:
        # Insert synthetic test data with a gap in quant coverage:
        # - Grade c: 0～50%
        # - Grade d: 50～80%
        # - Gap: 80%+ is uncovered
        # Plus a qual row for grade e (fallback for edge cases)

        cur.execute("""
            INSERT INTO criteria
            (year, section, member, item, subitem, criterion_type, grade, criterion_raw,
             parsed_field, parsed_min, parsed_min_op, parsed_max, parsed_max_op, table_no, page, source_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (2026, "test_section", "갭테스트부재", "갭테스트항목", "갭테스트서브", "quant", "c",
              "0～50%", "갭테스트지표", 0, ">=", 50, "<", "T1", 1, "test_source"))

        cur.execute("""
            INSERT INTO criteria
            (year, section, member, item, subitem, criterion_type, grade, criterion_raw,
             parsed_field, parsed_min, parsed_min_op, parsed_max, parsed_max_op, table_no, page, source_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (2026, "test_section", "갭테스트부재", "갭테스트항목", "갭테스트서브", "quant", "d",
              "50～80%", "갭테스트지표", 50, ">=", 80, "<", "T1", 2, "test_source"))

        # Insert qual row for grade e (fallback candidate)
        cur.execute("""
            INSERT INTO criteria
            (year, section, member, item, subitem, criterion_type, grade, criterion_raw, table_no, page, source_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (2026, "test_section", "갭테스트부재", "갭테스트항목", "갭테스트서브", "qual", "e",
              "심각한 손상 발견", "T1", 3, "test_source"))

        conn.commit()

        # Query with value 90 (in the gap - exceeds all defined quant ranges)
        result = grade_lookup(
            conn, member="갭테스트부재", item="갭테스트항목", subitem="갭테스트서브",
            measures={"갭테스트지표": 90}, year=2026,
        )

        # Should fall back to needs_judgment with qual candidates, not no_match
        assert result["status"] == "needs_judgment", f"Expected needs_judgment but got {result['status']}"
        assert any(c["grade"] == "e" for c in result["candidates"])
        assert any("심각한 손상" in c["criterion_raw"] for c in result["candidates"])

    finally:
        # Cleanup: remove test data
        cur.execute("DELETE FROM criteria WHERE year=2026 AND member='갭테스트부재'")
        conn.commit()
