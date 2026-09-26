"""Train the 4-band land-cover classifier: linear probe ("before"), then full fine-tune ("after").

Usage (PowerShell, from the repo root):
    .\\.venv\\Scripts\\python.exe ml\\landcover_patch\\train.py [--config ...] [--device cpu|cuda]

TRAIN is used for fitting, VALIDATION for model selection. TEST is only read by eval.py.
Writes probe.pt (before), resnet18_4band_ben.pt (after) and train_log.json to output_dir.
ImageNet weights are cached under <output_dir>/torch_hub (git-ignored).
"""
import argparse
import copy
import json
import os
import time
from datetime import datetime, timezone

import numpy as np

import common
from data import Split, band_stats, torch_dataset
from metrics import evaluate

from models.landcover_patch import ARTIFACT_FORMAT, BANDS, CLASS_NAMES, MODEL_NAME, build_network  # noqa: E402

VERSION = "1.0.0"


def artifact(net, mean, std, meta):
    return {"format": ARTIFACT_FORMAT, "arch": "resnet18", "bands": list(BANDS), "class_names": CLASS_NAMES,
            "mean": list(map(float, mean)), "std": list(map(float, std)),
            "state_dict": {k: v.detach().cpu() for k, v in net.state_dict().items()}, "meta": meta}


def predict(net, loader, device):
    import torch

    net.eval()
    probs, ys = [], []
    with torch.inference_mode():
        for x, y in loader:
            probs.append(torch.sigmoid(net(x.to(device))).cpu().numpy())
            ys.append(y.numpy())
    return np.concatenate(ys), np.concatenate(probs)


def features(net, loader, device):
    """512-d pooled features from the frozen backbone (fc replaced by identity)."""
    import torch

    fc, net.fc = net.fc, torch.nn.Identity()
    try:
        return predict_raw(net, loader, device)
    finally:
        net.fc = fc


def predict_raw(net, loader, device):
    import torch

    net.eval()
    out, ys = [], []
    with torch.inference_mode():
        for x, y in loader:
            out.append(net(x.to(device)).cpu().numpy())
            ys.append(y.numpy())
    return np.concatenate(out), np.concatenate(ys)


def train_probe(net, train_feats, val_feats, cfg, device, log):
    """Fit only the linear head on cached features; keep the epoch with the best val micro mAP."""
    import torch

    head = net.fc
    opt = torch.optim.AdamW(head.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    lossf = torch.nn.BCEWithLogitsLoss()
    xt, yt = (torch.from_numpy(a).to(device) for a in train_feats)
    xv, yv = val_feats
    best, best_state = -1, None
    for epoch in range(1, cfg["epochs"] + 1):
        head.train()
        perm = torch.randperm(len(xt))
        for s in range(0, len(perm), 256):
            i = perm[s:s + 256]
            opt.zero_grad()
            lossf(head(xt[i]), yt[i]).backward()
            opt.step()
        head.eval()
        with torch.inference_mode():
            pv = torch.sigmoid(head(torch.from_numpy(xv).to(device))).cpu().numpy()
        m = evaluate(yv, pv, CLASS_NAMES)["micro_map"]
        if m > best:
            best, best_state = m, copy.deepcopy(head.state_dict())
        if epoch % 5 == 0 or epoch == cfg["epochs"]:
            log(f"probe epoch {epoch:3d}  val micro mAP {m:.4f}")
    head.load_state_dict(best_state)
    return best


def finetune(net, train_loader, val_loader, cfg, device, log):
    import torch

    opt = torch.optim.AdamW(net.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=cfg["epochs"] * len(train_loader))
    lossf = torch.nn.BCEWithLogitsLoss()
    best, best_state, bad, history = -1, None, 0, []
    for epoch in range(1, cfg["epochs"] + 1):
        net.train()
        t0, total, seen = time.perf_counter(), 0.0, 0
        for step, (x, y) in enumerate(train_loader, 1):
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = lossf(net(x), y)
            loss.backward()
            opt.step()
            sched.step()
            total += loss.item() * len(x)
            seen += len(x)
            if step % 50 == 0:
                log(f"  epoch {epoch} step {step}/{len(train_loader)}  loss {total / seen:.4f}  "
                    f"{(time.perf_counter() - t0) / seen * 1000:.1f} ms/patch")
        yv, pv = predict(net, val_loader, device)
        m = evaluate(yv, pv, CLASS_NAMES)
        history.append({"epoch": epoch, "train_loss": round(total / seen, 4), "val_micro_map": m["micro_map"],
                        "val_macro_map": m["macro_map"], "minutes": round((time.perf_counter() - t0) / 60, 1)})
        log(f"finetune epoch {epoch}  loss {total / seen:.4f}  val micro mAP {m['micro_map']:.4f}  "
            f"macro mAP {m['macro_map']:.4f}  ({history[-1]['minutes']} min)")
        if m["micro_map"] > best:
            best, best_state, bad = m["micro_map"], copy.deepcopy(net.state_dict()), 0
        else:
            bad += 1
            if bad >= cfg["patience"]:
                log(f"early stop after {bad} epochs without improvement")
                break
    net.load_state_dict(best_state)
    return best, history


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train the BigEarthNet 4-band land-cover classifier.")
    parser.add_argument("--config", default=None)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    cfg = common.load_config(args.config)
    out = cfg["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TORCH_HOME", str(out / "torch_hub"))

    import torch

    torch.manual_seed(cfg["train"]["seed"])
    torch.set_num_threads(cfg["train"]["num_threads"])
    started = time.perf_counter()
    lines = []

    def log(msg):
        print(msg, flush=True)
        lines.append(msg)

    sub = cfg["dataset"]["subset_dir"]
    train, val = Split(sub / "train.parquet"), Split(sub / "validation.parquet")
    log(f"train {len(train)} patches, validation {len(val)} patches")
    mean, std = band_stats(train)
    log(f"band mean {np.round(mean, 1).tolist()}  std {np.round(std, 1).tolist()}")

    bs = cfg["train"]["batch_size"]
    workers = cfg["train"].get("num_workers", 0)  # 0 on Windows; >0 on Linux/Colab
    DL = lambda ds, shuffle: torch.utils.data.DataLoader(ds, batch_size=bs, shuffle=shuffle, num_workers=workers,
                                                        pin_memory=args.device == "cuda")
    plain_train = DL(torch_dataset(train, mean, std), False)
    val_loader = DL(torch_dataset(val, mean, std), False)
    aug_train = DL(torch_dataset(train, mean, std, augment=cfg["train"]["augment"]), True)

    net = build_network(imagenet_init=True).to(args.device)
    base_meta = {"version": VERSION, "model": MODEL_NAME, "bands": list(BANDS), "input": "reflectance x 10000 at 10 m",
                 "trained_on": f"BigEarthNet v2 subset ({len(train)} train patches, official splits)",
                 "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    # "Before": ImageNet backbone frozen, linear head only.
    t = time.perf_counter()
    train_feats = features(net, plain_train, args.device)
    val_feats = features(net, val_loader, args.device)
    log(f"probe features extracted in {time.perf_counter() - t:.0f} s")
    probe_best = train_probe(net, train_feats, val_feats, cfg["train"]["probe"], args.device, log)
    torch.save(artifact(net, mean, std, {**base_meta, "stage": "linear_probe", "val_micro_map": probe_best}),
               out / "probe.pt")
    log(f"saved probe.pt (val micro mAP {probe_best:.4f})")

    # "After": full fine-tune, starting from the probe head (LP-FT).
    ft_best, history = finetune(net, aug_train, val_loader, cfg["train"]["finetune"], args.device, log)
    torch.save(artifact(net, mean, std, {**base_meta, "stage": "finetuned", "val_micro_map": ft_best}),
               cfg["checkpoint"])
    total_min = (time.perf_counter() - started) / 60
    log(f"saved {cfg['checkpoint'].name} (val micro mAP {ft_best:.4f}); total {total_min:.1f} min")
    (out / "train_log.json").write_text(json.dumps(
        {"meta": base_meta, "probe_val_micro_map": probe_best, "finetune_val_micro_map": ft_best,
         "history": history, "band_mean": mean, "band_std": std, "minutes": round(total_min, 1),
         "log": lines}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
