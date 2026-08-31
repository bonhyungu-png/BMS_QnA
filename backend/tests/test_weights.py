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


def test_defect_item_disambiguates_concrete_upper_lower_blocks():
    # 2022~2024 표1.30/1.31의 콘크리트(탄산화) 블록은 '결함도 평가항목'이
    # ["탄산화", "상부"]처럼 서로 다른 두 값으로 중복 기재된다. 상부/하부를
    # 구분하지 못하면 같은 (year, defect_item, structure_type) 조합에 두 행이
    # 충돌해서 하나가 사실상 사라진다 -- defect_item에 두 값을 모두 반영해야 한다.
    fixture_2024 = Path(__file__).parent / "fixtures" / "표1_30_2024_각주가중치.md"
    parsed = parse_kv_file(fixture_2024.read_text(encoding="utf-8"))
    rows = parse_weight_table(parsed, year=2024, source_path=str(fixture_2024))

    defect_items = {r["defect_item"] for r in rows}
    assert "탄산화/상부" in defect_items
    assert "탄산화/하부" in defect_items

    upper_row = next(
        r for r in rows
        if r["defect_item"] == "탄산화/상부" and r["structure_type"] == "슬래브 교량"
    )
    assert upper_row["weight"] == 2.0

    lower_row = next(
        r for r in rows
        if r["defect_item"] == "탄산화/하부" and r["structure_type"] == "슬래브 교량"
    )
    assert lower_row["weight"] == 2.0

    # 일반 블록(바닥판 등)은 '결함도 평가항목'이 하나만 기재(중복 없음)되므로
    # 기존처럼 단일 값만 사용해야 한다(회귀 없음 확인).
    fixture_2026 = Path(__file__).parent / "fixtures" / "표1_31_일반교량_가중치.md"
    parsed_2026 = parse_kv_file(fixture_2026.read_text(encoding="utf-8"))
    rows_2026 = parse_weight_table(parsed_2026, year=2026, source_path=str(fixture_2026))
    defect_items_2026 = {r["defect_item"] for r in rows_2026}
    assert "바닥판" in defect_items_2026
    assert "바닥판/바닥판" not in defect_items_2026
