"""Photos (JPG/PNG/WebP) must never produce confident but meaningless numbers."""
import warnings

import numpy as np
import pytest
import rasterio
from rasterio.errors import NotGeoreferencedWarning

from agent.controller import run_query
from ingest import store
from ingest.validation import validate_upload
from raster.band_adapter import resolve_bands
from raster.metadata import read_metadata
from tests.scenes import optical_sar_scene
from tests.synthetic import make_geotiff

pytestmark = pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")


def png(path, data):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path, "w", driver="PNG", width=data.shape[2], height=data.shape[1],
                           count=data.shape[0], dtype="uint8") as dst:
            dst.write(data)
    return path


def upload(mode, paths, dates=None, benchmark=True):
    """Store an accepted upload from existing files (like POST /api/uploads)."""
    import shutil

    upload_id = store.new_upload_id()
    staged = store.staging_dir(upload_id)
    files = []
    for slot, src in enumerate(paths, start=1):
        target = staged / store.stored_name(slot, str(src))
        shutil.copyfile(src, target)
        files.append((src.name, target))
    res = validate_upload(mode, files, dates=dates, benchmark_mode=benchmark)
    assert res["ok"], res["reasons"]
    for info, (_, target) in zip(res["files"], files):
        info["stored_as"] = target.name
    store.commit(upload_id, {"upload_id": upload_id, "mode": mode, "files": res["files"],
                             "pair": res["pair"], "warnings": res["warnings"]})
    return upload_id


rng = np.random.default_rng(0)


# --- band adapter: photos are RGB(A) or gray, never NIR or radar by accident ------------------

def test_rgba_png_alpha_is_not_nir(tmp_path):
    p = png(tmp_path / "a.png", rng.integers(0, 255, (4, 8, 8), dtype=np.uint8))
    bands = resolve_bands(read_metadata(p))
    assert bands["kind"] == "optical" and bands["roles"] == {"red": 1, "green": 2, "blue": 3}
    assert "nir" not in bands["roles"] and bands["warnings"] == []


def test_gray_png_is_optical_unless_in_sar_slot(tmp_path):
    p = png(tmp_path / "g.png", rng.integers(0, 255, (1, 8, 8), dtype=np.uint8))
    meta = read_metadata(p)
    assert resolve_bands(meta)["kind"] == "optical"
    assert resolve_bands(meta, expected_kind="sar")["kind"] == "sar"


def test_geotiff_band_rules_unchanged(tmp_path):
    meta = read_metadata(make_geotiff(tmp_path / "s.tif", count=2, dtype="float32"))
    assert resolve_bands(meta)["kind"] == "sar"
    meta = read_metadata(make_geotiff(tmp_path / "o.tif", count=4))
    assert resolve_bands(meta)["roles"] == {"blue": 1, "green": 2, "red": 3, "nir": 4}


# --- optical + SAR ------------------------------------------------------------------------------

def test_photo_pair_is_not_available(tmp_path, upload_dir):
    opt = png(tmp_path / "opt.png", rng.integers(0, 255, (3, 16, 16), dtype=np.uint8))
    sar = png(tmp_path / "sar.png", rng.integers(0, 255, (1, 16, 16), dtype=np.uint8))
    res = run_query(upload("optical_sar", [opt, sar]), "Map water and built-up areas")
    assert res["status"] == "NOT_AVAILABLE" and res["confidence"] is None
    assert "The SAR image is a photo (JPG/PNG), not calibrated radar data" in res["answer"]
    assert "photo with only red/green/blue" in res["answer"]
    assert res["evidence_images"] == []


def test_uncalibrated_sar_geotiff_is_not_available(tmp_path, upload_dir):
    optical, _ = optical_sar_scene()
    opt = make_geotiff(tmp_path / "o.tif", count=4, data=optical)
    dn = make_geotiff(tmp_path / "s.tif", count=1, dtype="uint16",
                      data=rng.integers(5000, 20000, (1, 8, 8)).astype("uint16"))
    res = run_query(upload("optical_sar", [opt, dn], benchmark=False), "Where is the water?")
    assert res["status"] == "NOT_AVAILABLE"
    assert "does not contain calibrated backscatter" in res["answer"]
    assert "photo" not in res["answer"].split("SAR data")[1]  # only the radar reason


def test_calibrated_geotiff_pair_still_answers(tmp_path, upload_dir):
    optical, sar = optical_sar_scene()
    opt = make_geotiff(tmp_path / "o.tif", count=4, data=optical)
    s = make_geotiff(tmp_path / "s.tif", count=1, dtype="float32", data=sar)
    res = run_query(upload("optical_sar", [opt, s], benchmark=False), "Where is the water?")
    assert res["status"] == "OK" and res["details"]["classes"]["water"]["percent"] == 25.0


# --- change analysis ----------------------------------------------------------------------------

def test_rgba_photos_do_not_get_a_fake_change_answer(tmp_path, upload_dir):
    a = png(tmp_path / "t1.png", rng.integers(0, 255, (4, 16, 16), dtype=np.uint8))
    b = png(tmp_path / "t2.png", rng.integers(0, 255, (4, 16, 16), dtype=np.uint8))
    res = run_query(upload("bi_temporal", [a, b], dates=["2021-01-01", "2025-01-01"]), "What changed?")
    assert res["status"] == "NOT_AVAILABLE" and "missing on at least one date: nir" in res["answer"]


def test_vqa_count_on_photo_carries_scale_note(tmp_path, upload_dir, monkeypatch):
    torch = pytest.importorskip("torch")  # noqa: F841
    from models import remoteclip
    from tests.fakes import FakeEncoder, unit
    from tests.test_vqa_head import make_artifact

    enc = FakeEncoder(image_vector=unit("x"))
    monkeypatch.setattr(remoteclip, "availability", lambda: (True, None))
    monkeypatch.setattr(remoteclip, "get_encoder", lambda: enc)
    monkeypatch.setenv("VQA_HEAD_PATH", str(make_artifact(tmp_path / "h.pt", bias_towards="5")))
    photo = png(tmp_path / "p.png", rng.integers(0, 255, (3, 16, 16), dtype=np.uint8))
    uid = upload("single", [photo])

    res = run_query(uid, "How many buildings are there?")
    assert (res["status"], res["answer"]) == ("OK", "5")          # canonical answer kept for benchmarks
    assert "no map scale" in res["details"]["warnings"][0]
    res = run_query(uid, "Is there a road?")
    assert res["details"]["warnings"] == []                        # only counts get the note


def test_rgba_png_in_sar_slot_is_accepted_then_not_available(tmp_path, upload_dir):
    opt = png(tmp_path / "optical 2", rng.integers(0, 255, (4, 16, 16), dtype=np.uint8))   # no extension, RGBA
    sar = png(tmp_path / "sar 2", rng.integers(0, 255, (4, 16, 16), dtype=np.uint8))
    meta = read_metadata(sar)
    bands = resolve_bands(meta, expected_kind="sar")
    assert bands["kind"] == "sar" and bands["roles"] == {"vv": 1}
    res = run_query(upload("optical_sar", [opt, sar]), "Map water and built-up areas")
    assert res["status"] == "NOT_AVAILABLE"
    assert "The SAR image is a photo (JPG/PNG), not calibrated radar data" in res["answer"]
    assert "photo with only red/green/blue" in res["answer"]
    assert res["answer"].count("calibrated radar") == 1   # photo reason replaces the generic one
