from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.build_db import main as build_main
import app.main as main_module

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "안전점검진단_교량편"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    build_main(DATA_DIR, db_path)
    main_module.DB_PATH = str(db_path)
    main_module._searcher_cache.clear()
    return TestClient(main_module.app)


def test_grade_endpoint_returns_graded_result(client):
    resp = client.post("/inspection/grade", json={
        "member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열",
        "measures": {"균열폭": 0.35}, "year": 2026,
    })
    assert resp.status_code == 200
    assert resp.json()["grade"] == "c"


def test_schema_endpoint_lists_known_member(client):
    resp = client.get("/inspection/schema", params={"year": 2026})
    assert resp.status_code == 200
    members = {row["member"] for row in resp.json()}
    assert "콘크리트 바닥판" in members


def test_fields_endpoint_lists_quant_fields(client):
    resp = client.get("/inspection/fields", params={
        "member": "콘크리트 바닥판", "item": "균열1)", "subitem": "1방향 균열", "year": 2026,
    })
    assert resp.status_code == 200
    fields = {row["parsed_field"] for row in resp.json()}
    assert "균열폭" in fields
    assert "균열률" in fields


def test_compare_endpoint(client):
    resp = client.get("/compare", params={
        "member": "월류(여유고 조사)", "item": "여유고 검토1)", "years": "2024,2026",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_year"]["2024"] == []


def test_search_endpoint(client):
    resp = client.get("/search", params={"q": "특수교는 어떤 교량인가", "year": 2026})
    assert resp.status_code == 200
    assert len(resp.json()) > 0
