import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.compare import compare_years

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_detects_member_newly_introduced_in_2026(conn):
    # 월류(여유고 조사)는 2026 신설 부재 -> 실제 데이터로 검증된 사실
    result = compare_years(conn, member="월류(여유고 조사)", item="여유고 검토1)", subitem="", years=[2024, 2026])
    assert result["by_year"][2024] == []
    assert len(result["by_year"][2026]) > 0


def test_unchanged_criterion_reports_no_diff(conn):
    # 표1.11 콘크리트 바닥판은 2022~2026 원문이 동일함을 diff로 이미 확인함
    result = compare_years(
        conn, member="콘크리트 바닥판", item="균열1)", subitem="1방향 균열", years=[2022, 2026],
    )
    assert result["changed_grades"] == {}


def test_changed_criterion_text_is_reported(conn):
    conn.execute(
        "INSERT INTO criteria (year, section, table_no, table_title, member, item, subitem, grade, "
        "criterion_raw, criterion_type, page, source_path) VALUES "
        "(2024, '1.4', 't', 'title', '테스트부재', '테스트항목', '', 'b', '균열폭 0.1이상', 'quant', 1, 'x')"
    )
    conn.execute(
        "INSERT INTO criteria (year, section, table_no, table_title, member, item, subitem, grade, "
        "criterion_raw, criterion_type, page, source_path) VALUES "
        "(2026, '1.4', 't', 'title', '테스트부재', '테스트항목', '', 'b', '균열폭 0.2이상', 'quant', 1, 'x')"
    )
    conn.commit()
    result = compare_years(conn, member="테스트부재", item="테스트항목", subitem="", years=[2024, 2026])
    assert "b" in result["changed_grades"]
    assert result["changed_grades"]["b"][2024] == ["균열폭 0.1이상"]
    assert result["changed_grades"]["b"][2026] == ["균열폭 0.2이상"]

    # Cleanup: delete synthetic test data
    conn.execute("DELETE FROM criteria WHERE member='테스트부재' AND item='테스트항목'")
    conn.commit()
