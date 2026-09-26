"""Batch prediction with the same agent as POST /api/query.

Usage (PowerShell, from backend/):
    python -m app.predict --task vqa --input manifest.json --out predictions.json
    python -m app.predict --task caption --input C:\\images --out predictions.json
    python -m app.predict --task vqa --input C:\\images --question "Is it a rural or an urban area?" --out p.json

--input is either
  * a folder: every .tif/.tiff (plus .png/.jpg/.jpeg with --benchmark) becomes one single-image item,
    asked --question (default for --task caption: "Describe this image"), or
  * a manifest JSON list of items:
      {"id": "q1", "image": "a.tif", "question": "Is there a road?"}
      {"id": "c1", "mode": "bi_temporal", "images": ["t1.tif", "t2.tif"], "dates": ["2021-02-15", "2025-02-15"],
       "question": "Has built-up area increased?", "band_roles": ["blue,green,red,nir", null]}
    Relative paths are resolved against the manifest's folder.

Each prediction has a short canonical ``answer`` (e.g. "yes", "12", "urban", "increased") when the
tool provides one, else the full answer text; ``answer`` is null unless status is OK.
Uploads go to UPLOAD_DIR (git-ignored), or --work-dir.
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

IMAGE_EXTS = {".tif", ".tiff"}
BENCHMARK_EXTS = {".png", ".jpg", ".jpeg"}
DEFAULT_QUESTIONS = {"caption": "Describe this image"}


def load_items(input_path, task, question, benchmark):
    path = Path(input_path)
    if path.is_dir():
        exts = IMAGE_EXTS | (BENCHMARK_EXTS if benchmark else set())
        q = question or DEFAULT_QUESTIONS.get(task)
        if not q:
            raise SystemExit("--question is required when --input is a folder (except for --task caption)")
        return [{"id": f.stem, "image": str(f), "question": q}
                for f in sorted(path.iterdir()) if f.suffix.lower() in exts]
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("manifest must be a JSON list of items")
    base = path.parent
    out = []
    for i, item in enumerate(items):
        images = item.get("images") or [item["image"]]
        q = item.get("question") or question or DEFAULT_QUESTIONS.get(task)
        if not q:
            raise SystemExit(f"manifest item {i} has no question")
        out.append({**item, "id": str(item.get("id", i)), "question": q,
                    "images": [str(p if Path(p).is_absolute() else base / p) for p in images]})
    return out


def ingest(item, benchmark):
    """Validate and store an item's files exactly like POST /api/uploads. Returns (upload_id, reasons)."""
    from ingest import store
    from ingest.validation import validate_upload

    images = item.get("images") or [item["image"]]
    mode = item.get("mode") or ("single" if len(images) == 1 else "optical_sar")
    upload_id = store.new_upload_id()
    staged = store.staging_dir(upload_id)
    try:
        files = []
        for slot, src in enumerate(images, start=1):
            target = staged / store.stored_name(slot, src)
            shutil.copyfile(src, target)
            files.append((Path(src).name, target))
        result = validate_upload(mode, files, dates=item.get("dates"), sensors=item.get("sensors"),
                                 benchmark_mode=benchmark, band_roles=item.get("band_roles"))
        if not result["ok"]:
            return None, result["reasons"]
        for info, (_, target) in zip(result["files"], files):
            info["stored_as"] = target.name
        store.commit(upload_id, {"upload_id": upload_id, "status": "accepted", "mode": mode,
                                 "benchmark_mode": benchmark, "files": result["files"],
                                 "pair": result["pair"], "warnings": result["warnings"]})
        return upload_id, None
    finally:
        store.discard(upload_id)


def canonical(res):
    if res["status"] != "OK":
        return None
    short = res.get("details", {}).get("short_answer")
    return short if short is not None else res["answer"]


def predict(items, task, benchmark, log=print):
    from agent.controller import run_query

    predictions = []
    for n, item in enumerate(items, 1):
        t = time.perf_counter()
        upload_id, reasons = ingest(item, benchmark)
        if upload_id is None:
            pred = {"id": item["id"], "question": item["question"], "status": "REJECTED", "answer": None,
                    "confidence": None, "reasons": reasons}
        else:
            res = run_query(upload_id, item["question"])
            run_step = res["trace"]["steps"][-1]["detail"] if res["trace"]["steps"] else {}
            pred = {"id": item["id"], "question": item["question"], "status": res["status"],
                    "answer": canonical(res), "confidence": res["confidence"],
                    "task": res["trace"]["task"], "tool": res["trace"]["tool"],
                    "tool_version": res["trace"]["tool_version"],
                    "answered_by": run_step.get("answered_by"), "upload_id": upload_id,
                    "query_id": res["query_id"]}
            if res["status"] != "OK":
                pred["reason"] = res["answer"]
            if task != "auto" and res["trace"]["task"] != task:
                pred["task_mismatch"] = f"routed to '{res['trace']['task']}', not '{task}'"
        pred["seconds"] = round(time.perf_counter() - t, 3)
        predictions.append(pred)
        log(f"[{n}/{len(items)}] {pred['id']}: {pred['status']} {pred['answer']!r}")
    return predictions


def main(argv=None):
    parser = argparse.ArgumentParser(description="Batch predictions with the SatQuery AI agent.")
    parser.add_argument("--task", default="auto", choices=["auto", "vqa", "caption", "metadata", "water_builtup", "change"])
    parser.add_argument("--input", required=True, help="folder of images or manifest.json")
    parser.add_argument("--out", required=True, help="predictions JSON file to write")
    parser.add_argument("--question", default=None, help="question for every image (folder input)")
    parser.add_argument("--benchmark", action="store_true", help="also accept PNG/JPEG")
    parser.add_argument("--work-dir", default=None, help="where uploads are stored (default: UPLOAD_DIR)")
    args = parser.parse_args(argv)
    if args.work_dir:
        os.environ["UPLOAD_DIR"] = args.work_dir

    items = load_items(args.input, args.task, args.question, args.benchmark)
    started = time.perf_counter()
    predictions = predict(items, args.task, args.benchmark)
    counts = {}
    for p in predictions:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    out = {"task": args.task, "n": len(predictions), "status_counts": counts,
           "seconds": round(time.perf_counter() - started, 1), "predictions": predictions}
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: {counts}")


if __name__ == "__main__":
    sys.exit(main())
