from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.weights import parse_weight_table

FIXTURE = Path(__file__).parent / "fixtures" / "표1_31_일반교량_가중치.md"


def test_parses_weight_matrix_and_skips_total_row():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    rows = parse_weight_table(parsed, year=2026, source_path=str(FIXTURE))

    assert not any(r["category"] == "합계" for r in rows)

    바닥판_일반거더 = next(
        r for r in rows
        if r["defect_item"] == "바닥판" and r["structure_type"] == "거더교량 > 일반 거더교 > 일반"
    )
    assert 바닥판_일반거더["weight"] == 18.0
    assert 바닥판_일반거더["category"] == "상부"

    바닥판_바닥판없음 = next(
        r for r in rows
        if r["defect_item"] == "바닥판" and r["structure_type"] == "거더교량 > 일반 거더교 > 바닥판 없음"
    )
    assert 바닥판_바닥판없음["weight"] is None  # 원문 '-'

    일반거더_전체가중치 = sum(
        r["weight"] for r in rows
        if r["structure_type"] == "거더교량 > 일반 거더교 > 일반" and r["weight"] is not None
    )
    assert 일반거더_전체가중치 == 117.0  # 표의 '합계' 행 값과 일치해야 함
