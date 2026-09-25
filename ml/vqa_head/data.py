"""Read RSVQA-LR split files into flat (image, question, answer, type) records."""
import json
from pathlib import Path

SPLITS = ("train", "val", "test")


def load_split(data_dir, split):
    """Active questions of one split, joined with their answers.

    Returns a list of dicts: qid, img_id, question, answer, type.
    """
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}")
    data_dir = Path(data_dir)
    images = _read(data_dir / f"LR_split_{split}_images.json", "images")
    questions = _read(data_dir / f"LR_split_{split}_questions.json", "questions")
    answers = _read(data_dir / f"LR_split_{split}_answers.json", "answers")

    active_images = {im["id"] for im in images if im.get("active")}
    answer_by_qid = {a["question_id"]: a["answer"] for a in answers if a.get("active")}
    records = []
    for q in questions:
        if not q.get("active") or q["img_id"] not in active_images or q["id"] not in answer_by_qid:
            continue
        records.append({"qid": q["id"], "img_id": q["img_id"], "question": q["question"],
                        "answer": str(answer_by_qid[q["id"]]), "type": q["type"]})
    return records


def image_path(data_dir, img_id):
    return Path(data_dir) / "Images_LR" / f"{img_id}.tif"


def _read(path, key):
    with open(path, encoding="utf-8") as f:
        return json.load(f)[key]
