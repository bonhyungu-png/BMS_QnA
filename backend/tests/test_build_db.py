import sqlite3
from pathlib import Path

from app.build_db import main as build_main

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


def test_build_db_populates_all_tables(tmp_path):
    db_path = tmp_path / "test.db"
    stats = build_main(DATA_DIR, db_path)

    assert stats["criteria"] > 0
    assert stats["weight_tables"] > 0
    assert stats["defect_score"] > 0
    assert stats["text_docs"] > 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # 실제 데이터 사실 검증: 콘크리트 바닥판 2026, c등급 1방향균열 2개 기준(균열폭/균열률)
    rows = conn.execute(
        "SELECT criterion_raw FROM criteria WHERE year=2026 AND member='콘크리트 바닥판' "
        "AND subitem='1방향 균열' AND grade='c'"
    ).fetchall()
    assert {r["criterion_raw"] for r in rows} == {
        "균열폭 0.3㎜이상～0.5㎜미만",
        "균열률 2%이상～10% 미만",
    }

    # 실제 사실: 월류(여유고 조사)는 2026에만 존재, 2024엔 없음
    count_2026 = conn.execute(
        "SELECT COUNT(*) c FROM criteria WHERE year=2026 AND member='월류(여유고 조사)'"
    ).fetchone()["c"]
    count_2024 = conn.execute(
        "SELECT COUNT(*) c FROM criteria WHERE year=2024 AND member='월류(여유고 조사)'"
    ).fetchone()["c"]
    assert count_2026 > 0
    assert count_2024 == 0

    # 실제 사실: 표1.31 일반거더교 일반 형식의 가중치 합계는 117
    total = conn.execute(
        "SELECT SUM(weight) t FROM weight_tables WHERE year=2026 "
        "AND structure_type='거더교량 > 일반 거더교 > 일반'"
    ).fetchone()["t"]
    assert total == 117.0
