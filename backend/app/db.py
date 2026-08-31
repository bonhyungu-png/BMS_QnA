"""SQLite 스키마 생성 및 삽입 헬퍼."""
from __future__ import annotations

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS criteria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  section TEXT NOT NULL,
  table_no TEXT,
  table_title TEXT,
  member TEXT NOT NULL,
  item TEXT NOT NULL,
  subitem TEXT,
  grade TEXT NOT NULL,
  criterion_raw TEXT NOT NULL,
  criterion_type TEXT NOT NULL,
  parsed_field TEXT,
  parsed_min REAL,
  parsed_min_op TEXT,
  parsed_max REAL,
  parsed_max_op TEXT,
  parsed_unit TEXT,
  page INTEGER,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_criteria_lookup ON criteria (year, member, item, subitem);

CREATE TABLE IF NOT EXISTS weight_tables (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  category TEXT,
  defect_item TEXT NOT NULL,
  structure_type TEXT NOT NULL,
  weight REAL,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_weight_lookup ON weight_tables (year, defect_item, structure_type);

CREATE TABLE IF NOT EXISTS defect_score (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  grade TEXT NOT NULL,
  index_value REAL,
  range_min REAL,
  range_max REAL,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_defect_score_lookup ON defect_score (year, grade);

CREATE TABLE IF NOT EXISTS text_docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  year INTEGER NOT NULL,
  section TEXT,
  heading_path TEXT,
  paragraph TEXT NOT NULL,
  source_path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_text_docs_lookup ON text_docs (year, section);
"""


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def insert_criteria(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO criteria
           (year, section, table_no, table_title, member, item, subitem, grade,
            criterion_raw, criterion_type, parsed_field, parsed_min, parsed_min_op,
            parsed_max, parsed_max_op, parsed_unit, page, source_path)
           VALUES (:year, :section, :table_no, :table_title, :member, :item, :subitem, :grade,
                   :criterion_raw, :criterion_type, :parsed_field, :parsed_min, :parsed_min_op,
                   :parsed_max, :parsed_max_op, :parsed_unit, :page, :source_path)""",
        rows,
    )
    conn.commit()


def insert_weight(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO weight_tables (year, category, defect_item, structure_type, weight, source_path)
           VALUES (:year, :category, :defect_item, :structure_type, :weight, :source_path)""",
        rows,
    )
    conn.commit()


def insert_defect_score(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO defect_score (year, grade, index_value, range_min, range_max, source_path)
           VALUES (:year, :grade, :index_value, :range_min, :range_max, :source_path)""",
        rows,
    )
    conn.commit()


def insert_text_docs(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        """INSERT INTO text_docs (year, section, heading_path, paragraph, source_path)
           VALUES (:year, :section, :heading_path, :paragraph, :source_path)""",
        rows,
    )
    conn.commit()
