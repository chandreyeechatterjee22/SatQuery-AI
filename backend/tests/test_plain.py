"""Plain-language answers: present for every tool and status, jargon-free, and using exactly the
tool's own numbers and direction words."""
import json
import re

import numpy as np
import pytest

from agent import plain
from agent.controller import run_query
from tests.scenes import bitemporal_scene, optical_sar_scene
from tests.test_landcover_change import D1, D2, dimmed, fake_model  # noqa: F401 (fixture)
from tests.test_photo_inputs import png, upload
from tests.test_vqa_caption_tools import fake_clip  # noqa: F401 (fixture)
from tests.synthetic import make_geotiff

pytestmark = pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")

LEVELS = {"High", "Medium", "Low", "Not rated"}


def check_plain(res):
    """Shape + no-jargon checks shared by every result. Returns the plain block."""
    p = res["plain"]
    assert set(p) == {"headline", "what_it_means", "key_numbers", "how_we_know", "confidence", "caveats",
                      "next_step"}
    for key in ("headline", "what_it_means", "how_we_know"):
        assert isinstance(p[key], str) and p[key].strip(), key
    assert p["confidence"]["level"] in LEVELS
    assert p["confidence"]["text"] == f"{p['confidence']['level']} — {p['confidence']['reason']}"
    assert isinstance(p["key_numbers"], list) and isinstance(p["caveats"], list)
    if res["status"] == "OK":
        assert 1 <= len(p["key_numbers"]) <= 4
        assert 1 <= p["what_it_means"].count(". ") + 1 <= 6
    banned = plain.contains_banned(json.dumps(p, ensure_ascii=False))
    assert banned == [], f"jargon in plain answer: {banned}"
    return p


def level(value):
    return plain.level_for(value)


# --- confidence words ------------------------------------------------------------------

def test_confidence_levels_follow_env_thresholds(monkeypatch):
    assert (level(0.9), level(0.5), level(0.1), level(None)) == ("High", "Medium", "Low", "Not rated")
    monkeypatch.setenv("PLAIN_CONFIDENCE_HIGH", "0.95")
    monkeypatch.setenv("PLAIN_CONFIDENCE_MEDIUM", "0.6")
    assert (level(0.9), level(0.5)) == ("Medium", "Low")
    monkeypatch.setenv("PLAIN_CONFIDENCE_MEDIUM", "0.99")  # inconsistent -> defaults
    assert level(0.8) == "High"


def test_banned_word_detector():
    assert plain.contains_banned("VV below -18 dB, NDWI > 0, +3.2 pp") == ["dB", "pp", "VV", "NDWI"]
    assert plain.contains_banned("Map the water; apps and radar (SAR) images") == []


# --- single image ------------------------------------------------------------------------

def test_vqa_rural_urban(make_upload, fake_clip):  # noqa: F811
    from models.zero_shot import RURAL_URBAN_PROMPTS
    fake_clip(RURAL_URBAN_PROMPTS["urban"])
    res = run_query(make_upload("single", [{}]), "Is it a rural or an urban area?")
    p = check_plain(res)
    assert res["answer"] == "urban" and "urban area" in p["headline"]
    assert f"Model's certainty: {round(res['confidence'] * 100)}%" in p["key_numbers"]
    assert p["confidence"]["level"] == level(res["confidence"])


def test_vqa_presence_names_the_object(make_upload, fake_clip):  # noqa: F811
    from models.zero_shot import PRESENCE_PROMPTS
    fake_clip(PRESENCE_PROMPTS["yes"].format("road"))
    res = run_query(make_upload("single", [{}]), "Is there a road?")
    p = check_plain(res)
    assert res["answer"] == "yes" and p["headline"] == "Yes — the model found road in this image."


def test_caption_numbers_match(make_upload, fake_clip):  # noqa: F811
    from models.zero_shot import SCENE_TEMPLATE
    fake_clip(SCENE_TEMPLATE.format("farmland"))
    res = run_query(make_upload("single", [{}]), "Describe this image")
    p = check_plain(res)
    scores = res["details"]["scene_scores"]
    assert p["headline"] == f"This looks like {scores[0]['label']}."
    for s, line in zip(scores, p["key_numbers"]):
        assert line.lower().startswith(s["label"].lower()) and f"{round(s['probability'] * 100)}% match" in line


def test_metadata(make_upload):
    res = run_query(make_upload("single", [{"count": 5}]), "How many bands does this image have and what is the resolution?")
    p = check_plain(res)
    assert p["key_numbers"][0].startswith("Layers: 5")
    assert "Each pixel covers: 10 × 10 m on the ground" in p["key_numbers"]
    assert p["confidence"]["level"] == "High"


# --- optical + SAR -------------------------------------------------------------------------

@pytest.fixture
def optsar(make_upload):
    optical, sar = optical_sar_scene()
    return make_upload("optical_sar", [{"count": 4, "data": optical}, {"count": 1, "dtype": "float32", "data": sar}],
                       sensors=["cartosat2s", None])


def test_optical_sar_numbers_match(optsar):
    res = run_query(optsar, "Map water and built-up areas")
    p = check_plain(res)
    for cls, name in (("water", "Water"), ("built_up", "Built-up")):
        s = res["details"]["classes"][cls]
        assert f"{name}: {s['percent']:.2f}% of the area ({plain.km2(s['area_km2'])})" in p["key_numbers"]
        assert f"{s['percent']:.1f}%" in p["headline"]
        assert (f"{name} found by the normal image {s['optical_percent']:.2f}%, by radar {s['sar_percent']:.2f}%, "
                f"by both {s['both_percent']:.2f}%") in p["key_numbers"]
    assert plain.km2(res["details"]["valid_area_km2"]) in p["what_it_means"]
    assert p["confidence"]["level"] == level(res["confidence"])
    assert "radar (SAR)" in p["how_we_know"] and "buildings reflect radar strongly" in p["how_we_know"]


def test_optical_sar_single_class(optsar):
    res = run_query(optsar, "Where is the water?")
    p = check_plain(res)
    assert "built-up" not in p["headline"] and p["next_step"] == "How much of the area is built-up?"


def test_optical_sar_without_ground_scale_uses_pixels(tmp_path, upload_dir):
    # A CRS in US feet: the pair is georeferenced, but the tools report no km².
    optical, sar = optical_sar_scene()
    feet = {"crs": "EPSG:2227", "origin": (6000000.0, 2000000.0)}
    opt = make_geotiff(tmp_path / "o.tif", count=4, data=optical, **feet)
    s = make_geotiff(tmp_path / "s.tif", count=1, dtype="float32", data=sar, **feet)
    res = run_query(upload("optical_sar", [opt, s], benchmark=False), "Where is the water?")
    assert res["status"] == "OK"
    p = check_plain(res)
    assert res["details"]["valid_area_km2"] is None
    assert "km²" not in json.dumps(p, ensure_ascii=False)
    assert f"{res['details']['classes']['water']['pixels']:,} pixels" in p["key_numbers"][0]
    assert any("can't measure real areas" in c for c in p["caveats"])


def test_area_formatting():
    assert (plain.km2(14.7943), plain.km2(0.6246), plain.km2(0.0016), plain.km2(None)) == (
        "14.79 km²", "0.62 km²", "1,600 m²", None)


# --- change analysis -------------------------------------------------------------------------

@pytest.fixture
def change_pair(make_upload):
    before, after = bitemporal_scene()
    return make_upload("bi_temporal", [{"count": 4, "data": before}, {"count": 4, "data": after}],
                       dates=[D1, D2], sensors=["cartosat2s", "cartosat2s"])


def test_change_builtup_direction_and_numbers(change_pair):
    res = run_query(change_pair, "Has built-up area increased, decreased or remained unchanged?")
    p = check_plain(res)
    s = res["details"]["classes"]["built_up"]
    assert res["details"]["short_answer"] == "increased"
    assert p["headline"] == "Yes — the built-up area has increased."
    assert (f"Built-up: {s['before_percent']:.2f}% → {s['after_percent']:.2f}% of the area "
            f"({plain.km2(s['before_km2'])} → {plain.km2(s['after_km2'])})") in p["key_numbers"]
    assert f"about {s['before_percent']:.1f}%" in p["what_it_means"].lower()
    assert "15 Jan 2023" in p["what_it_means"] and "15 Jan 2025" in p["what_it_means"]
    assert "more of this area became buildings and roads" in p["what_it_means"]


@pytest.mark.parametrize("question, cls, word", [
    ("Has vegetation changed?", "vegetation", "decreased"),
    ("Has the water area changed?", "water", "unchanged"),
])
def test_change_other_directions(change_pair, question, cls, word):
    res = run_query(change_pair, question)
    p = check_plain(res)
    assert res["details"]["classes"][cls]["direction"] == word
    expected = {"decreased": "has decreased", "unchanged": "has stayed about the same"}[word]
    assert expected in p["headline"]
    assert p["headline"].startswith("No —" if word == "unchanged" else "Yes —")


def test_what_changed_uses_changed_share(change_pair):
    res = run_query(change_pair, "What changed?")
    p = check_plain(res)
    d = res["details"]
    assert p["headline"].startswith(f"About {d['changed_percent']:.1f}% of the area changed")
    assert f"Share of the area that changed: {d['changed_percent']:.2f}%" in p["key_numbers"]
    for line in p["key_numbers"][:3]:
        m = re.match(r"([\w -]+): (\d+\.\d\d)% → (\d+\.\d\d)%", line)
        cls = {"Water": "water", "Built-up": "built_up", "Vegetation": "vegetation", "Other land": "other"}[m[1]]
        assert (float(m[2]), float(m[3])) == (d["classes"][cls]["before_percent"], d["classes"][cls]["after_percent"])


def test_change_model_agrees(change_pair, fake_model):  # noqa: F811
    fake_model(0.40, 0.70)
    res = run_query(change_pair, "Has built-up area increased, decreased or remained unchanged?")
    p = check_plain(res)
    assert "How city-like the scene looks to our AI model: 40 → 70 out of 100" in p["key_numbers"]
    assert p["confidence"]["level"] == "High" and "both methods agree" in p["confidence"]["reason"]


def test_change_model_disagrees_is_uncertain(change_pair, fake_model):  # noqa: F811
    fake_model(0.70, 0.40)
    res = run_query(change_pair, "Has built-up area increased, decreased or remained unchanged?")
    p = check_plain(res)
    assert res["details"]["short_answer"] == "decreased"
    assert p["headline"] == "The built-up area probably decreased, but our two methods disagree."
    assert "treat this answer as uncertain" in p["what_it_means"]
    assert p["confidence"]["reason"] == "the two methods we used don't agree."
    assert p["confidence"]["level"] == level(res["confidence"])


def test_change_season_caveat(make_upload):
    before, _ = bitemporal_scene()
    uid = make_upload("bi_temporal", [{"count": 4, "data": before}, {"count": 4, "data": dimmed(before, 0.5)}],
                      dates=[D1, D2], sensors=["cartosat2s", "cartosat2s"])
    res = run_query(uid, "Has built-up area increased?")
    p = check_plain(res)
    assert p["confidence"]["level"] == "Low"
    assert any("differ in how green the land is" in c for c in p["caveats"])
    assert any("bare soil" in c for c in p["caveats"])  # 4-band images have no SWIR


# --- not available / rejected -------------------------------------------------------------

def test_not_available_model_missing(make_upload):
    res = run_query(make_upload("single", [{}]), "Describe this image")
    p = check_plain(res)
    assert res["status"] == "NOT_AVAILABLE"
    assert "isn't installed" in p["what_it_means"] and p["next_step"]
    assert p["key_numbers"] == [] and p["confidence"]["level"] == "Not rated"


def test_not_available_photo_pair(tmp_path, upload_dir):
    rng = np.random.default_rng(1)
    opt = png(tmp_path / "opt.png", rng.integers(0, 255, (3, 16, 16), dtype=np.uint8))
    sar = png(tmp_path / "sar.png", rng.integers(0, 255, (1, 16, 16), dtype=np.uint8))
    res = run_query(upload("optical_sar", [opt, sar]), "Map water and built-up areas")
    p = check_plain(res)
    assert "not real radar measurements" in p["what_it_means"]
    assert "Fetch from Earth Engine" in p["next_step"]


def test_not_available_change_without_infrared(tmp_path, upload_dir):
    rng = np.random.default_rng(2)
    a = png(tmp_path / "t1.png", rng.integers(0, 255, (3, 16, 16), dtype=np.uint8))
    b = png(tmp_path / "t2.png", rng.integers(0, 255, (3, 16, 16), dtype=np.uint8))
    res = run_query(upload("bi_temporal", [a, b], dates=["2021-01-01", "2025-01-01"]), "What changed?")
    p = check_plain(res)
    assert res["status"] == "NOT_AVAILABLE" and "infrared" in p["what_it_means"]


@pytest.mark.parametrize("question, headline", [
    ("zzzz qqqq", "We couldn't tell what you're asking."),
    ("What changed?", "This question doesn't fit the images you uploaded."),
])
def test_rejected(make_upload, question, headline):
    res = run_query(make_upload("single", [{}]), question)
    p = check_plain(res)
    assert res["status"] == "REJECTED" and p["headline"] == headline
    assert p["next_step"] == "Describe this image"


def test_template_failure_never_breaks_the_answer(make_upload, monkeypatch):
    monkeypatch.setattr(plain, "_metadata", lambda *a: 1 / 0)
    res = run_query(make_upload("single", [{}]), "How many bands?")
    assert res["status"] == "OK" and "Technical details" in res["plain"]["what_it_means"]
    assert res["answer"].startswith("File 1")  # the technical answer is untouched
    assert plain.contains_banned(json.dumps(res["plain"])) == []
