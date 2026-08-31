"""표1.31/1.32(구조형식별 부재 가중치) 파서. 각 블록은 '구분'(상부/하부/받침/기타/재료시험)과
'결함도 평가항목'(바닥판/주형/...) 행 하나이며, 그 외 키는 구조형식 경로 -> 가중치 값이다."""
from __future__ import annotations

import re

_META_KEYS = {"heading", "구분", "결함도 평가항목", "출처"}
_WEIGHT_PATTERN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)")


def _resolve_defect_item(values: list) -> str | None:
    """'결함도 평가항목' 키는 정상 블록에서는 같은 값이 중복 기재되지만(예: '바닥판'/'바닥판'),
    2022~2024 표1.30/1.31의 콘크리트(탄산화/염화물) 블록에서는 서로 다른 두 값이 기재된다
    (예: '탄산화'/'상부', '탄산화'/'하부'). 후자는 두 값을 결합해 상부/하부를 구분할 수 있는
    라벨을 만든다; 값이 동일하거나 하나뿐이면 그대로 첫 값을 사용한다."""
    if not values:
        return None
    first = values[0]
    if len(values) > 1 and values[1] and values[1] != first:
        return f"{first}/{values[1]}"
    return first


def _parse_weight_value(raw: str) -> float | None:
    """가중치 원문 문자열을 float으로 변환한다. '-'는 값 없음(None),
    '2(4)' 같은 각주 표기는 괄호 앞 정수를 채택한다."""
    raw = raw.strip()
    if raw == "-":
        return None
    match = _WEIGHT_PATTERN.match(raw)
    if match:
        return float(match.group(1))
    return None


def parse_weight_table(parsed: dict, year: int, source_path: str) -> list[dict]:
    rows: list[dict] = []
    for block in parsed["blocks"]:
        category = (block.get("구분") or [None])[0]
        if category == "합계":
            continue
        defect_item = _resolve_defect_item(block.get("결함도 평가항목") or [None])
        for key, values in block.items():
            if key in _META_KEYS:
                continue
            # 일부 실제 데이터(라멘교 계열 열)는 같은 구조형식 키가 한 블록 내에서
            # 두 번 이상 기재되며, 서로 다른 가중치 값을 갖는다(원문 PDF의 서로 다른
            # 두 열이 동일한 텍스트로 추출된 것으로 추정). 원래의 구분 라벨을 복원할
            # 방법이 없으므로, 값을 잃지 않기 위해 2번째 이후 값은 키에 " (n)" 접미사를
            # 붙여 별도 행으로 남긴다. 1번째 값은 기존처럼 접미사 없는 원래 키를 쓴다.
            for idx, raw in enumerate(values):
                structure_type = key if idx == 0 else f"{key} ({idx + 1})"
                rows.append({
                    "year": year,
                    "category": category,
                    "defect_item": defect_item,
                    "structure_type": structure_type,
                    "weight": _parse_weight_value(raw),
                    "source_path": source_path,
                })
    return rows
