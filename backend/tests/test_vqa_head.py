import os
import time

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from models import vqa_head  # noqa: E402
from models.vqa_head import ARTIFACT_FORMAT, VqaHead, build_network, type_mask  # noqa: E402
from tests.fakes import DIM  # noqa: E402

ANSWERS = ["yes", "no", "0", "5", "rural", "urban"]
BY_TYPE = {"presence": ["yes", "no"], "comp": ["yes", "no"], "count": ["0", "5"],
           "rural_urban": ["rural", "urban"]}


def make_artifact(path, bias_towards="5", seed=0):
    torch.manual_seed(seed)
    net = build_network(DIM, 16, len(ANSWERS), 0.0)
    with torch.no_grad():
        net.mlp[-1].bias.zero_()
        net.mlp[-1].bias[ANSWERS.index(bias_towards)] = 50.0
    torch.save({"format": ARTIFACT_FORMAT,
                "network": {"dim": DIM, "hidden": 16, "dropout": 0.0},
                "state_dict": net.state_dict(), "answers": ANSWERS, "answers_by_type": BY_TYPE,
                "meta": {"trained_on": "unit-test", "created": "2026-09-26", "val_accuracy": 0.5}},
               path)
    return path


def vec(seed):
    v = np.random.default_rng(seed).normal(size=DIM)
    return (v / np.linalg.norm(v)).astype("float32")


def test_type_mask():
    assert type_mask(ANSWERS, BY_TYPE, "count").tolist() == [False, False, True, True, False, False]
    assert type_mask(ANSWERS, BY_TYPE, "other").all()


def test_predict_masks_answers_by_question_type(tmp_path):
    head = VqaHead.load(make_artifact(tmp_path / "h.pt", bias_towards="5"))
    answer, prob, qtype, top = head.predict(vec(1), vec(2), "How many roads are there?")
    assert (answer, qtype) == ("5", "count") and prob > 0.99
    # The same network cannot answer "5" to a yes/no question.
    answer, prob, qtype, top = head.predict(vec(1), vec(2), "Is there a road?")
    assert qtype == "presence" and answer in ("yes", "no")
    assert np.isclose(sum(p for _, p in top), 1.0, atol=1e-6)


def test_probabilities_sum_to_one_per_row(tmp_path):
    head = VqaHead.load(make_artifact(tmp_path / "h.pt"))
    probs = head.probabilities(np.stack([vec(1), vec(3)]), np.stack([vec(2), vec(4)]),
                               ["count", "other"])
    assert np.allclose(probs.sum(axis=1), 1.0)
    assert probs[0, ANSWERS.index("yes")] == 0.0


def test_meta_is_kept(tmp_path):
    head = VqaHead.load(make_artifact(tmp_path / "h.pt"))
    assert head.meta["trained_on"] == "unit-test" and head.answers == ANSWERS


def test_bad_format_rejected(tmp_path):
    path = tmp_path / "bad.pt"
    torch.save({"format": 99}, path)
    with pytest.raises(ValueError, match="unsupported VQA head format"):
        VqaHead.load(path)


def test_availability_and_get_head(tmp_path, monkeypatch):
    path = tmp_path / "head.pt"
    monkeypatch.setenv("VQA_HEAD_PATH", str(path))
    ok, reason = vqa_head.availability()
    assert not ok and "train it with ml/vqa_head/train.py" in reason
    assert vqa_head.get_head() is None

    make_artifact(path, bias_towards="5")
    assert vqa_head.availability() == (True, None)
    head = vqa_head.get_head()
    assert head.predict(vec(1), vec(2), "How many?")[0] == "5"
    assert vqa_head.get_head() is head  # cached

    make_artifact(path, bias_towards="0")
    later = time.time() + 5
    os.utime(path, (later, later))  # make sure the mtime changes
    assert vqa_head.get_head().predict(vec(1), vec(2), "How many?")[0] == "0"
