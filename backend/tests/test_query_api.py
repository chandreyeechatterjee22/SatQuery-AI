import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.router import router


@pytest.fixture
def client(upload_dir):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_query_ok(client, make_upload):
    uid = make_upload("single", [{"count": 4}])
    r = client.post("/api/query", json={"upload_id": uid, "question": "What is the CRS?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK" and "EPSG:32643" in body["answer"]
    assert set(body) == {"query_id", "upload_id", "question", "status", "answer", "confidence",
                         "evidence_images", "details", "trace"}


def test_query_unknown_upload_404(client):
    r = client.post("/api/query", json={"upload_id": "f" * 32, "question": "What changed?"})
    assert r.status_code == 404


@pytest.mark.parametrize("payload", [
    {"upload_id": "a" * 32, "question": ""},
    {"upload_id": "a" * 32, "question": "   "},
    {"upload_id": "a" * 32},
    {"question": "What changed?"},
    {"upload_id": "a" * 32, "question": "x" * 1001},
])
def test_query_bad_request_422(client, payload):
    assert client.post("/api/query", json=payload).status_code == 422


def test_evidence_preview_served(client, make_upload):
    uid = make_upload("single", [{"count": 4}])
    body = client.post("/api/query", json={"upload_id": uid, "question": "metadata"}).json()
    r = client.get(body["evidence_images"][0]["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_unknown_slot_404(client, make_upload):
    uid = make_upload("single", [{}])
    assert client.get(f"/api/uploads/{uid}/preview/2").status_code == 404
    assert client.get(f"/api/uploads/{'0' * 32}/preview/1").status_code == 404


def test_saved_result_json_served(client, make_upload):
    uid = make_upload("single", [{}])
    body = client.post("/api/query", json={"upload_id": uid, "question": "How many bands?"}).json()
    r = client.get(f"/api/uploads/{uid}/queries/{body['query_id']}/result.json")
    assert r.status_code == 200 and r.json()["query_id"] == body["query_id"]


@pytest.mark.parametrize("name", ["..%2Fmanifest.json", "RESULT.JSON", "result.txt", "missing.png"])
def test_evidence_path_is_locked_down(client, make_upload, name):
    uid = make_upload("single", [{}])
    body = client.post("/api/query", json={"upload_id": uid, "question": "How many bands?"}).json()
    assert client.get(f"/api/uploads/{uid}/queries/{body['query_id']}/{name}").status_code == 404


def test_tools_listing(client):
    tools = {t["name"]: t for t in client.get("/api/tools").json()["tools"]}
    assert tools["image_metadata"]["available"] is True
    assert tools["landcover_change"]["available"] is True
    assert tools["rs_vqa"]["available"] is False  # no weights in tests
    assert tools["optical_sar_mapper"]["params"]["classes"]["choices"] == ["water", "built_up"]


def test_main_app_mounts_agent_routes():
    import main

    paths = set(main.app.openapi()["paths"])
    assert {"/api/query", "/api/tools", "/api/uploads/{upload_id}/preview/{slot}"} <= paths
