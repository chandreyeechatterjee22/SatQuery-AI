"""Before-vs-after on the held-out BigEarthNet TEST subset (linear probe vs full fine-tune).

Usage (PowerShell, from the repo root):
    .\\.venv\\Scripts\\python.exe ml\\landcover_patch\\eval.py [--config ...]

Reports micro mAP, macro mAP, macro F1 (threshold 0.5) and per-class AP for both
checkpoints, and writes eval_test.json next to them.
"""
import argparse
import json
import time

import numpy as np

import common
from data import Split
from metrics import evaluate

from models.landcover_patch import CLASS_NAMES, PatchClassifier  # noqa: E402


def run(checkpoint, split, batch=256):
    clf = PatchClassifier.load(checkpoint)
    probs = []
    for s in range(0, len(split), batch):
        probs.append(clf.predict_patches(np.stack([split.x(i) for i in range(s, min(s + batch, len(split)))])))
    return clf, evaluate(split.labels, np.concatenate(probs), CLASS_NAMES)


def table(before, after):
    rows = ["| metric | before (linear probe) | after (fine-tuned) | change |", "|---|---|---|---|"]
    for key, label in (("micro_map", "micro mAP"), ("macro_map", "macro mAP"), ("macro_f1", "macro F1 @0.5")):
        rows.append(f"| {label} | {before[key]:.4f} | {after[key]:.4f} | {after[key] - before[key]:+.4f} |")
    rows += ["", "| class | AP before | AP after |", "|---|---|---|"]
    for name in CLASS_NAMES:
        b, a = before["per_class_ap"][name], after["per_class_ap"][name]
        rows.append(f"| {name} | {'-' if b is None else f'{b:.3f}'} | {'-' if a is None else f'{a:.3f}'} |")
    return "\n".join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate before/after on BigEarthNet test.")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    cfg = common.load_config(args.config)
    import torch

    torch.set_num_threads(cfg["train"]["num_threads"])
    t = time.perf_counter()
    test = Split(cfg["dataset"]["subset_dir"] / "test.parquet")
    print(f"test: {len(test)} patches")
    _, before = run(cfg["output_dir"] / "probe.pt", test)
    clf, after = run(cfg["checkpoint"], test)
    report = {"split": "BigEarthNet v2 test subset (official test split, held out)", "n": len(test),
              "model": clf.trace_info, "before_linear_probe": before, "after_finetuned": after,
              "seconds": round(time.perf_counter() - t, 1)}
    (cfg["output_dir"] / "eval_test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(table(before, after))
    print(f"saved {cfg['output_dir'] / 'eval_test.json'}")


if __name__ == "__main__":
    main()
