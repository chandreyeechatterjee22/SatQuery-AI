"""Train the VQA head on RSVQA-LR TRAIN; select the best epoch on VAL. TEST is never read.

Usage (PowerShell, from the repo root):
    .\\.venv\\Scripts\\python.exe ml\\vqa_head\\train.py [--config ml\\vqa_head\\config.yaml]
"""
import argparse
import collections
import copy
import json
import time
from datetime import datetime, timezone

import numpy as np

import common
from data import load_split
from embed import features, split_embeddings

from models import rsvqa  # noqa: E402  (backend import, set up by common)
from models.vqa_head import ARTIFACT_FORMAT, build_network, type_mask  # noqa: E402

MASKED_LOGIT = -1e9


def build_vocab(records, min_count=1):
    """Answer list (most frequent first) and, per question type, the answers seen in TRAIN."""
    counts = collections.Counter(r["answer"] for r in records)
    answers = [a for a, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])) if c >= min_count]
    kept = set(answers)
    by_type = collections.defaultdict(set)
    for r in records:
        if r["answer"] in kept:
            by_type[r["type"]].add(r["answer"])
    return answers, {t: sorted(v) for t, v in by_type.items()}


def labels_for(records, answers):
    index = {a: i for i, a in enumerate(answers)}
    return np.array([index.get(r["answer"], -1) for r in records])


def masks_for(records, answers, answers_by_type):
    """Mask per record from the DETECTED question type, exactly as at serve time."""
    cache = {}
    rows = []
    for r in records:
        qtype = rsvqa.question_type(r["question"])
        if qtype not in cache:
            cache[qtype] = type_mask(answers, answers_by_type, qtype)
        rows.append(cache[qtype])
    return np.stack(rows)


def fit(train, val, n_answers, net_cfg, train_cfg, seed=0, log=print):
    """Train with early stopping on val accuracy.

    ``train``/``val`` are tuples (img, q, labels, masks) of numpy arrays; val labels
    may be -1 (answer not in vocabulary: always counted wrong).
    Returns (best_state_dict, history).
    """
    import torch

    torch.manual_seed(seed)
    np.random.seed(seed)
    dim = train[0].shape[1]
    net = build_network(dim, net_cfg["hidden"], n_answers, net_cfg["dropout"])
    opt = torch.optim.AdamW(net.parameters(), lr=train_cfg["lr"], weight_decay=train_cfg["weight_decay"])
    loss_fn = torch.nn.CrossEntropyLoss()

    keep = train[2] >= 0
    t_img, t_q, t_y, t_m = (torch.from_numpy(a[keep]) for a in train)
    t_y = t_y.long()
    best_acc, best_state, bad_epochs, history = -1.0, None, 0, []

    for epoch in range(1, train_cfg["epochs"] + 1):
        net.train()
        order = torch.randperm(len(t_y))
        total = 0.0
        for start in range(0, len(order), train_cfg["batch_size"]):
            idx = order[start:start + train_cfg["batch_size"]]
            logits = net(t_img[idx], t_q[idx]).masked_fill(~t_m[idx], MASKED_LOGIT)
            loss = loss_fn(logits, t_y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(idx)

        val_acc = accuracy(net, *val)
        history.append({"epoch": epoch, "train_loss": round(total / len(t_y), 4), "val_accuracy": round(val_acc, 4)})
        log(f"epoch {epoch:3d}  train_loss {total / len(t_y):.4f}  val_acc {val_acc:.4f}")
        if val_acc > best_acc:
            best_acc, best_state, bad_epochs = val_acc, copy.deepcopy(net.state_dict()), 0
        else:
            bad_epochs += 1
            if bad_epochs >= train_cfg["patience"]:
                log(f"early stop: no val improvement for {bad_epochs} epochs")
                break
    return best_state, history


def predict(net, img, q, masks, batch_size=4096):
    import torch

    net.eval()
    out = []
    with torch.inference_mode():
        for s in range(0, len(img), batch_size):
            logits = net(torch.from_numpy(img[s:s + batch_size]), torch.from_numpy(q[s:s + batch_size]))
            logits = logits.masked_fill(~torch.from_numpy(masks[s:s + batch_size]), MASKED_LOGIT)
            out.append(logits.argmax(dim=1).numpy())
    return np.concatenate(out)


def accuracy(net, img, q, labels, masks):
    return float((predict(net, img, q, masks) == labels).mean())


def per_type_accuracy(pred, labels, records):
    hits = collections.defaultdict(list)
    for p, y, r in zip(pred, labels, records):
        hits[r["type"]].append(p == y)
    return {t: round(float(np.mean(v)), 4) for t, v in sorted(hits.items())}


def main(argv=None):
    import torch

    from models import remoteclip

    parser = argparse.ArgumentParser(description="Train the RSVQA-LR VQA head.")
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)
    cfg = common.load_config(args.config)
    started = time.perf_counter()

    train_records = load_split(cfg["data_dir"], "train")
    val_records = load_split(cfg["data_dir"], "val")
    print(f"train: {len(train_records)} questions, val: {len(val_records)} questions")

    encoder = remoteclip.get_encoder()
    answers, answers_by_type = build_vocab(train_records, cfg["answers"]["min_count"])
    print(f"answer vocabulary: {len(answers)} (from TRAIN, min_count={cfg['answers']['min_count']})")

    def arrays(split, records):
        img, q = features(records, *split_embeddings(cfg, split, records, encoder))
        return img, q, labels_for(records, answers), masks_for(records, answers, answers_by_type)

    train = arrays("train", train_records)
    val = arrays("val", val_records)
    print(f"train questions with in-vocabulary answers: {int((train[2] >= 0).sum())}; "
          f"val questions whose answer is out of vocabulary (always wrong): {int((val[2] < 0).sum())}")

    best_state, history = fit(train, val, len(answers), cfg["network"], cfg["train"], cfg["seed"])
    net = build_network(train[0].shape[1], cfg["network"]["hidden"], len(answers), cfg["network"]["dropout"])
    net.load_state_dict(best_state)
    val_pred = predict(net, val[0], val[1], val[3])
    val_acc = float((val_pred == val[2]).mean())
    val_per_type = per_type_accuracy(val_pred, val[2], val_records)

    meta = {
        "trained_on": "RSVQA-LR train split (best epoch chosen on val)",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "encoder": encoder.model_id,
        "val_accuracy": round(val_acc, 4),
        "val_accuracy_per_type": val_per_type,
        "n_train_questions": int((train[2] >= 0).sum()),
        "best_epoch": max(history, key=lambda h: h["val_accuracy"])["epoch"],
        "config": {k: (str(v) if k in common.PATH_KEYS else v) for k, v in cfg.items()},
    }
    out = cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"format": ARTIFACT_FORMAT,
                "network": {"dim": int(train[0].shape[1]), **cfg["network"]},
                "state_dict": best_state, "answers": answers,
                "answers_by_type": answers_by_type, "meta": meta}, out)
    log_path = out.with_name("train_log.json")
    log_path.write_text(json.dumps({"meta": meta, "history": history}, indent=2), encoding="utf-8")
    print(f"saved {out} ({out.stat().st_size / 1e6:.1f} MB) and {log_path.name}")
    print(f"val accuracy {val_acc:.4f}  per type {val_per_type}")
    print(f"total time {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
