"""FastAPI 앱: grade/aggregate/compare/search 엔드포인트."""
from __future__ import annotations

import contextlib
import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.grading import grade_lookup
from app.aggregate import aggregate_structure_grade, aggregate_bridge_grade
from app.compare import compare_years
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


app = FastAPI(title="교량편 QnA API")

# 로컬 개발(vite dev, :5173)은 항상 허용. 프론트를 백엔드와 별도 오리진에 배포하는
# 경우에만 FRONTEND_ORIGIN 환경변수로 그 주소를 추가로 허용한다(같은 오리진에서
# 정적 파일로 서빙하는 기본 배포 방식에서는 이 값이 필요 없다).
_allowed_origins = ["http://localhost:5173"]
if os.environ.get("FRONTEND_ORIGIN"):
    _allowed_origins.append(os.environ["FRONTEND_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GradeRequest(BaseModel):
    member: str
    item: str
    subitem: str | None = None
    measures: dict[str, float]
    year: int = 2026


@app.post("/inspection/grade")
def api_grade(req: GradeRequest):
    with contextlib.closing(get_conn()) as conn:
        return grade_lookup(conn, req.member, req.item, req.subitem, req.measures, req.year)


class AggregateStructureRequest(BaseModel):
    year: int = 2026
    structure_type: str
    member_grades: dict[str, str]
    critical_defect_member: str | None = None


@app.post("/inspection/aggregate-structure")
def api_aggregate_structure(req: AggregateStructureRequest):
    try:
        with contextlib.closing(get_conn()) as conn:
            return aggregate_structure_grade(
                conn, req.year, req.structure_type, req.member_grades, req.critical_defect_member,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AggregateBridgeRequest(BaseModel):
    year: int = 2026
    structure_results: dict[str, dict]
    span_ratios: dict[str, float]
    critical_defect_structure: str | None = None


@app.post("/inspection/aggregate-bridge")
def api_aggregate_bridge(req: AggregateBridgeRequest):
    try:
        with contextlib.closing(get_conn()) as conn:
            return aggregate_bridge_grade(
                conn, req.year, req.structure_results, req.span_ratios, req.critical_defect_structure,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/inspection/schema")
def api_schema(year: int = 2026):
    with contextlib.closing(get_conn()) as conn:
        cur = conn.execute(
            "SELECT DISTINCT member, item, subitem FROM criteria WHERE year=? ORDER BY member, item, subitem",
            (year,),
        )
        return [dict(r) for r in cur.fetchall()]


@app.get("/inspection/fields")
def api_fields(member: str, item: str, subitem: str = "", year: int = 2026):
    with contextlib.closing(get_conn()) as conn:
        cur = conn.execute(
            "SELECT DISTINCT parsed_field, parsed_unit FROM criteria "
            "WHERE year=? AND member=? AND item=? AND subitem=? AND criterion_type='quant'",
            (year, member, item, subitem),
        )
        return [dict(r) for r in cur.fetchall()]


@app.get("/compare")
def api_compare(member: str, item: str, subitem: str = "", years: str = "2022,2023,2024,2026"):
    year_list = [int(y) for y in years.split(",")]
    with contextlib.closing(get_conn()) as conn:
        result = compare_years(conn, member, item, subitem, year_list)
    return {
        "by_year": {str(y): rows for y, rows in result["by_year"].items()},
        "changed_grades": {
            grade: {str(y): texts for y, texts in by_year.items()}
            for grade, by_year in result["changed_grades"].items()
        },
    }


@app.get("/search")
def api_search(q: str, section: str | None = None, year: int = 2026):
    return get_searcher(year).search(q, section)


from app.llm_config import load_config, build_llm
from app.llm_tools import run_chat


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
def api_chat(req: ChatRequest):
    llm = build_llm(load_config())
    answer = run_chat(llm, req.message)
    return {"answer": answer}


# 배포용: `npm run build`로 만든 프론트엔드 정적 파일을 같은 서버에서 서빙한다.
# 로컬 개발(vite dev, :5173)에서는 이 디렉터리가 없으므로 아무 것도 마운트하지 않는다
# (API 라우트들보다 뒤에서 "/"를 잡아야 위 엔드포인트들과 경로가 겹치지 않는다).
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
