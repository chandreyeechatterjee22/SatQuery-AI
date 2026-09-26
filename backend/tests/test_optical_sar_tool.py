import re

import pytest
import rasterio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.controller import run_query
from agent.router import router
from tests.scenes import optical_sar_scene

pytestmark = pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")


@pytest.fixture
def pair(make_upload):
    optical, sar = optical_sar_scene()
    return make_upload("optical_sar", [{"count": 4, "data": optical},
                                       {"count": 1, "dtype": "float32", "data": sar}],
                       sensors=["cartosat2s", None])


def test_water_question_end_to_end(pair, upload_dir):
    res = run_query(pair, "Where is the water?")

    assert res["status"] == "OK"
    assert res["trace"]["tool"] == "optical_sar_mapper" and res["trace"]["tool_version"] == "1.0.0"
    assert res["trace"]["params"]["classes"] == ["water"]
    assert [i["role"] for i in res["trace"]["inputs"]] == ["optical", "sar"]
    water = res["details"]["classes"]["water"]
    assert water["percent"] == 25.0 and water["agreement"] == round(16 / 17, 4)
    assert res["confidence"] == water["agreement"]
    assert res["details"]["confidence_basis"] == "modality_agreement"

    assert "Water: 25.00% of the 0.0064 km² both images cover (0.0016 km²)" in res["answer"]
    assert "they agree on 25.00% (optical only 0.00%, SAR only 1.56%, agreement 94%)" in res["answer"]
    assert "both modalities must agree" in res["answer"]
    assert "Built-up" not in res["answer"]

    kinds = [(e["id"], e["kind"]) for e in res["evidence_images"]]
    assert kinds == [("preview_1", "preview"), ("preview_2", "preview"), ("water_overlay", "overlay")]
    overlay = res["evidence_images"][2]
    assert overlay["base"] == "preview_1"
    assert [l["label"] for l in overlay["legend"]] == ["optical + SAR agree", "optical only", "SAR only"]
    png = upload_dir / pair / "queries" / res["query_id"] / "water_overlay.png"
    with rasterio.open(png) as src:
        rgba = src.read()
    assert rgba.shape == (4, 8, 8)
    assert (rgba[3, 0:2] > 0).all()         # water rows painted
    assert rgba[3, 7, 7] > 0 and rgba[3, 7, 6] == 0  # SAR-only pixel painted, vegetation not
    assert tuple(rgba[:3, 7, 7]) == (0xa3, 0x71, 0xf7)  # SAR-only colour


def test_both_classes_and_answer_numbers_match_stats(pair):
    res = run_query(pair, "Map water and built-up areas")
    stats = res["details"]["classes"]
    assert set(stats) == {"water", "built_up"}
    assert res["confidence"] == round((stats["water"]["agreement"] + stats["built_up"]["agreement"]) / 2, 4)
    # Every percentage printed in the answer comes from the stats.
    printed = {float(x) for x in re.findall(r"(\d+\.\d\d)%", res["answer"])}
    known = {v for s in stats.values() for k, v in s.items() if k.endswith("percent") and v is not None}
    assert printed <= known
    assert "Built-up: 23.44%" in res["answer"]
    assert [e["id"] for e in res["evidence_images"]][-2:] == ["water_overlay", "built_up_overlay"]


def test_or_fusion_param(pair):
    res = run_query(pair, "Where is the water?", params={"fusion": "or"})
    assert res["details"]["classes"]["water"]["percent"] == 26.56
    assert "either modality is enough" in res["answer"]


@pytest.mark.parametrize("params, fragment", [
    ({"sar_water_db": -5.0, "sar_builtup_db": -10.0}, "'sar_builtup_db' must be higher"),
    ({"sar_water_db": -50.0}, "between -35 and -5"),
    ({"fusion": "xor"}, "must be one of"),
    ({"max_size": 10}, "between 128 and 2048"),
    ({"classes": ["clouds"]}, "not in"),
])
def test_bad_params_rejected(pair, params, fragment):
    res = run_query(pair, "Where is the water?", params=params)
    assert res["status"] == "REJECTED" and fragment in res["answer"]


def test_sar_only_when_optical_is_rgb(make_upload):
    optical, sar = optical_sar_scene()
    uid = make_upload("optical_sar", [{"count": 3, "data": optical[:3]},
                                      {"count": 1, "dtype": "float32", "data": sar}])
    res = run_query(uid, "Where is the water?")
    assert res["status"] == "OK"
    assert res["confidence"] is None                    # no agreement without two modalities
    assert "Detected by SAR only" in res["answer"]
    overlay = res["evidence_images"][-1]
    assert [l["label"] for l in overlay["legend"]] == ["SAR only"]


def test_overlay_is_served(pair, upload_dir):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = run_query(pair, "Where are the buildings?")
    url = next(e["url"] for e in res["evidence_images"] if e["kind"] == "overlay")
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
