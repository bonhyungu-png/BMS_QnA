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


def test_parses_weight_with_parenthetical_footnote_suffix():
    # 2022~2024년 표1.30/1.31 재료시험(탄산화/염화물) 행은 "2(4)", "4(7)" 형태.
    # 괄호 앞 정수를 가중치로 채택하고 괄호값은 이 범위에서 파싱하지 않는다.
    fixture_2024 = Path(__file__).parent / "fixtures" / "표1_30_2024_각주가중치.md"
    parsed = parse_kv_file(fixture_2024.read_text(encoding="utf-8"))
    rows = parse_weight_table(parsed, year=2024, source_path=str(fixture_2024))

    # 슬래브 교량: 2(4) → 2.0
    slab_row = next(r for r in rows if r["structure_type"] == "슬래브 교량")
    assert slab_row["weight"] == 2.0

    # 거더교량 > 일반 거더교 > 바닥판 없음: - → None
    none_row = next(
        r for r in rows
        if r["structure_type"] == "거더교량 > 일반 거더교 > 바닥판 없음"
    )
    assert none_row["weight"] is None

    # 라멘교 > 거더 없음: 4(7) → 4.0
    ramen_row = next(r for r in rows if r["structure_type"] == "라멘교 > 거더 없음")
    assert ramen_row["weight"] == 4.0
