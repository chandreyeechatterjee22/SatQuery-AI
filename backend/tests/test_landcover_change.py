import re

import numpy as np
import pytest
import rasterio

from agent.controller import run_query
from local_analysis import landcover_change as lc
from raster.band_adapter import resolve_bands
from raster.metadata import read_metadata
from tests.scenes import LC_BUILT, LC_VEG, bitemporal_scene, landcover_image
from tests.synthetic import make_geotiff

pytestmark = pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")

D1, D2 = "2023-01-15", "2025-01-15"


def side(tmp_path, name, data, date, count=4):
    path = make_geotiff(tmp_path / name, count=count, data=data)
    return {"path": path, "bands": resolve_bands(read_metadata(path), "cartosat2s" if count == 4 else "auto"),
            "date": date}


# --- analysis ----------------------------------------------------------------

def test_per_class_change(tmp_path):
    before, after = bitemporal_scene()
    res = lc.analyse_change(side(tmp_path, "b.tif", before, D1), side(tmp_path, "a.tif", after, D2))
    c = res["classes"]

    assert (c["water"]["before_percent"], c["water"]["after_percent"], c["water"]["delta_pp"]) == (25.0, 25.0, 0.0)
    assert c["water"]["direction"] == "unchanged"
    assert (c["built_up"]["before_percent"], c["built_up"]["after_percent"]) == (25.0, 37.5)
    assert c["built_up"]["delta_pp"] == 12.5 and c["built_up"]["direction"] == "increased"
    assert c["built_up"]["relative_change_percent"] == 50.0
    assert (c["built_up"]["before_km2"], c["built_up"]["after_km2"], c["built_up"]["delta_km2"]) == \
        (0.0016, 0.0024, 0.0008)
    assert c["vegetation"]["delta_pp"] == -25.0 and c["vegetation"]["direction"] == "decreased"
    assert c["other"]["delta_pp"] == 12.5 and c["other"]["relative_change_percent"] is None

    assert res["changed_percent"] == 25.0
    assert res["transitions"] == [
        {"from": "vegetation", "to": "built_up", "percent": 12.5, "pixels": 8},
        {"from": "vegetation", "to": "other", "percent": 12.5, "pixels": 8},
    ]
    assert res["valid_area_km2"] == 0.0064
    assert res["methods"]["built_up_index"].startswith("low-NDVI proxy")
    assert any("No SWIR band" in w for w in res["warnings"])


def test_shares_sum_to_100_each_date(tmp_path):
    before, after = bitemporal_scene()
    res = lc.analyse_change(side(tmp_path, "b.tif", before, D1), side(tmp_path, "a.tif", after, D2))
    for when in ("before", "after"):
        assert sum(s[f"{when}_percent"] for s in res["classes"].values()) == pytest.approx(100.0, abs=0.05)


def test_robustness_is_full_for_clear_cut_scene(tmp_path):
    before, after = bitemporal_scene()
    res = lc.analyse_change(side(tmp_path, "b.tif", before, D1), side(tmp_path, "a.tif", after, D2))
    assert res["robustness"]["runs"] == 27
    assert res["robustness"]["per_class"] == {"water": 1.0, "built_up": 1.0, "vegetation": 1.0, "other": 1.0}


def test_robustness_drops_when_pixels_sit_on_a_threshold(tmp_path):
    before, after = bitemporal_scene()
    borderline = (500, 800, 900, 1300)  # NDVI ~0.18: built-up at 0.2, "other" if the threshold drops to 0.15
    after = landcover_image([(500, 1000, 300, 200)] * 2 + [borderline] * 3 + [LC_VEG] * 3)
    res = lc.analyse_change(side(tmp_path, "b.tif", before, D1), side(tmp_path, "a.tif", after, D2))
    assert res["classes"]["built_up"]["direction"] == "increased"
    assert res["robustness"]["per_class"]["built_up"] < 1.0


def test_tolerance_controls_unchanged(tmp_path):
    before = landcover_image([LC_BUILT] * 2 + [LC_VEG] * 6)
    after = before.copy()
    after[:, 2, 0] = LC_BUILT  # one pixel veg -> built = +1.56 pp
    b, a = side(tmp_path, "b.tif", before, D1), side(tmp_path, "a.tif", after, D2)
    assert lc.analyse_change(b, a)["classes"]["built_up"]["direction"] == "increased"
    assert lc.analyse_change(b, a, {"unchanged_tolerance_pp": 2.0})["classes"]["built_up"]["direction"] == "unchanged"


def test_sentinel2_uses_mndwi_and_ndbi(tmp_path):
    before, after = bitemporal_scene()

    def s2(img):
        out = np.zeros((10, 8, 8), dtype="uint16")
        out[0], out[1], out[2], out[6] = img           # blue, green, red, nir
        nir = img[3].astype(float)
        out[8] = np.where(img[3] == 1000, 1500, np.where(img[3] == 200, 50, nir * 0.5))  # SWIR1
        return out

    b = side(tmp_path, "b.tif", s2(before), D1, count=10)
    a = side(tmp_path, "a.tif", s2(after), D2, count=10)
    res = lc.analyse_change(b, a)
    assert res["methods"]["water_index"] == "MNDWI (green, SWIR1)"
    assert res["methods"]["built_up_index"] == "NDBI (SWIR1, NIR)"
    assert res["classes"]["built_up"]["delta_pp"] == 12.5
    assert not any("No SWIR" in w for w in res["warnings"])


def test_missing_bands_raise(tmp_path):
    rgb = np.full((3, 8, 8), 100, dtype="uint16")
    b = {"path": make_geotiff(tmp_path / "b.tif", count=3, data=rgb), "date": D1}
    a = {"path": make_geotiff(tmp_path / "a.tif", count=3, data=rgb), "date": D2}
    b["bands"] = resolve_bands(read_metadata(b["path"]))
    a["bands"] = resolve_bands(read_metadata(a["path"]))
    with pytest.raises(lc.MissingBands, match="missing on at least one date: nir"):
        lc.analyse_change(b, a)


def test_direction_helper():
    assert lc.direction(0.99, 1.0) == "unchanged"
    assert lc.direction(1.0, 1.0) == "increased"
    assert lc.direction(-1.0, 1.0) == "decreased"


# --- tool through the controller ------------------------------------------------------

@pytest.fixture
def pair(make_upload):
    before, after = bitemporal_scene()
    return make_upload("bi_temporal", [{"count": 4, "data": before}, {"count": 4, "data": after}],
                       dates=[D1, D2], sensors=["cartosat2s", "cartosat2s"])


LINE = re.compile(r"^(?P<label>[\w-]+) (?P<verb>increased|decreased|remained essentially unchanged): "
                  r"(?P<b>\d+\.\d\d)% on (?P<d1>[\d-]+) -> (?P<a>\d+\.\d\d)% on (?P<d2>[\d-]+) "
                  r"\((?P<d>[+-]\d+\.\d\d) percentage points")


def check_lines_match_numbers(answer, details, tolerance=1.0):
    """Every class line: after - before == delta, and the verb matches the delta."""
    labels = {"Water": "water", "Built-up": "built_up", "Vegetation": "vegetation", "Other": "other"}
    found = 0
    for line in answer.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        found += 1
        b, a, d = float(m["b"]), float(m["a"]), float(m["d"])
        assert round(a - b, 2) == d
        expected = ("remained essentially unchanged" if abs(d) < tolerance
                    else "increased" if d > 0 else "decreased")
        assert m["verb"] == expected
        stats = details["classes"][labels[m["label"]]]
        assert (stats["before_percent"], stats["after_percent"], stats["delta_pp"]) == (b, a, d)
    return found


def test_builtup_question(pair):
    res = run_query(pair, "Has built-up area increased, decreased or remained unchanged?")
    assert res["status"] == "OK"
    assert res["trace"]["tool"] == "landcover_change" and res["trace"]["params"]["classes"] == ["built_up"]
    assert res["details"]["short_answer"] == "increased"
    assert res["answer"].startswith(f"Built-up increased: 25.00% on {D1} -> 37.50% on {D2} "
                                    "(+12.50 percentage points, 0.0016 -> 0.0024 km², +0.0008 km², +50.0% relative).")
    assert check_lines_match_numbers(res["answer"], res["details"]) == 1
    assert res["confidence"] == 1.0
    assert res["details"]["confidence_basis"] == "threshold_robustness"


def test_what_changed(pair):
    res = run_query(pair, "What changed?")
    assert res["status"] == "OK" and res["trace"]["params"]["classes"] == list(lc.CLASSES)
    assert "short_answer" not in res["details"]
    lines = res["answer"].splitlines()
    assert lines[0] == f"Between {D1} and {D2}, 25.00% of the compared area changed land-cover class."
    assert lines[1].startswith("Vegetation decreased")          # sorted by |delta|
    assert "Water remained essentially unchanged" in res["answer"]
    assert "within the ±1 pp tolerance" in res["answer"]
    assert "Largest transitions: Vegetation -> Built-up 12.50%; Vegetation -> Other 12.50%." in res["answer"]
    assert check_lines_match_numbers(res["answer"], res["details"]) == 4


def test_reverse_upload_order_is_sorted_by_date(make_upload):
    before, after = bitemporal_scene()
    uid = make_upload("bi_temporal", [{"count": 4, "data": after}, {"count": 4, "data": before}],
                      dates=[D2, D1], sensors=["cartosat2s", "cartosat2s"])
    res = run_query(uid, "Has built-up area increased?")
    assert res["details"]["short_answer"] == "increased"
    assert [(i["slot"], i["role"]) for i in res["trace"]["inputs"]] == [(2, "before"), (1, "after")]
    assert res["details"]["dates"] == {"before": D1, "after": D2}


def test_water_question_on_bitemporal_is_change(pair):
    res = run_query(pair, "Where is the water?")
    assert res["trace"]["task"] == "change" and res["trace"]["rerouted_from"] == "water_builtup"
    assert res["details"]["short_answer"] == "unchanged"
    assert res["answer"].startswith("Water remained essentially unchanged")


def test_landcover_maps_as_evidence(pair, upload_dir):
    res = run_query(pair, "What changed?")
    ids = [e["id"] for e in res["evidence_images"]]
    assert ids == ["preview_1", "preview_2", "landcover_before", "landcover_after"]
    after_map = res["evidence_images"][3]
    assert after_map["base"] == "preview_2" and after_map["kind"] == "overlay"
    assert [l["label"] for l in after_map["legend"]] == ["Water", "Built-up", "Vegetation", "Other"]
    png = upload_dir / pair / "queries" / res["query_id"] / "landcover_after.png"
    with rasterio.open(png) as src:
        rgba = src.read()
    assert tuple(rgba[:3, 0, 0]) == (0x1f, 0x6f, 0xeb)   # water row
    assert tuple(rgba[:3, 4, 0]) == (0xd7, 0x3a, 0x49)   # new built-up row
    assert tuple(rgba[:3, 7, 0]) == (0xbf, 0x87, 0x00)   # other row


def test_rgb_pair_is_not_available(make_upload):
    rgb = np.full((3, 8, 8), 100, dtype="uint16")
    uid = make_upload("bi_temporal", [{"count": 3, "data": rgb}, {"count": 3, "data": rgb}], dates=[D1, D2])
    res = run_query(uid, "What changed?")
    assert res["status"] == "NOT_AVAILABLE"
    assert "needs multispectral images" in res["answer"]


def test_bad_params(pair):
    res = run_query(pair, "What changed?", params={"unchanged_tolerance_pp": 50})
    assert res["status"] == "REJECTED" and "between 0 and 20" in res["answer"]
