"""Evaluate on the RSVQA-LR TEST split: accuracy per question type, OA and AA.

Compares three answerers on the same questions:
  - trained head (the artifact written by train.py),
  - zero-shot RemoteCLIP (only presence and rural/urban; others count as wrong),
  - majority baseline (most frequent TRAIN answer per question type).
Count questions are also scored after binning (0, 1-10, 11-100, 101-1000, >1000),
the convention of the original RSVQA paper, reported separately.

Usage (PowerShell, from the repo root):
    .\\.venv\\Scripts\\python.exe ml\\vqa_head\\eval.py [--config ...] [--no-zero-shot]
"""
import argparse
import collections
import json
import time

import numpy as np

import common
from data import load_split
from embed import features, split_embeddings

from models import rsvqa  # noqa: E402
from models.vqa_head import VqaHead  # noqa: E402


def score(records, predictions):
    """Per-type accuracy, overall accuracy (OA), average accuracy over types (AA),
    and binned count accuracy. ``predictions`` may contain None (= no answer)."""
    hits = collections.defaultdict(list)
    count_bin_hits = []
    for r, p in zip(records, predictions):
        hits[r["type"]].append(p == r["answer"])
        if r["type"] == rsvqa.COUNT:
            count_bin_hits.append(p is not None and rsvqa.count_bin(p) == rsvqa.count_bin(r["answer"]))
    per_type = {t: round(float(np.mean(v)), 4) for t, v in sorted(hits.items())}
    return {
        "per_type": per_type,
        "overall_accuracy": round(float(np.mean([h for v in hits.values() for h in v])), 4),
        "average_accuracy": round(float(np.mean(list(per_type.values()))), 4),
        "count_binned_accuracy": round(float(np.mean(count_bin_hits)), 4) if count_bin_hits else None,
        "answered": sum(p is not None for p in predictions),
        "n": len(records),
    }


def majority_predictions(train_records, records):
    by_type = collections.defaultdict(collections.Counter)
    for r in train_records:
        by_type[r["type"]][r["answer"]] += 1
    top = {t: c.most_common(1)[0][0] for t, c in by_type.items()}
    return [top.get(r["type"]) for r in records]


def head_predictions(head, records, img, q):
    qtypes = [rsvqa.question_type(r["question"]) for r in records]
    probs = head.probabilities(img, q, qtypes)
    best = probs.argmax(axis=1)
    return [head.answers[i] for i in best], probs[np.arange(len(best)), best]


def zero_shot_predictions(encoder, records, img):
    from models.zero_shot import Unsupported, ZeroShot

    zs = ZeroShot(encoder)
    out = []
    for r, emb in zip(records, img):
        try:
            out.append(zs.answer(emb, r["question"])[0])
        except Unsupported:
            out.append(None)
    return out


def table(results):
    types = sorted({t for res in results.values() for t in res["per_type"]})
    header = "| answerer | " + " | ".join(types) + " | OA | AA | count (binned) |"
    lines = [header, "|" + "---|" * (len(types) + 4)]
    for name, res in results.items():
        cells = [f"{res['per_type'].get(t, 0):.2%}" for t in types]
        binned = f"{res['count_binned_accuracy']:.2%}" if res["count_binned_accuracy"] is not None else "-"
        lines.append(f"| {name} | " + " | ".join(cells)
                     + f" | {res['overall_accuracy']:.2%} | {res['average_accuracy']:.2%} | {binned} |")
    return "\n".join(lines)


def main(argv=None):
    from models import remoteclip

    parser = argparse.ArgumentParser(description="Evaluate the VQA head on RSVQA-LR test.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--no-zero-shot", action="store_true")
    args = parser.parse_args(argv)
    cfg = common.load_config(args.config)
    started = time.perf_counter()

    test = load_split(cfg["data_dir"], "test")
    train = load_split(cfg["data_dir"], "train")  # only for the majority baseline
    print(f"test: {len(test)} questions on {len({r['img_id'] for r in test})} images")

    encoder = remoteclip.get_encoder()
    img, q = features(test, *split_embeddings(cfg, "test", test, encoder))
    head = VqaHead.load(cfg["output"])
    head_answers, head_conf = head_predictions(head, test, img, q)

    type_detection = float(np.mean([rsvqa.question_type(r["question"]) == r["type"] for r in test]))
    results = {"trained head": score(test, head_answers)}
    if not args.no_zero_shot:
        results["zero-shot RemoteCLIP"] = score(test, zero_shot_predictions(encoder, test, img))
    results["majority baseline"] = score(test, majority_predictions(train, test))

    out = {
        "split": "RSVQA-LR test",
        "head": {"path": str(cfg["output"]), "meta": head.meta},
        "question_type_detection_accuracy": round(type_detection, 4),
        "mean_confidence_trained_head": round(float(np.mean(head_conf)), 4),
        "results": results,
        "seconds": round(time.perf_counter() - started, 1),
    }
    report = cfg["output"].with_name("eval_test.json")
    report.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(table(results))
    print(f"question-type detection accuracy on test: {type_detection:.2%}")
    print(f"saved {report}")


if __name__ == "__main__":
    main()
