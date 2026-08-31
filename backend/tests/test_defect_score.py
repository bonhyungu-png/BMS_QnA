from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.defect_score import parse_defect_score

FIXTURE = Path(__file__).parent / "fixtures" / "표1_33_결함도점수.md"


def test_parses_index_and_range_for_each_grade():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    rows = {r["grade"]: r for r in parse_defect_score(parsed, year=2026, source_path=str(FIXTURE))}

    assert rows["A"]["index_value"] == 0.10
    assert rows["A"]["range_min"] == 0.0 and rows["A"]["range_max"] == 0.13

    assert rows["E"]["index_value"] == 1.00
    assert rows["E"]["range_min"] == 0.79 and rows["E"]["range_max"] is None
