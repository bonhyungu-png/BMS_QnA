import sqlite3
from pathlib import Path

import pytest

from app.build_db import main as build_main
from app.search import TextSearcher

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_finds_relevant_paragraph_for_definition_query(conn):
    searcher = TextSearcher(conn, year=2026)
    results = searcher.search("특수교는 어떤 교량인가")
    assert len(results) > 0
    assert any("특수교" in r["paragraph"] for r in results)


def test_section_filter_narrows_results(conn):
    searcher = TextSearcher(conn, year=2026)
    results = searcher.search("보수 보강", section="1.7 보수·보강 방법")
    assert len(results) > 0
    assert all(r["section"] == "1.7 보수·보강 방법" for r in results)


def test_irrelevant_query_returns_empty_or_low_score(conn):
    searcher = TextSearcher(conn, year=2026)
    results = searcher.search("xyz불가능한검색어123")
    assert results == []
