"""VQA and caption tools end to end through the controller, with a fake encoder."""
import pytest

from agent.controller import run_query
from models import remoteclip
from models.zero_shot import PRESENCE_PROMPTS, RURAL_URBAN_PROMPTS, SCENE_TEMPLATE
from tests.fakes import FakeEncoder, unit


@pytest.fixture
def fake_clip(monkeypatch):
    def install(image_text):
        enc = FakeEncoder(image_vector=unit(image_text))
        monkeypatch.setattr(remoteclip, "availability", lambda: (True, None))
        monkeypatch.setattr(remoteclip, "get_encoder", lambda: enc)
        return enc
    return install


def run_step(res):
    return res["trace"]["steps"][-1]


# --- without any model -------------------------------------------------------

@pytest.mark.parametrize("question", ["Describe this image", "Is there a road?"])
def test_no_weights_means_not_available(make_upload, question):
    uid = make_upload("single", [{}])
    res = run_query(uid, question)
    assert res["status"] == "NOT_AVAILABLE"
    assert "weights not found" in res["answer"]
    assert res["confidence"] is None


# --- caption -------------------------------------------------------------------

def test_caption(make_upload, fake_clip, upload_dir):
    enc = fake_clip(SCENE_TEMPLATE.format("farmland"))
    uid = make_upload("single", [{"count": 4}])
    res = run_query(uid, "Describe this image")

    assert res["status"] == "OK"
    assert res["answer"].startswith("A satellite image of farmland")
    assert res["confidence"] == round(res["details"]["scene_scores"][0]["probability"], 4)
    assert res["trace"]["tool"] == "rs_caption" and res["trace"]["tool_version"] == "1.0.0"
    assert run_step(res)["detail"]["model"] == "fake-clip"
    assert res["evidence_images"][0]["kind"] == "preview"
    assert len(res["details"]["scene_scores"]) == 3

    # The image embedding is cached on disk: a second question does not re-encode.
    run_query(uid, "Give me a caption", params={"top_k": 1})
    assert enc.image_calls == 1
    assert (upload_dir / uid / "embeddings" / "file_1_fake-clip.npy").is_file()


def test_caption_param_limits(make_upload, fake_clip):
    fake_clip("x")
    uid = make_upload("single", [{}])
    res = run_query(uid, "Describe this image", params={"top_k": 9})
    assert res["status"] == "REJECTED" and "between 1 and 5" in res["answer"]


# --- VQA: zero-shot ----------------------------------------------------------------

def test_zero_shot_presence(make_upload, fake_clip):
    fake_clip(PRESENCE_PROMPTS["yes"].format("water area"))
    uid = make_upload("single", [{}])
    res = run_query(uid, "Is there a water area?")

    assert res["status"] == "OK" and res["answer"] == "yes"
    assert 0.5 < res["confidence"] <= 1.0
    assert res["trace"]["task"] == "vqa" and res["trace"]["rerouted_from"] == "water_builtup"
    assert run_step(res)["detail"]["answered_by"] == "zero_shot"
    assert run_step(res)["detail"]["question_type"] == "presence"
    assert res["details"]["answered_by"] == "zero_shot"


def test_zero_shot_rural_urban(make_upload, fake_clip):
    fake_clip(RURAL_URBAN_PROMPTS["rural"])
    uid = make_upload("single", [{}])
    res = run_query(uid, "Is it a rural or an urban area")
    assert (res["status"], res["answer"]) == ("OK", "rural")


def test_zero_shot_cannot_count(make_upload, fake_clip):
    fake_clip("x")
    uid = make_upload("single", [{}])
    res = run_query(uid, "How many buildings are there?")
    assert res["status"] == "NOT_AVAILABLE"
    assert "cannot answer 'count'" in res["answer"] and "no trained VQA head" in res["answer"]
    detail = run_step(res)["detail"]
    assert detail["question_type"] == "count" and detail["head_available"] is False


# --- VQA: trained head ---------------------------------------------------------------

def test_trained_head_is_preferred(make_upload, fake_clip, tmp_path, monkeypatch):
    pytest.importorskip("torch")
    from tests.test_vqa_head import make_artifact

    fake_clip(PRESENCE_PROMPTS["yes"].format("road"))
    head_path = make_artifact(tmp_path / "head.pt", bias_towards="5")
    monkeypatch.setenv("VQA_HEAD_PATH", str(head_path))
    uid = make_upload("single", [{}])

    res = run_query(uid, "How many roads are there?")
    assert res["status"] == "OK" and res["answer"] == "5"
    assert res["confidence"] == round(res["details"]["top_answers"][0]["probability"], 4)
    detail = run_step(res)["detail"]
    assert detail["answered_by"] == "trained_head"
    assert detail["head"]["trained_on"] == "unit-test"
    assert detail["question_type"] == "count"

    # Presence also goes to the head when it is installed, and the answer stays canonical.
    res = run_query(uid, "Is there a road?")
    assert res["answer"] in ("yes", "no")
    assert run_step(res)["detail"]["answered_by"] == "trained_head"


def test_broken_head_falls_back_to_zero_shot(make_upload, fake_clip, tmp_path, monkeypatch):
    fake_clip(PRESENCE_PROMPTS["no"].format("road"))
    broken = tmp_path / "broken.pt"
    broken.write_bytes(b"garbage")
    monkeypatch.setenv("VQA_HEAD_PATH", str(broken))
    uid = make_upload("single", [{}])

    res = run_query(uid, "Is there a road?")
    assert (res["status"], res["answer"]) == ("OK", "no")
    detail = run_step(res)["detail"]
    assert detail["answered_by"] == "zero_shot" and "head_error" in detail
