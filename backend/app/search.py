"""text_docs(서술형 본문)에 대한 TF-IDF 코사인 유사도 검색.
표(criteria/weight_tables/defect_score)는 DB 질의로 정확히 계산하고,
이 모듈은 1.1~1.7절 서술형 본문에 대한 자유검색만 담당한다."""
from __future__ import annotations

import sqlite3

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class TextSearcher:
    def __init__(self, conn: sqlite3.Connection, year: int = 2026):
        self.year = year
        cur = conn.execute(
            "SELECT id, section, heading_path, paragraph, source_path FROM text_docs WHERE year=?",
            (year,),
        )
        self.rows = [dict(r) for r in cur.fetchall()]
        self.vectorizer = TfidfVectorizer(analyzer="char")
        self.matrix = self.vectorizer.fit_transform([r["paragraph"] for r in self.rows]) if self.rows else None

    def search(self, query: str, section: str | None = None, top_k: int = 5) -> list[dict]:
        if not self.rows:
            return []
        candidates = self.rows
        matrix = self.matrix
        if section:
            idx = [i for i, r in enumerate(self.rows) if r["section"] == section]
            if not idx:
                return []
            candidates = [self.rows[i] for i in idx]
            matrix = self.matrix[idx]

        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, matrix)[0]
        ranked = sims.argsort()[::-1][:top_k]
        # Use a minimum similarity threshold to filter out very low-scoring irrelevant results
        # (char analyzer can produce small scores from character overlap in unrelated documents)
        return [{**candidates[i], "score": float(sims[i])} for i in ranked if sims[i] >= 0.25]
