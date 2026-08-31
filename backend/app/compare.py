"""(부재, 평가항목, 세부항목) 키로 연도별 기준을 비교한다.
표 번호는 연도마다 밀리므로(예: 표1.34->1.35~37) 표 번호가 아니라 이 키로 매칭한다."""
from __future__ import annotations

import sqlite3


def compare_years(
    conn: sqlite3.Connection,
    member: str,
    item: str,
    subitem: str | None,
    years: list[int],
) -> dict:
    by_year: dict[int, list[dict]] = {}
    for year in years:
        cur = conn.execute(
            "SELECT grade, criterion_raw, table_no, page FROM criteria "
            "WHERE year=? AND member=? AND item=? AND subitem=? ORDER BY grade, criterion_raw",
            (year, member, item, subitem or ""),
        )
        by_year[year] = [dict(r) for r in cur.fetchall()]

    all_grades = sorted({row["grade"] for rows in by_year.values() for row in rows})
    changed_grades: dict[str, dict[int, list[str]]] = {}
    for grade in all_grades:
        texts_by_year = {
            year: sorted(r["criterion_raw"] for r in rows if r["grade"] == grade)
            for year, rows in by_year.items()
        }
        distinct = {tuple(v) for v in texts_by_year.values()}
        if len(distinct) > 1:
            changed_grades[grade] = texts_by_year

    return {"by_year": by_year, "changed_grades": changed_grades}
