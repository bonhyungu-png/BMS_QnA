"""Streamlit 앱: 정밀안전점검·진단 교량편 QnA — 채팅 탭 + 점검표 탭.

React+FastAPI 버전(backend/app/main.py, frontend/)을 대체한다. HTTP 대신
backend/app의 함수들을 같은 프로세스 안에서 직접 호출한다."""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.aggregate import aggregate_structure_grade
from app.build_db import main as build_db_main
from app.conn import DB_PATH, get_conn
from app.grading import grade_lookup
from app.llm_config import build_llm, load_config
from app.llm_tools import run_chat

YEAR = 2026

# Streamlit Cloud의 Secrets 매니저에 등록된 값을 환경변수로 옮긴다 —
# llm_config.load_config()가 이미 BRIDGE_QNA_API_KEY 환경변수를 파일보다 우선 읽는다.
# 로컬 개발 환경에는 secrets.toml이 없는 게 정상이므로(파일 기반 api_key.txt를 쓰면 됨)
# 그 경우 StreamlitSecretNotFoundError를 조용히 무시한다.
try:
    if "BRIDGE_QNA_API_KEY" in st.secrets:
        os.environ.setdefault("BRIDGE_QNA_API_KEY", st.secrets["BRIDGE_QNA_API_KEY"])
        if st.secrets.get("BRIDGE_QNA_PROVIDER"):
            os.environ.setdefault("BRIDGE_QNA_PROVIDER", st.secrets["BRIDGE_QNA_PROVIDER"])
        if st.secrets.get("BRIDGE_QNA_MODEL"):
            os.environ.setdefault("BRIDGE_QNA_MODEL", st.secrets["BRIDGE_QNA_MODEL"])
except st.errors.StreamlitSecretNotFoundError:
    pass

st.set_page_config(page_title="정밀안전점검·진단 교량편 QnA")


@st.cache_resource
def ensure_db_built() -> str:
    db_path = Path(DB_PATH)
    if not db_path.exists():
        data_dir = ROOT / "data" / "안전점검진단_교량편"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        build_db_main(data_dir, db_path)
    return DB_PATH


@st.cache_data
def fetch_schema(year: int) -> list[dict]:
    with contextlib.closing(get_conn()) as conn:
        cur = conn.execute(
            "SELECT DISTINCT member, item, subitem FROM criteria WHERE year=? ORDER BY member, item, subitem",
            (year,),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_fields(member: str, item: str, subitem: str, year: int) -> list[dict]:
    with contextlib.closing(get_conn()) as conn:
        cur = conn.execute(
            "SELECT DISTINCT parsed_field, parsed_unit FROM criteria "
            "WHERE year=? AND member=? AND item=? AND subitem=? AND criterion_type='quant'",
            (year, member, item, subitem),
        )
        return [dict(r) for r in cur.fetchall()]


ensure_db_built()
st.title("정밀안전점검·진단 교량편 QnA")
tab_chat, tab_sheet = st.tabs(["채팅", "점검표"])

with tab_chat:
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for role, text in st.session_state.chat_history:
        st.chat_message(role).write(text)

    question = st.chat_input("질문을 입력하세요")
    if question:
        st.session_state.chat_history.append(("user", question))
        st.chat_message("user").write(question)
        with st.chat_message("assistant"):
            with st.spinner("답변 생성 중..."):
                try:
                    answer = run_chat(build_llm(load_config()), question)
                except Exception as e:  # noqa: BLE001 - 사용자에게 오류를 그대로 보여주는 게 목적
                    answer = f"오류: {e}"
            st.write(answer)
        st.session_state.chat_history.append(("assistant", answer))

with tab_sheet:
    if "rows" not in st.session_state:
        st.session_state.rows = []

    schema = fetch_schema(YEAR)
    members = sorted({row["member"] for row in schema})

    picked = st.selectbox(
        "부재 추가", options=[""] + members,
        format_func=lambda m: "+ 부재 추가" if m == "" else m,
    )
    if picked and st.button("추가"):
        first = next(r for r in schema if r["member"] == picked)
        st.session_state.rows.append({
            "member": first["member"], "item": first["item"], "subitem": first["subitem"],
            "fields": fetch_fields(first["member"], first["item"], first["subitem"], YEAR),
            "measures": {}, "result": None, "error": None,
        })

    for i, row in enumerate(st.session_state.rows):
        st.markdown(f"**{row['member']}** / {row['item']} / {row['subitem']}")
        for f in row["fields"]:
            label = f["parsed_field"] + (f" ({f['parsed_unit']})" if f["parsed_unit"] else "")
            row["measures"][f["parsed_field"]] = st.text_input(label, key=f"measure_{i}_{f['parsed_field']}")

        if st.button("등급 판정", key=f"grade_btn_{i}"):
            measures: dict[str, float] = {}
            for k, v in row["measures"].items():
                try:
                    measures[k] = float(v)
                except (TypeError, ValueError):
                    pass
            try:
                with contextlib.closing(get_conn()) as conn:
                    row["result"] = grade_lookup(conn, row["member"], row["item"], row["subitem"], measures, YEAR)
                row["error"] = None
            except Exception as e:  # noqa: BLE001
                row["error"] = str(e)
                row["result"] = None

        if row["error"]:
            st.error(row["error"])
        elif row["result"]:
            status = row["result"].get("status")
            if status == "graded":
                st.success(f"등급: {row['result']['grade']}")
            elif status == "needs_judgment":
                st.warning("정성 판단 필요 (후보 확인)")
            elif status == "no_match":
                st.info("구간 불일치")
            elif status == "not_found":
                st.info("일치하는 기준을 찾지 못했습니다")
        st.divider()

    st.subheader("전체 등급 계산")
    structure_type = st.text_input("구조형식", value="거더교량 > 일반 거더교 > 일반")
    if st.button("전체 등급 계산"):
        member_grades = {
            r["member"]: r["result"]["grade"]
            for r in st.session_state.rows
            if r["result"] and r["result"].get("grade")
        }
        try:
            with contextlib.closing(get_conn()) as conn:
                agg = aggregate_structure_grade(conn, YEAR, structure_type, member_grades)
            st.success(f"환산 결함도 점수: {agg['converted_score']:.4f} → 등급: {agg['grade']}")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
