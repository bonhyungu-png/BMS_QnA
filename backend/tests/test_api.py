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


def test_aggregate_structure_unknown_structure_type_returns_400(client):
    """aggregate_structure_grade raises ValueError on unknown structure_type -> HTTP 400"""
    resp = client.post("/inspection/aggregate-structure", json={
        "year": 2026,
        "structure_type": "unknown_type_that_does_not_exist",
        "member_grades": {"콘크리트 바닥판": "a"},
    })
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    # Verify it's a ValueError-derived error (contains error message, not 500 exception)
    assert isinstance(body["detail"], str)
    assert len(body["detail"]) > 0


def test_aggregate_bridge_missing_structure_result_returns_400(client):
    """aggregate_bridge_grade raises ValueError when span_ratios key missing from structure_results -> HTTP 400"""
    resp = client.post("/inspection/aggregate-bridge", json={
        "year": 2026,
        "structure_results": {
            "main": {"converted_score": 2.5, "grade": "a"}
        },
        "span_ratios": {
            "main": 0.8,
            "ramp": 0.2  # 'ramp' not in structure_results
        },
    })
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    assert "structure_results" in body["detail"]


def test_aggregate_bridge_missing_converted_score_returns_400(client):
    """aggregate_bridge_grade raises ValueError when converted_score missing -> HTTP 400"""
    resp = client.post("/inspection/aggregate-bridge", json={
        "year": 2026,
        "structure_results": {
            "main": {"grade": "a"}  # missing 'converted_score'
        },
        "span_ratios": {
            "main": 1.0
        },
    })
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    assert "converted_score" in body["detail"]


def test_cors_headers_present_on_request_from_vite_dev_server(client):
    """CORS headers are present when request includes Origin: http://localhost:5173"""
    resp = client.get("/inspection/schema", params={"year": 2026}, headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
