import json

import pytest

from app import predict
from tests.scenes import bitemporal_scene
from tests.synthetic import make_geotiff


def test_folder_input_with_question(tmp_path, upload_dir):
    folder = tmp_path / "imgs"
    folder.mkdir()
    make_geotiff(folder / "a.tif", count=4)
    make_geotiff(folder / "b.tif", count=13)
    (folder / "notes.txt").write_text("ignored")
    out = tmp_path / "p.json"
    predict.main(["--task", "metadata", "--input", str(folder), "--question", "How many bands does this image have?",
                  "--out", str(out)])
    data = json.loads(out.read_text())
    assert data["n"] == 2 and data["status_counts"] == {"OK": 2}
    by_id = {p["id"]: p for p in data["predictions"]}
    assert "4 band(s)" in by_id["a"]["answer"] and "13 band(s)" in by_id["b"]["answer"]
    assert by_id["a"]["tool"] == "image_metadata" and "task_mismatch" not in by_id["a"]


def test_folder_without_question_needs_one(tmp_path):
    with pytest.raises(SystemExit, match="--question is required"):
        predict.load_items(tmp_path, "vqa", None, False)


def test_caption_default_question_and_not_available_is_honest(tmp_path, upload_dir):
    folder = tmp_path / "imgs"
    folder.mkdir()
    make_geotiff(folder / "a.tif", count=4)
    out = tmp_path / "p.json"
    predict.main(["--task", "caption", "--input", str(folder), "--out", str(out)])
    p = json.loads(out.read_text())["predictions"][0]
    assert p["question"] == "Describe this image"
    assert p["status"] == "NOT_AVAILABLE" and p["answer"] is None and p["confidence"] is None
    assert "weights not found" in p["reason"]


def test_manifest_bitemporal_short_answer_and_rejection(tmp_path, upload_dir):
    before, after = bitemporal_scene()
    make_geotiff(tmp_path / "t1.tif", count=4, data=before)
    make_geotiff(tmp_path / "t2.tif", count=4, data=after)
    make_geotiff(tmp_path / "far.tif", count=4, origin=(900000.0, 1440000.0))
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([
        {"id": "c1", "mode": "bi_temporal", "images": ["t1.tif", "t2.tif"], "dates": ["2021-01-01", "2025-01-01"],
         "sensors": ["cartosat2s", "cartosat2s"], "question": "Has built-up area increased?"},
        {"id": "bad", "mode": "bi_temporal", "images": ["t1.tif", "far.tif"], "dates": ["2021-01-01", "2025-01-01"],
         "question": "What changed?"},
    ]))
    out = tmp_path / "p.json"
    predict.main(["--task", "change", "--input", str(manifest), "--out", str(out)])
    preds = {p["id"]: p for p in json.loads(out.read_text())["predictions"]}
    assert preds["c1"]["status"] == "OK" and preds["c1"]["answer"] == "increased"
    assert preds["bad"]["status"] == "REJECTED" and preds["bad"]["reasons"][0]["code"] == "no_overlap"


def test_task_mismatch_is_flagged(tmp_path, upload_dir):
    make_geotiff(tmp_path / "a.tif", count=4)
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"id": "x", "image": "a.tif", "question": "What is the CRS?"}]))
    out = tmp_path / "p.json"
    predict.main(["--task", "vqa", "--input", str(manifest), "--out", str(out)])
    p = json.loads(out.read_text())["predictions"][0]
    assert p["status"] == "OK" and p["task_mismatch"] == "routed to 'metadata', not 'vqa'"
