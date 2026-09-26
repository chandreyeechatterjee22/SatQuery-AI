"""Fetch from Earth Engine, fully offline: Earth Engine is replaced by fakes that record the export
request and serve a synthetic GeoTIFF on exactly the requested grid."""
import io
import socket

import numpy as np
import pytest
import rasterio
from affine import Affine
from fastapi import FastAPI
from fastapi.testclient import TestClient

import gee_fetch
from agent.controller import run_query
from ingest.gee_router import router

BELLANDUR = [77.640, 12.915, 77.680, 12.945]


class FakeImage:
    registry = {}

    def __init__(self, bands, dtype, value):
        self.bands, self.dtype, self.value = bands, dtype, value
        self.params = None

    def getDownloadURL(self, params):
        self.params = params
        url = f"fake://{id(self)}"
        FakeImage.registry[url] = self
        return url

    def geotiff_bytes(self):
        w, h = map(int, self.params["dimensions"].split("x"))
        a, b, c, d, e, f = self.params["crs_transform"]
        data = np.full((self.bands, h, w), self.value, dtype=self.dtype)
        data[:, : h // 4] = self.value * (2 if self.dtype == "uint16" else 1.5)  # some structure
        buf = io.BytesIO()
        with rasterio.MemoryFile() as mem:
            with mem.open(driver="GTiff", width=w, height=h, count=self.bands, dtype=self.dtype,
                          crs=self.params["crs"], transform=Affine(a, b, c, d, e, f)) as dst:
                dst.write(data)
            buf.write(mem.read())
        return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_ee(monkeypatch, upload_dir):
    calls = {"s2": [], "s1": []}
    counts = {"s2": 5, "s1": 7}

    def s2(aoi, start, end):
        calls["s2"].append((start, end))
        return FakeImage(6, "uint16", 1500), counts["s2"]

    def s1(aoi, start, end):
        calls["s1"].append((start, end))
        return FakeImage(2, "float32", -12.0), counts["s1"]

    monkeypatch.setattr(gee_fetch, "_status", {"configured": True, "reason": None, "detail": None})
    monkeypatch.setattr(gee_fetch, "aoi_geometry", lambda bbox: ("aoi", tuple(bbox)))
    monkeypatch.setattr(gee_fetch, "s2_composite", s2)
    monkeypatch.setattr(gee_fetch, "s1_composite", s1)
    monkeypatch.setattr(gee_fetch.urllib.request, "urlopen",
                        lambda url, timeout: FakeResponse(FakeImage.registry[url].geotiff_bytes()))
    return {"calls": calls, "counts": counts}


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# --- grid and area -------------------------------------------------------------------------

def test_grid_is_utm_10m_and_snapped():
    g = gee_fetch.grid_for_bbox(BELLANDUR)
    assert g["crs"] == "EPSG:32643" and g["scale"] == 10
    a, b, c, d, e, f = g["crs_transform"]
    assert (a, b, d, e) == (10, 0, 0, -10) and c % 10 == 0 and f % 10 == 0
    w, h = map(int, g["dimensions"].split("x"))
    assert 430 <= w <= 440 and 330 <= h <= 340   # ~4.3 x 3.3 km


def test_utm_zone_south_and_west():
    assert gee_fetch.utm_epsg(-47.9, -15.8) == "EPSG:32723"
    assert gee_fetch.utm_epsg(77.6, 12.9) == "EPSG:32643"


@pytest.mark.parametrize("bbox, fragment", [
    ([77.5, 12.9, 77.7, 13.0], "the maximum is 10 x 10 km"),       # ~21.7 x 11 km
    ([77.6, 12.9, 77.5, 13.0], "not a valid"),
    ([77.6, 12.9], "must be [west, south, east, north]"),
])
def test_area_checks(bbox, fragment):
    with pytest.raises(gee_fetch.FetchError, match=fragment.replace("[", r"\[")):
        gee_fetch.check_bbox(bbox)


def test_10km_box_is_allowed():
    lat = 12.9
    dlon = 10 / (111.32 * np.cos(np.radians(lat))) * 0.999
    gee_fetch.check_bbox([77.5, lat, 77.5 + dlon, lat + 0.0898])


def test_area_limit_via_api(client, fake_ee):
    r = client.post("/api/gee/fetch", json={"mode": "single", "bbox": [77.5, 12.9, 77.7, 13.0],
                                            "date_ranges": [["2024-01-01", "2024-03-31"]]})
    assert r.status_code == 422 and "maximum is 10 x 10 km" in r.json()["detail"]
    assert fake_ee["calls"]["s2"] == []   # nothing fetched


# --- fetch per mode -----------------------------------------------------------------------------

def test_optical_sar_fetch_shares_one_grid_and_answers(client, fake_ee):
    r = client.post("/api/gee/fetch", json={"mode": "optical_sar", "bbox": BELLANDUR,
                                            "date_ranges": [["2024-01-01", "2024-03-31"]]})
    assert r.status_code == 201, r.json()
    m = r.json()
    params = [img.params for img in FakeImage.registry.values()][-2:]
    assert params[0] == params[1]                                  # identical crs/transform/dimensions
    assert m["pair"]["same_crs"] and m["pair"]["overlap_fraction"] == 1.0 and m["pair"]["same_resolution"]
    assert m["files"][0]["bands"]["roles"] == {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "swir2": 6}
    assert m["files"][1]["bands"]["roles"] == {"vv": 1, "vh": 2}
    src = m["source"]
    assert src["provider"] == "Google Earth Engine" and src["crs"] == "EPSG:32643" and src["scale_m"] == 10
    assert src["products"][0]["collection"] == ["COPERNICUS/S2_SR_HARMONIZED", "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"]
    assert src["products"][1]["collection"] == ["COPERNICUS/S1_GRD"]
    assert src["products"][1]["bands"] == ["VV", "VH"] and src["products"][0]["scenes"] == 5
    assert src["products"][0]["date_range"] == ["2024-01-01", "2024-03-31"]

    res = run_query(m["upload_id"], "Where is the water?")
    assert res["status"] == "OK"
    assert res["trace"]["source"]["provider"] == "Google Earth Engine"


def test_bi_temporal_fetch_two_ranges_same_grid(client, fake_ee):
    r = client.post("/api/gee/fetch", json={"mode": "bi_temporal", "bbox": BELLANDUR,
                                            "date_ranges": [["2021-01-01", "2021-03-31"], ["2025-01-01", "2025-03-31"]]})
    assert r.status_code == 201, r.json()
    m = r.json()
    assert fake_ee["calls"]["s2"] == [("2021-01-01", "2021-03-31"), ("2025-01-01", "2025-03-31")]
    assert [f["date"] for f in m["files"]] == ["2021-02-14", "2025-02-14"]
    assert m["pair"]["overlap_fraction"] == 1.0


def test_single_fetch(client, fake_ee):
    r = client.post("/api/gee/fetch", json={"mode": "single", "bbox": BELLANDUR,
                                            "date_ranges": [["2024-01-01", "2024-03-31"]]})
    assert r.status_code == 201 and len(r.json()["files"]) == 1
    assert fake_ee["calls"]["s1"] == []


# --- errors ----------------------------------------------------------------------------------------

def test_no_images_suggests_widening(client, fake_ee):
    fake_ee["counts"]["s1"] = 0
    r = client.post("/api/gee/fetch", json={"mode": "optical_sar", "bbox": BELLANDUR,
                                            "date_ranges": [["2024-01-01", "2024-01-05"]]})
    assert r.status_code == 422
    assert "No Sentinel-1 GRD images" in r.json()["detail"] and "Widen the date range" in r.json()["detail"]


def test_timeout(client, fake_ee, monkeypatch):
    def slow(url, timeout):
        raise socket.timeout("timed out")
    monkeypatch.setattr(gee_fetch.urllib.request, "urlopen", slow)
    r = client.post("/api/gee/fetch", json={"mode": "single", "bbox": BELLANDUR,
                                            "date_ranges": [["2024-01-01", "2024-03-31"]]})
    assert r.status_code == 504 and "timed out" in r.json()["detail"]


@pytest.mark.parametrize("ranges, fragment", [
    ([["2024-03-01", "2024-01-01"]], "start must be before the end"),
    ([["2099-01-01", "2099-03-01"]], "in the future"),
    ([["01/01/2024", "2024-03-01"]], "YYYY-MM-DD"),
])
def test_bad_date_ranges(client, fake_ee, ranges, fragment):
    r = client.post("/api/gee/fetch", json={"mode": "single", "bbox": BELLANDUR, "date_ranges": ranges})
    assert r.status_code == 422 and fragment in r.json()["detail"]


def test_bi_temporal_needs_two_ranges(client, fake_ee):
    r = client.post("/api/gee/fetch", json={"mode": "bi_temporal", "bbox": BELLANDUR,
                                            "date_ranges": [["2021-01-01", "2021-03-31"]]})
    assert r.status_code == 422 and "two date ranges" in r.json()["detail"]


# --- no credentials fallback -------------------------------------------------------------------

def test_no_credentials(client, monkeypatch, upload_dir):
    import gee_service

    def boom():
        raise RuntimeError("Please authorize access to your Earth Engine account")
    monkeypatch.setattr(gee_fetch, "_status", None)
    monkeypatch.setattr(gee_service, "initialize_gee", boom)
    s = client.get("/api/gee/status").json()
    assert s["configured"] is False and s["max_side_km"] == 10
    assert s["reason"] == "Earth Engine not configured — use samples/ or upload GeoTIFFs."
    assert "Please authorize" in s["detail"]
    r = client.post("/api/gee/fetch", json={"mode": "single", "bbox": BELLANDUR,
                                            "date_ranges": [["2024-01-01", "2024-03-31"]]})
    assert r.status_code == 503 and "use samples/ or upload GeoTIFFs" in r.json()["detail"]
