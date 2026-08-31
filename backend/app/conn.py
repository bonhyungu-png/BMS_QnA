"""DB 커넥션/검색기 생성 헬퍼. Streamlit 앱과 llm_tools.py가 공유해서 쓴다."""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from app.search import TextSearcher

DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "bridge_qna.db")
_searcher_cache: dict[int, TextSearcher] = {}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_searcher(year: int) -> TextSearcher:
    if year not in _searcher_cache:
        with contextlib.closing(get_conn()) as conn:
            _searcher_cache[year] = TextSearcher(conn, year=year)
    return _searcher_cache[year]
