"""All-India location list (generated file) and the /api/states, /api/areas, /api/location endpoints."""
import json

import pytest
from fastapi.testclient import TestClient

import locations

# India incl. Andaman & Nicobar, Lakshadweep and Ladakh.
INDIA_BBOX = (68.0, 6.0, 97.5, 37.5)  # west, south, east, north

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]
UTS = [
    "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]


@pytest.fixture(scope="module")
def client():
    import main
    return TestClient(main.app)  # no context manager: the Earth Engine startup hook does not run


def raw():
    return json.loads(locations.DATA_FILE.read_text(encoding="utf-8"))


# --- the data file -----------------------------------------------------------------------------

def test_all_28_states_and_8_uts_alphabetical():
    names = locations.state_names()
    assert sorted(names) == sorted(STATES + UTS) and len(names) == 36
    assert names == sorted(names)
    types = {s["name"]: s["type"] for s in raw()["states"]}
    assert sorted(n for n, t in types.items() if t == "state") == sorted(STATES)
    assert sorted(n for n, t in types.items() if t == "union_territory") == sorted(UTS)


def test_every_district_is_inside_india_with_a_valid_bbox_and_zoom():
    west, south, east, north = INDIA_BBOX
    total = 0
    for state in locations.state_names():
        names = locations.district_names(state)
        assert names, state
        assert names == sorted(names), f"{state} districts not alphabetical"
        for name in names:
            d = locations.resolve(state, name)
            assert west <= d["lon"] <= east and south <= d["lat"] <= north, (state, name)
            w, s, e, n = d["bbox"]
            assert west <= w < e <= east and south <= s < n <= north, (state, name)
            assert w <= d["lon"] <= e and s <= d["lat"] <= n, (state, name)
            assert 5 <= d["zoom"] <= 12
            total += 1
    assert 700 <= total <= 800


def test_major_cities_point_at_real_districts():
    for state in locations.state_names():
        majors = locations.major_cities(state)
        assert 1 <= len(majors) <= 6, state
        districts = set(locations.district_names(state))
        for m in majors:
            assert m["district"] in districts, (state, m)
            assert m["label"]
        assert len({m["district"] for m in majors}) == len(majors), state


def test_major_cities_examples():
    def labels(state):
        return [m["label"] for m in locations.major_cities(state)]
    assert labels("Maharashtra") == ["Mumbai", "Pune", "Nagpur", "Nashik", "Thane"]
    wb = {m["label"]: m["district"] for m in locations.major_cities("West Bengal")}
    assert wb["Kolkata"] == "Kolkata" and wb["Howrah"] == "Howrah"
    assert wb["Siliguri area (Darjeeling)"] == "Darjeeling"
    assert wb["Asansol area (Paschim Bardhaman)"] == "Paschim Bardhaman"


@pytest.mark.parametrize("state, old, new", [
    ("Karnataka", "Bengaluru Urban", "Bengaluru Urban"),
    ("Karnataka", "Bengaluru Rural", "Bengaluru Rural"),
    ("Karnataka", "Mysuru", "Mysuru"),
    ("Karnataka", "Mandya", "Mandya"),
    ("Karnataka", "Tumakuru", "Tumakuru"),
    ("Karnataka", "Mangaluru", "Dakshina Kannada"),
    ("Karnataka", "Shivamogga", "Shivamogga"),
    ("Karnataka", "Bangalore", "Bengaluru Urban"),     # source spelling still resolves
    ("Maharashtra", "Mumbai", "Mumbai"),
    ("Maharashtra", "Pune", "Pune"),
    ("Maharashtra", "Nagpur", "Nagpur"),
    ("Maharashtra", "Nashik", "Nashik"),
    ("Tamil Nadu", "Chennai", "Chennai"),
    ("Tamil Nadu", "Coimbatore", "Coimbatore"),
    ("Tamil Nadu", "Madurai", "Madurai"),
    ("West Bengal", "Haora", "Howrah"),
    ("Uttar Pradesh", "Allahabad", "Prayagraj"),
])
def test_old_names_still_resolve(state, old, new):
    d = locations.resolve(state, old)
    assert d is not None and d["name"] == new


def test_old_names_land_near_their_old_coordinates():
    # The three former states' entries were city points; new centroids are district centroids.
    for state, area, lat, lon in [("Karnataka", "Bengaluru Urban", 12.9716, 77.5946),
                                  ("Maharashtra", "Mumbai", 19.0760, 72.8777),
                                  ("Tamil Nadu", "Chennai", 13.0827, 80.2707)]:
        d = locations.resolve(state, area)
        assert abs(d["lat"] - lat) < 0.15 and abs(d["lon"] - lon) < 0.15


def test_known_fixes():
    assert "Yanam" in locations.district_names("Puducherry")
    assert "Yanam" not in locations.district_names("Andhra Pradesh")
    assert "Leh" in locations.district_names("Ladakh")
    assert all("DATA NOT AVAILABLE" not in locations.district_names(s) for s in locations.state_names())
    assert "Hyderabad" in locations.district_names("Telangana")


def test_source_and_licence_recorded():
    src = raw()["source"]
    assert "geoBoundaries" in src["dataset"] and src["release_commit"]
    assert src["adm1"]["licence"] == "CC BY 2.5 IN" and src["adm2"]["licence"] == "ODbL 1.0"


def test_file_is_small_and_has_no_polygons():
    assert locations.DATA_FILE.stat().st_size < 300 * 1024
    text = locations.DATA_FILE.read_text(encoding="utf-8")
    assert '"coordinates"' not in text and '"geometry"' not in text


# --- API (same shapes as before, plus major_cities on /areas) ----------------------------------

def test_states_endpoint(client):
    body = client.get("/api/states").json()
    assert set(body) == {"states"} and len(body["states"]) == 36
    assert body["states"][0] == "Andaman and Nicobar Islands" and body["states"][-1] == "West Bengal"


def test_areas_endpoint_keeps_shape_and_adds_major_cities(client):
    body = client.get("/api/areas/West Bengal").json()
    assert set(body) == {"areas", "major_cities"}
    assert all(isinstance(a, str) for a in body["areas"]) and "Kolkata" in body["areas"]
    assert body["major_cities"][0] == {"label": "Kolkata", "district": "Kolkata"}


def test_district_list_changes_with_the_state(client):
    wb = client.get("/api/areas/West Bengal").json()["areas"]
    ladakh = client.get("/api/areas/Ladakh").json()["areas"]
    assert ladakh == ["Kargil", "Leh"]
    assert not set(wb) & set(ladakh)
    assert client.get("/api/areas/Nowhere").status_code == 404


def test_location_endpoint_keeps_shape(client):
    body = client.get("/api/location/Karnataka/Bengaluru Urban").json()
    assert set(body) == {"lat", "lon", "zoom"}
    assert isinstance(body["lat"], float) and isinstance(body["zoom"], int)
    assert client.get("/api/location/Karnataka/Mangaluru").status_code == 200
    assert client.get("/api/location/Kerala/Thiruvananthapuram").json()["lat"] < 9
    assert client.get("/api/location/Karnataka/Kolkata").status_code == 404
    assert client.get("/api/location/Atlantis/Kolkata").status_code == 404
