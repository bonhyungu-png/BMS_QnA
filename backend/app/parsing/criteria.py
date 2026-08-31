"""상태평가/안전성평가 기준(criteria) 표를 정규화된 행으로 변환한다.

기준 문장은 두 갈래다:
  - 정량(quant): "균열폭 0.3㎜이상～0.5㎜미만", "SF > 1.0" 처럼 숫자 구간이 있는 문장.
  - 정성(qual): "펀칭파괴 발생 가능성 있음"처럼 점검자 판단이 필요한 서술.
1.4절 본문("정량적 평가와 정성적 평가를 동시에 수행하며 최젓값을 기준으로 산정")에 따라
정량은 코드가 확정하고, 정성은 절대 자동 확정하지 않는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedCriterion:
    field: str | None
    min_value: float | None
    min_op: str | None
    max_value: float | None
    max_op: str | None
    unit: str | None


_UNIT = r"㎜|mm|%|kg/m3|kg|kN|m3"
_NUM = r"(?<!/)[0-9]+(?:\.[0-9]+)?"

_RANGE_PATTERN = re.compile(
    rf"(?P<min>{_NUM})\s*(?P<unit1>{_UNIT})?\s*이상\s*[～~]\s*"
    rf"(?P<max>{_NUM})\s*(?P<unit2>{_UNIT})?\s*미만"
)
_GE_PATTERN = re.compile(rf"(?P<val>{_NUM})\s*(?P<unit>{_UNIT})?\s*이상(?!\s*[～~])")
_LT_PATTERN = re.compile(rf"(?P<val>{_NUM})\s*(?P<unit>{_UNIT})?\s*미만")
_FIELD_PREFIX = re.compile(r"^([^\d]+?)\s*[0-9]")

_SF_RANGE_PATTERN = re.compile(
    rf"(?P<min>{_NUM})\s*(?P<minop>[≤<])\s*SF\s*(?P<maxop><)\s*(?P<max>{_NUM})"
)
_SF_CMP_PATTERN = re.compile(rf"SF\s*(?P<op>[>≥])\s*(?P<val>{_NUM})")
_SF_OP_MAP = {"≤": ">=", "≥": ">=", "<": "<", ">": ">"}


def parse_criterion_text(text: str) -> ParsedCriterion | None:
    text = text.strip()
    if text in ("", "없음", "-"):
        return None

    m = _SF_RANGE_PATTERN.search(text)
    if m:
        return ParsedCriterion(
            field="SF",
            min_value=float(m.group("min")),
            min_op=_SF_OP_MAP[m.group("minop")],
            max_value=float(m.group("max")),
            max_op="<",
            unit=None,
        )

    m = _SF_CMP_PATTERN.search(text)
    if m:
        return ParsedCriterion(
            field="SF",
            min_value=float(m.group("val")),
            min_op=_SF_OP_MAP[m.group("op")],
            max_value=None,
            max_op=None,
            unit=None,
        )

    field_match = _FIELD_PREFIX.match(text)
    field = field_match.group(1).strip() if field_match else None

    m = _RANGE_PATTERN.search(text)
    if m:
        unit = m.group("unit1") or m.group("unit2")
        return ParsedCriterion(field, float(m.group("min")), ">=", float(m.group("max")), "<", unit)

    m = _GE_PATTERN.search(text)
    if m:
        return ParsedCriterion(field, float(m.group("val")), ">=", None, None, m.group("unit"))

    m = _LT_PATTERN.search(text)
    if m:
        return ParsedCriterion(field, None, None, float(m.group("val")), "<", m.group("unit"))

    return None


def classify_criterion(text: str) -> str:
    text = text.strip()
    if text in ("", "없음", "-"):
        return "none"
    return "quant" if parse_criterion_text(text) is not None else "qual"


def build_criteria_rows(parsed: dict, year: int, section: str, source_path: str) -> list[dict]:
    meta = parsed["meta"]
    table_no = meta.get("표")
    table_title = meta.get("title")
    page_raw = meta.get("면")
    page = int(page_raw) if page_raw and page_raw.isdigit() else None

    rows: list[dict] = []
    for block in parsed["blocks"]:
        member = (block.get("부재") or [meta.get("부재")])[0]
        item = (block.get("평가항목") or [None])[0]
        subitem = (block.get("세부항목") or [""])[0]
        grade = (block.get("등급") or [None])[0]
        for raw_text in block.get("기준", []):
            criterion_type = classify_criterion(raw_text)
            parsed_criterion = parse_criterion_text(raw_text) if criterion_type == "quant" else None
            rows.append({
                "year": year,
                "section": section,
                "table_no": table_no,
                "table_title": table_title,
                "member": member,
                "item": item,
                "subitem": subitem,
                "grade": grade,
                "criterion_raw": raw_text,
                "criterion_type": criterion_type,
                "parsed_field": parsed_criterion.field if parsed_criterion else None,
                "parsed_min": parsed_criterion.min_value if parsed_criterion else None,
                "parsed_min_op": parsed_criterion.min_op if parsed_criterion else None,
                "parsed_max": parsed_criterion.max_value if parsed_criterion else None,
                "parsed_max_op": parsed_criterion.max_op if parsed_criterion else None,
                "parsed_unit": parsed_criterion.unit if parsed_criterion else None,
                "page": page,
                "source_path": source_path,
            })
    return rows
