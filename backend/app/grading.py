"""부재 하나의 상태평가 등급을 판정한다.

정량 지표가 있으면 코드가 구간 대입으로 등급을 확정한다. 여러 정량 지표가
서로 다른 등급을 가리키면 더 나쁜(알파벳이 더 뒤인) 등급을 채택한다
(1.4절 본문 "정량적, 정성적 평가의 최젓값을 기준으로 산정" 원칙).
정성 지표만 있으면 절대 등급을 확정하지 않고 후보를 그대로 반환한다.
"""
from __future__ import annotations

import operator
import sqlite3

_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}


def grade_lookup(
    conn: sqlite3.Connection,
    member: str,
    item: str,
    subitem: str | None,
    measures: dict[str, float],
    year: int = 2026,
) -> dict:
    cur = conn.execute(
        "SELECT * FROM criteria WHERE year=? AND member=? AND item=? AND subitem=?",
        (year, member, item, subitem or ""),
    )
    rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        return {"status": "not_found"}

    quant_rows = [r for r in rows if r["criterion_type"] == "quant"]

    # Check if any quantitative criteria can be applied (i.e., we have measures for them)
    applicable_quant_rows = [r for r in quant_rows if r["parsed_field"] and r["parsed_field"] in measures]

    if applicable_quant_rows:
        matched = []
        for r in quant_rows:
            field = r["parsed_field"]
            value = measures.get(field)
            if value is None:
                continue
            ok = True
            if r["parsed_min"] is not None:
                ok = ok and _OPS[r["parsed_min_op"]](value, r["parsed_min"])
            if r["parsed_max"] is not None:
                ok = ok and _OPS[r["parsed_max_op"]](value, r["parsed_max"])
            if ok:
                matched.append({
                    "grade": r["grade"], "criterion_raw": r["criterion_raw"],
                    "table_no": r["table_no"], "page": r["page"],
                })
        if matched:
            worst = max(matched, key=lambda m: m["grade"])
            return {"status": "graded", "grade": worst["grade"], "evidence": matched}
        return {
            "status": "no_match",
            "available_fields": sorted({r["parsed_field"] for r in quant_rows if r["parsed_field"]}),
        }

    qual_rows = [r for r in rows if r["criterion_type"] == "qual"]
    if qual_rows:
        return {
            "status": "needs_judgment",
            "candidates": [
                {"grade": r["grade"], "criterion_raw": r["criterion_raw"], "table_no": r["table_no"], "page": r["page"]}
                for r in qual_rows
            ],
        }

    # If there are quantitative rows but no applicable measures, return no_match
    if quant_rows:
        return {
            "status": "no_match",
            "available_fields": sorted({r["parsed_field"] for r in quant_rows if r["parsed_field"]}),
        }

    return {"status": "not_found"}
