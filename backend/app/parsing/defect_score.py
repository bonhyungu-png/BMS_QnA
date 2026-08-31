"""표1.33(결함도 점수 범위에 따른 기준) 파서.
블록 두 개('결함도 지수', '결함도 범위')를 등급(A~E)별 한 행으로 합친다."""
from __future__ import annotations

import re

_GRADES = ("A", "B", "C", "D", "E")
_RANGE_BOTH = re.compile(r"^([0-9.]+)≤X＜([0-9.]+)$")
_RANGE_LOWER_ONLY = re.compile(r"^([0-9.]+)≤X$")


def _parse_range(text: str) -> tuple[float, float | None]:
    m = _RANGE_BOTH.match(text.strip())
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _RANGE_LOWER_ONLY.match(text.strip())
    if m:
        return float(m.group(1)), None
    raise ValueError(f"결함도 범위 문자열을 해석할 수 없습니다: {text!r}")


def parse_defect_score(parsed: dict, year: int, source_path: str) -> list[dict]:
    index_values: dict[str, float] = {}
    ranges: dict[str, tuple[float, float | None]] = {}

    for block in parsed["blocks"]:
        label = (block.get("기준") or [None])[0]
        if label == "결함도 지수":
            for g in _GRADES:
                if g in block:
                    index_values[g] = float(block[g][0])
        elif label == "결함도 범위":
            for g in _GRADES:
                if g in block:
                    ranges[g] = _parse_range(block[g][0])

    rows = []
    for g in _GRADES:
        lo, hi = ranges.get(g, (None, None))
        rows.append({
            "year": year,
            "grade": g,
            "index_value": index_values.get(g),
            "range_min": lo,
            "range_max": hi,
            "source_path": source_path,
        })
    return rows
