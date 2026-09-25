"""Tests for the RSVQA-LR training pipeline on a tiny synthetic dataset (no downloads)."""
import json

import numpy as np
import pytest

import common
from data import load_split
from eval import majority_predictions, score
from train import build_vocab, fit, labels_for, masks_for, per_type_accuracy, predict

torch = pytest.importorskip("torch")


def write_split(folder, split, items):
    """items: list of (img_id, question, answer, type, active)."""
    images = [{"id": i, "active": True} for i in sorted({it[0] for it in items})]
    images.append({"id": 999, "active": False})
    questions, answers = [], []
    for qid, (img_id, question, answer, qtype, active) in enumerate(items):
        questions.append({"id": qid, "img_id": img_id, "type": qtype, "question": question, "active": active})
        answers.append({"id": qid, "question_id": qid, "answer": answer, "active": active})
    for key, rows in (("images", images), ("questions", questions), ("answers", answers)):
        (folder / f"LR_split_{split}_{key}.json").write_text(json.dumps({key: rows}))


def test_load_split_joins_and_skips_inactive(tmp_path):
    write_split(tmp_path, "train", [
        (1, "Is there a road?", "yes", "presence", True),
        (1, "What is the number of roads?", "12", "count", True),
        (2, "Is it a rural or an urban area", "rural", "rural_urban", False),
    ])
    records = load_split(tmp_path, "train")
    assert records == [
        {"qid": 0, "img_id": 1, "question": "Is there a road?", "answer": "yes", "type": "presence"},
        {"qid": 1, "img_id": 1, "question": "What is the number of roads?", "answer": "12", "type": "count"},
    ]


def test_load_split_rejects_unknown_split(tmp_path):
    with pytest.raises(ValueError):
        load_split(tmp_path, "holdout")


def rec(question, answer, qtype, img_id=0):
    return {"qid": 0, "img_id": img_id, "question": question, "answer": answer, "type": qtype}


def test_build_vocab_and_labels():
    records = [rec("Is there a road?", "yes", "presence"), rec("Is there a road?", "yes", "presence"),
               rec("Is there water?", "no", "presence"), rec("What is the number of roads?", "3", "count"),
               rec("What is the number of roads?", "7", "count")]
    answers, by_type = build_vocab(records, min_count=1)
    assert answers[0] == "yes"
    assert by_type == {"presence": ["no", "yes"], "count": ["3", "7"]}
    answers2, by_type2 = build_vocab(records, min_count=2)
    assert answers2 == ["yes"] and by_type2 == {"presence": ["yes"]}
    assert labels_for(records, answers2).tolist() == [0, 0, -1, -1, -1]


def test_masks_use_detected_question_type():
    answers = ["yes", "no", "3"]
    by_type = {"presence": ["yes", "no"], "count": ["3"]}
    masks = masks_for([rec("How many roads are there?", "3", "count"),
                       rec("Is there a road?", "yes", "presence")], answers, by_type)
    assert masks.tolist() == [[False, False, True], [True, True, False]]


def synthetic_task(n=400, dim=8, seed=0):
    """Answer is 'yes' when image and question embeddings point the same way."""
    rng = np.random.default_rng(seed)
    img = rng.normal(size=(n, dim)).astype("float32")
    q = rng.normal(size=(n, dim)).astype("float32")
    labels = ((img * q).sum(axis=1) > 0).astype("int64")  # 0 = yes, 1 = no
    masks = np.ones((n, 2), dtype=bool)
    return img, q, labels, masks


def test_fit_learns_and_early_stops():
    train = synthetic_task(seed=0)
    val = synthetic_task(n=200, seed=1)
    logs = []
    state, history = fit(train, val, 2, {"hidden": 32, "dropout": 0.0},
                         {"epochs": 60, "batch_size": 64, "lr": 0.01, "weight_decay": 0.0,
                          "patience": 5}, log=logs.append)
    best = max(h["val_accuracy"] for h in history)
    assert best > 0.8
    assert state is not None and len(history) <= 60


def test_fit_ignores_out_of_vocab_training_labels():
    img, q, labels, masks = synthetic_task(n=100)
    labels[:50] = -1
    state, history = fit((img, q, labels, masks), synthetic_task(n=50, seed=2), 2,
                         {"hidden": 8, "dropout": 0.0},
                         {"epochs": 2, "batch_size": 32, "lr": 0.01, "weight_decay": 0.0, "patience": 5},
                         log=lambda _: None)
    assert len(history) == 2


def test_predict_respects_masks():
    from models.vqa_head import build_network

    net = build_network(8, 8, 3, 0.0)
    img, q, _, _ = synthetic_task(n=10)
    masks = np.zeros((10, 3), dtype=bool)
    masks[:, 2] = True
    assert (predict(net, img, q, masks) == 2).all()


def test_per_type_accuracy():
    records = [rec("a", "yes", "presence"), rec("b", "no", "presence"), rec("c", "3", "count")]
    assert per_type_accuracy(np.array([0, 0, 2]), np.array([0, 1, 2]), records) == \
        {"count": 1.0, "presence": 0.5}


def test_score_oa_aa_and_count_bins():
    records = [rec("q", "yes", "presence"), rec("q", "no", "presence"),
               rec("q", "12", "count"), rec("q", "0", "count")]
    res = score(records, ["yes", "yes", "15", None])
    assert res["per_type"] == {"count": 0.0, "presence": 0.5}
    assert res["overall_accuracy"] == 0.25
    assert res["average_accuracy"] == 0.25
    assert res["count_binned_accuracy"] == 0.5    # 15 and 12 share the 11-100 bin
    assert res["answered"] == 3 and res["n"] == 4


def test_majority_baseline_uses_train_only():
    train = [rec("q", "yes", "presence"), rec("q", "yes", "presence"), rec("q", "no", "presence")]
    test = [rec("q", "no", "presence"), rec("q", "5", "count")]
    assert majority_predictions(train, test) == ["yes", None]


def test_config_paths_are_resolved_from_repo_root():
    cfg = common.load_config()
    assert cfg["output"] == common.REPO_ROOT / "data" / "models" / "vqa_head" / "rsvqa_lr_head.pt"
    assert cfg["data_dir"].is_absolute()
