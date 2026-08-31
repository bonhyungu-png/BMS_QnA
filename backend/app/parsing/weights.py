"""표1.31/1.32(구조형식별 부재 가중치) 파서. 각 블록은 '구분'(상부/하부/받침/기타/재료시험)과
'결함도 평가항목'(바닥판/주형/...) 행 하나이며, 그 외 키는 구조형식 경로 -> 가중치 값이다."""
from __future__ import annotations

import re

_META_KEYS = {"heading", "구분", "결함도 평가항목", "출처"}
_WEIGHT_PATTERN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)")


def parse_weight_table(parsed: dict, year: int, source_path: str) -> list[dict]:
    rows: list[dict] = []
    for block in parsed["blocks"]:
        category = (block.get("구분") or [None])[0]
        if category == "합계":
            continue
        defect_item = (block.get("결함도 평가항목") or [None])[0]
        for key, values in block.items():
            if key in _META_KEYS:
                continue
            raw = values[0].strip()
            if raw == "-":
                weight = None
            else:
                match = _WEIGHT_PATTERN.match(raw)
                if match:
                    weight = float(match.group(1))
                else:
                    weight = None
            rows.append({
                "year": year,
                "category": category,
                "defect_item": defect_item,
                "structure_type": key,
                "weight": weight,
                "source_path": source_path,
            })
    return rows
