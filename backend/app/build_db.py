"""data/안전점검진단_교량편 전체를 순회해 SQLite로 적재하는 CLI 진입점."""
from __future__ import annotations

import sys
from pathlib import Path

from app.db import init_db, insert_criteria, insert_defect_score, insert_text_docs, insert_weight
from app.parsing.kv_blocks import parse_kv_file
from app.parsing.criteria import build_criteria_rows
from app.parsing.weights import parse_weight_table
from app.parsing.defect_score import parse_defect_score
from app.parsing.text_docs import parse_text_file


def _classify_table_file(parsed: dict) -> str:
    blocks = parsed["blocks"]
    if not blocks:
        return "empty"
    first = blocks[0]
    if "등급" in first:
        return "criteria"
    label = (first.get("기준") or [None])[0]
    if label in ("결함도 지수", "결함도 범위"):
        return "defect_score"
    if "구분" in first and "결함도 평가항목" in first:
        return "weight"
    return "other"


def main(data_dir: Path, db_path: Path) -> dict:
    conn = init_db(str(db_path))
    stats = {"criteria": 0, "weight_tables": 0, "defect_score": 0, "text_docs": 0, "skipped": []}

    for section_dir in sorted(data_dir.iterdir()):
        if not section_dir.is_dir():
            continue
        section = section_dir.name

        table_dir = section_dir / "table"
        if table_dir.exists():
            for year_dir in sorted(table_dir.iterdir()):
                if not year_dir.is_dir():
                    continue
                year = int(year_dir.name)
                for md_file in sorted(year_dir.glob("*.md")):
                    parsed = parse_kv_file(md_file.read_text(encoding="utf-8"))
                    kind = _classify_table_file(parsed)
                    if kind == "criteria":
                        rows = build_criteria_rows(parsed, year, section, str(md_file))
                        if rows:
                            insert_criteria(conn, rows)
                            stats["criteria"] += len(rows)
                    elif kind == "defect_score":
                        rows = parse_defect_score(parsed, year, str(md_file))
                        insert_defect_score(conn, rows)
                        stats["defect_score"] += len(rows)
                    elif kind == "weight":
                        rows = parse_weight_table(parsed, year, str(md_file))
                        insert_weight(conn, rows)
                        stats["weight_tables"] += len(rows)
                    else:
                        stats["skipped"].append(str(md_file))

        text_dir = section_dir / "text"
        if text_dir.exists():
            for year_dir in sorted(text_dir.iterdir()):
                if not year_dir.is_dir():
                    continue
                year = int(year_dir.name)
                for md_file in sorted(year_dir.glob("*.md")):
                    parsed = parse_text_file(md_file.read_text(encoding="utf-8"))
                    rows = [
                        {
                            "year": year,
                            "section": section,
                            "heading_path": p["heading_path"],
                            "paragraph": p["content"],
                            "source_path": str(md_file),
                        }
                        for p in parsed["paragraphs"]
                    ]
                    if rows:
                        insert_text_docs(conn, rows)
                        stats["text_docs"] += len(rows)

    conn.close()
    return stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data" / "안전점검진단_교량편"
    db_path = Path(__file__).resolve().parent.parent / "data" / "bridge_qna.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    result = main(data_dir, db_path)
    print(f"criteria={result['criteria']} weight_tables={result['weight_tables']} "
          f"defect_score={result['defect_score']} text_docs={result['text_docs']} "
          f"skipped={len(result['skipped'])}개 파일")
