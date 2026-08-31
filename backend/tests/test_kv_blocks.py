from pathlib import Path
from app.parsing.kv_blocks import parse_kv_file

FIXTURE = Path(__file__).parent / "fixtures" / "표1_11_콘크리트_바닥판.md"


def test_parses_meta_header():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    meta = parsed["meta"]
    assert meta["title"] == "[표 1.11] 콘크리트 바닥판 상태평가기준"
    assert meta["절"] == "1.4 상태평가기준 및 방법"
    assert meta["표"] == "1.11"
    assert meta["면"] == "29"
    assert meta["부재"] == "콘크리트 바닥판"
    assert meta["평가항목"] == [
        "균열1) > 1방향 균열",
        "균열1) > 2방향 균열",
        "열화 및 손상 > 누수 및 백태",
        "열화 및 손상 > 표면손상",
        "열화 및 손상 > 철근부식",
    ]


def test_parses_blocks_with_repeated_keys():
    parsed = parse_kv_file(FIXTURE.read_text(encoding="utf-8"))
    blocks = parsed["blocks"]
    assert len(blocks) == 25  # 5항목 x 5등급(a~e) = 25개
    b_1방향 = next(
        b for b in blocks
        if b.get("등급") == ["b"] and b.get("세부항목") == ["1방향 균열"]
    )
    assert b_1방향["기준"] == [
        "균열폭 0.1㎜이상～0.3㎜미만",
        "균열률 2%미만",
    ]
    assert b_1방향["출처"] == ["[표 1.11] 안전점검진단_교량@2026 29면"]
