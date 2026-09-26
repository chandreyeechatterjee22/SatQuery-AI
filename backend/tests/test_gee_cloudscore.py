"""Offline regression tests for the Earth Engine flow (no network, no credentials).

Bug: scenes newer than their Cloud Score+ image made link_cs() call addBands(null),
so /api/analyze returned 500. Fix: only keep scenes that have a Cloud Score+ image,
and return 422 when nothing is left.
"""
import types

from fastapi.testclient import TestClient

import gee_service
import main


class FakeCollection:
    def __init__(self, name, ops=None):
        self.name, self.ops = name, list(ops or [])

    def _next(self, op):
        return FakeCollection(self.name, self.ops + [op])

    def filterBounds(self, aoi):
        return self._next(("filterBounds", aoi))

    def filterDate(self, start, end):
        return self._next(("filterDate", start, end))

    def filter(self, flt):
        return self._next(("filter", flt))

    def map(self, fn):
        return self._next(("map", fn.__name__))

    def aggregate_array(self, prop):
        return ("aggregate_array", self.name, prop)


def fake_ee():
    return types.SimpleNamespace(
        ImageCollection=FakeCollection,
        Filter=types.SimpleNamespace(inList=lambda prop, values: ("inList", prop, values),
                                     eq=lambda prop, value: ("eq", prop, value)),
    )


def test_scenes_without_cloud_score_are_dropped_before_join(monkeypatch):
    monkeypatch.setattr(gee_service, "ee", fake_ee())
    col = gee_service.get_s2_sr_cld_col("aoi", "2025-09-26", "2026-09-26")

    assert col.name == "COPERNICUS/S2_SR_HARMONIZED"
    ops = [op[0] for op in col.ops]
    assert ops == ["filterBounds", "filterDate", "filter", "map", "map"]
    assert col.ops[2] == ("filter", ("inList", "system:index",
                                     ("aggregate_array", "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED",
                                      "system:index")))
    assert [op[1] for op in col.ops[3:]] == ["link_cs", "apply_cs_mask"]


class EmptyCollection:
    def __init__(self, n=0):
        self.n = n

    def filterDate(self, *args):
        return EmptyCollection(0)

    def size(self):
        return types.SimpleNamespace(getInfo=lambda: self.n)


AOI = {"type": "Polygon", "coordinates": [[[73.78, 19.98], [73.80, 19.98], [73.80, 20.0], [73.78, 19.98]]]}


def client(monkeypatch, total_scenes):
    monkeypatch.setattr(main, "dict_to_ee_geometry", lambda geom: "aoi")
    monkeypatch.setattr(main, "get_s2_sr_cld_col", lambda *a: EmptyCollection(total_scenes))
    return TestClient(main.app)  # no context manager: GEE startup is not run


def test_analyze_without_recent_scenes_returns_422(monkeypatch):
    r = client(monkeypatch, 0).post("/api/analyze", json={"state": "Maharashtra", "area": "Nashik",
                                                          "geometry": AOI, "query": "Where are the water bodies?"})
    assert r.status_code == 422
    assert r.json()["detail"] == main.NO_IMAGERY_90D


def test_sentinel_without_any_scenes_returns_422(monkeypatch):
    r = client(monkeypatch, 0).post("/api/sentinel", json={"state": "Maharashtra", "area": "Nashik", "geometry": AOI})
    assert r.status_code == 422
    assert r.json()["detail"] == main.NO_IMAGERY_12M
