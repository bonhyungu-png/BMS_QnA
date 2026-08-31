from pathlib import Path
from app.parsing.text_docs import parse_text_file

FIXTURE = Path(__file__).parent / "fixtures" / "1_1_관리일반.md"


def test_parses_meta():
    parsed = parse_text_file(FIXTURE.read_text(encoding="utf-8"))
    assert parsed["meta"]["title"] == "1.1 관리일반"
    assert parsed["meta"]["절"] == "1.1"
    assert parsed["meta"]["판본"] == "안전점검진단_교량@2026"


def test_paragraphs_are_grouped_by_heading_path():
    parsed = parse_text_file(FIXTURE.read_text(encoding="utf-8"))
    paragraphs = parsed["paragraphs"]

    적용범위_문단 = [p for p in paragraphs if p["heading_path"] == "1.1.1 적용 범위"]
    assert len(적용범위_문단) >= 2
    assert any("도로교량과 철도교량에 적용" in p["content"] for p in 적용범위_문단)

    용어정의_문단 = [p for p in paragraphs if p["heading_path"] == "1.1.2 용어 정의"]
    assert any("특수교(特殊橋)" in p["content"] for p in 용어정의_문단)


def test_table_reference_lines_are_skipped():
    parsed = parse_text_file(FIXTURE.read_text(encoding="utf-8"))
    assert not any("표참조" in p["content"] for p in parsed["paragraphs"])
