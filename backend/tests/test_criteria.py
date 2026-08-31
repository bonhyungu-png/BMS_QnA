from pathlib import Path
from app.parsing.criteria import parse_criterion_text, build_criteria_rows
from app.parsing.kv_blocks import parse_kv_file


def test_parses_range_with_unit():
    r = parse_criterion_text("균열폭 0.3㎜이상～0.5㎜미만")
    assert r is not None
    assert r.field == "균열폭"
    assert r.min_value == 0.3 and r.min_op == ">="
    assert r.max_value == 0.5 and r.max_op == "<"
    assert r.unit == "㎜"


def test_parses_percent_range_with_space_before_unit():
    r = parse_criterion_text("균열률 2%이상～10% 미만")
    assert r.field == "균열률"
    assert r.min_value == 2 and r.min_op == ">="
    assert r.max_value == 10 and r.max_op == "<"
    assert r.unit == "%"


def test_parses_lower_bound_only():
    r = parse_criterion_text("균열폭 1.0㎜이상")
    assert r.field == "균열폭"
    assert r.min_value == 1.0 and r.min_op == ">="
    assert r.max_value is None


def test_parses_upper_bound_only():
    r = parse_criterion_text("균열폭 0.1㎜미만")
    assert r.field == "균열폭"
    assert r.max_value == 0.1 and r.max_op == "<"
    assert r.min_value is None


def test_parses_safety_factor_range():
    r = parse_criterion_text("0.9 ≤ SF < 1 이나, 공용내하력이 설계하중보다 크게 평가된 경우")
    assert r.field == "SF"
    assert r.min_value == 0.9 and r.min_op == ">="
    assert r.max_value == 1 and r.max_op == "<"


def test_parses_safety_factor_gt():
    r = parse_criterion_text("SF > 1.0")
    assert r.field == "SF"
    assert r.min_value == 1.0 and r.min_op == ">"
    assert r.max_value is None


def test_fraction_denominator_is_not_mistaken_for_threshold():
    # "1/2 이상"의 2를 "2 이상"으로 잘못 읽으면 안 된다 — 실제 표1.22 교량받침 e등급 원문
    r = parse_criterion_text("받침이 밀착되지 않고 떠있는 부분이 전체면적의 1/2 이상")
    assert r is None  # 정성 항목으로 폴백


def test_pure_qualitative_text_returns_none():
    r = parse_criterion_text("부식으로 인한 철근의 단면감소가 심하여 바닥판의 안전성이 저하되는 경우")
    assert r is None


def test_none_and_dash_are_not_quant():
    assert parse_criterion_text("없음") is None
    assert parse_criterion_text("-") is None


def test_parses_range_separated_by_space_instead_of_tilde():
    r = parse_criterion_text("표면손상 면적 2% 이상 10% 미만")
    assert r is not None
    assert r.field == "표면손상 면적"
    assert r.min_value == 2 and r.min_op == ">="
    assert r.max_value == 10 and r.max_op == "<"
    assert r.unit == "%"


def test_parses_safety_factor_lt():
    r = parse_criterion_text("SF < 0.75")
    assert r is not None
    assert r.field == "SF"
    assert r.max_value == 0.75 and r.max_op == "<"
    assert r.min_value is None


FIXTURE = Path(__file__).parent / "fixtures" / "표1_11_콘크리트_바닥판.md"


def test_build_criteria_rows_from_real_table():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    rows = build_criteria_rows(parsed, year=2026, section="1.4 상태평가기준 및 방법", source_path=str(FIXTURE))

    b_rows = [r for r in rows if r["grade"] == "b" and r["subitem"] == "1방향 균열"]
    assert len(b_rows) == 2  # 균열폭 기준 + 균열률 기준, OR 관계로 행 분리
    assert {r["criterion_raw"] for r in b_rows} == {
        "균열폭 0.1㎜이상～0.3㎜미만",
        "균열률 2%미만",
    }
    assert all(r["criterion_type"] == "quant" for r in b_rows)
    assert all(r["member"] == "콘크리트 바닥판" for r in rows)

    e_철근부식 = next(
        r for r in rows if r["grade"] == "e" and r["subitem"] == "철근부식"
    )
    assert e_철근부식["criterion_type"] == "qual"
    assert e_철근부식["parsed_min"] is None
