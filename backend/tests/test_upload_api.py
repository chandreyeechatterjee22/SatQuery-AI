import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ingest.router import router
from tests.synthetic import WGS84, make_geotiff, make_png


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    target = tmp_path / "uploads"
    monkeypatch.setenv("UPLOAD_DIR", str(target))
    return target


@pytest.fixture
def client(upload_dir):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def src(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    return d


def tif(path, **kw):
    make_geotiff(path, **kw)
    return path.read_bytes()


def stored_ids(upload_dir):
    return [p.name for p in upload_dir.iterdir() if p.name != ".staging"] if upload_dir.exists() else []


def staging_is_empty(upload_dir):
    staging = upload_dir / ".staging"
    return not staging.exists() or not any(staging.iterdir())


def test_single_upload_accepted_and_stored(client, src, upload_dir):
    data = tif(src / "scene.tif", count=13)
    r = client.post("/api/uploads", data={"mode": "single"},
                    files={"file_1": ("scene.tif", data, "image/tiff")})

    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["status"] == "accepted" and body["mode"] == "single"
    assert len(body["upload_id"]) == 32
    f = body["files"][0]
    assert f["filename"] == "scene.tif" and f["stored_as"] == "file_1.tif"
    assert f["metadata"]["band_count"] == 13
    assert f["bands"]["sensor"] == "sentinel2"

    folder = upload_dir / body["upload_id"]
    assert (folder / "file_1.tif").read_bytes() == data
    assert (folder / "manifest.json").is_file()
    assert staging_is_empty(upload_dir)


def test_get_upload_returns_manifest(client, src):
    data = tif(src / "a.tif", count=4)
    created = client.post("/api/uploads", data={"mode": "single", "sensor_1": "cartosat2s"},
                          files={"file_1": ("a.tif", data)}).json()

    r = client.get(f"/api/uploads/{created['upload_id']}")
    assert r.status_code == 200
    assert r.json() == created
    assert r.json()["files"][0]["bands"]["sensor"] == "cartosat2s"


@pytest.mark.parametrize("upload_id", ["0" * 32, "not-an-id", "..%2F..%2Fetc"])
def test_get_unknown_upload_404(client, upload_id):
    assert client.get(f"/api/uploads/{upload_id}").status_code == 404


def test_optical_sar_upload(client, src):
    r = client.post("/api/uploads", data={"mode": "optical_sar"}, files={
        "file_1": ("opt.tif", tif(src / "o.tif", count=4)),
        "file_2": ("sar.tif", tif(src / "s.tif", count=2, dtype="float32")),
    })
    assert r.status_code == 201, r.json()
    body = r.json()
    assert [f["kind"] for f in body["files"]] == ["optical", "sar"]
    assert body["pair"]["same_crs"] is True


def test_bi_temporal_upload(client, src):
    r = client.post("/api/uploads",
                    data={"mode": "bi_temporal", "date_1": "2023-02-01", "date_2": "2025-02-01"},
                    files={"file_1": ("t1.tif", tif(src / "1.tif")),
                           "file_2": ("t2.tif", tif(src / "2.tif"))})
    assert r.status_code == 201, r.json()
    assert [f["date"] for f in r.json()["files"]] == ["2023-02-01", "2025-02-01"]


def test_rejection_returns_reasons_and_stores_nothing(client, src, upload_dir):
    r = client.post("/api/uploads", data={"mode": "optical_sar"}, files={
        "file_1": ("opt.tif", tif(src / "o.tif", count=4)),
        "file_2": ("sar.tif", tif(src / "s.tif", count=2, dtype="float32",
                                  crs=WGS84, origin=(77.5, 13.0), res=0.0001)),
    })
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "rejected"
    assert [x["code"] for x in body["reasons"]] == ["crs_mismatch"]
    assert stored_ids(upload_dir) == []
    assert staging_is_empty(upload_dir)


def test_wrong_file_count(client, src):
    r = client.post("/api/uploads", data={"mode": "bi_temporal", "date_1": "2023-01-01",
                                          "date_2": "2024-01-01"},
                    files={"file_1": ("t1.tif", tif(src / "1.tif"))})
    assert r.status_code == 422
    assert r.json()["reasons"][0]["code"] == "file_count"


def test_no_files(client):
    r = client.post("/api/uploads", data={"mode": "single"})
    assert r.status_code == 422
    assert r.json()["reasons"][0]["code"] == "file_count"


def test_png_needs_benchmark_mode(client, src):
    png = make_png(src / "a.png").read_bytes()
    r = client.post("/api/uploads", data={"mode": "single"}, files={"file_1": ("a.png", png)})
    assert r.status_code == 422
    assert r.json()["reasons"][0]["code"] == "image_requires_benchmark_mode"

    r = client.post("/api/uploads", data={"mode": "single", "benchmark_mode": "true"},
                    files={"file_1": ("a.png", png)})
    assert r.status_code == 201
    assert r.json()["benchmark_mode"] is True
    assert r.json()["files"][0]["stored_as"] == "file_1.png"


def test_file_too_large(client, src, upload_dir, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0.001")  # ~1 KB
    r = client.post("/api/uploads", data={"mode": "single"},
                    files={"file_1": ("big.tif", tif(src / "b.tif", width=64, height=64))})
    assert r.status_code == 413
    assert r.json()["reasons"][0]["code"] == "file_too_large"
    assert stored_ids(upload_dir) == []


def test_user_filename_never_used_as_path(client, src, upload_dir):
    r = client.post("/api/uploads", data={"mode": "single"},
                    files={"file_1": ("../../evil.tif", tif(src / "a.tif"))})
    assert r.status_code == 201
    folder = upload_dir / r.json()["upload_id"]
    assert sorted(p.name for p in folder.iterdir()) == ["file_1.tif", "manifest.json"]
    assert not (upload_dir.parent / "evil.tif").exists()


def test_main_app_mounts_upload_routes():
    import main

    paths = set(main.app.openapi()["paths"])
    assert {"/api/uploads", "/api/uploads/{upload_id}"} <= paths
    # The Earth Engine routes are still there.
    assert {"/api/sentinel", "/api/analyze", "/api/states"} <= paths


def test_band_roles_form_fields(client, src):
    r = client.post("/api/uploads",
                    data={"mode": "optical_sar", "band_roles_1": "blue,green,red,nir,swir1",
                          "band_roles_2": "vv,vh"},
                    files={"file_1": ("s2.tif", tif(src / "o.tif", count=5)),
                           "file_2": ("s1.tif", tif(src / "s.tif", count=2, dtype="float32"))})
    assert r.status_code == 201, r.json()
    files = r.json()["files"]
    assert files[0]["bands"]["source"] == "user_roles" and files[0]["bands"]["roles"]["swir1"] == 5
    assert files[1]["bands"]["roles"] == {"vv": 1, "vh": 2}
