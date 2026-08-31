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


def test_returns_needs_judgment_for_qualitative_only_item(conn):
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
