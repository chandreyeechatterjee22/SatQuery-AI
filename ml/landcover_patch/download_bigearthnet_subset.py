"""Download a country-balanced BigEarthNet v2 subset (RGB + NIR + labels only) from Hugging Face.

Usage (PowerShell, from the repo root):
    .\\.venv\\Scripts\\python.exe ml\\landcover_patch\\download_bigearthnet_subset.py [--dry-run]

Whole 100-patch row groups are sampled from every shard of each official split
(train / validation / test are geographically separated, so they are never
re-split). Only the needed columns are fetched with ranged reads; SWIR is
skipped. ``--dry-run`` prints the plan and download size without fetching data.
Writes <subset_dir>/{split}.parquet and selection.json (what was taken and why).
"""
import argparse
import collections
import json
import random
import sys
import time

import pyarrow as pa
import pyarrow.parquet as pq

import common

SPLITS = ("train", "validation", "test")
BLOCK = 1 << 16  # small reads: footers must not pull megabytes


def list_row_groups(fs, repo, columns):
    """[(split, file, row_group, rows, bytes_for_columns, country)] from parquet footers only."""
    out = []
    for path in sorted(fs.ls(f"datasets/{repo}/data", detail=False)):
        split = path.rsplit("/", 1)[1].split("-")[0]
        with fs.open(path, "rb", block_size=BLOCK) as fh:
            md = pq.ParquetFile(fh).metadata
        for i in range(md.num_row_groups):
            rg = md.row_group(i)
            size, country = 0, "mixed"
            for c in range(rg.num_columns):
                col = rg.column(c)
                top = col.path_in_schema.split(".")[0]
                if top in columns:
                    size += col.total_compressed_size
                if top == "country" and col.statistics is not None and col.statistics.has_min_max \
                        and col.statistics.min == col.statistics.max:
                    country = col.statistics.min
            out.append({"split": split, "file": path, "row_group": i, "rows": rg.num_rows,
                        "bytes": size, "country": country})
    return out


def select(groups, target_rows, max_share, rng):
    """Pick row groups so no country exceeds ``max_share`` of the rows, spreading across shards."""
    by_country = collections.defaultdict(list)
    for g in groups:
        by_country[g["country"]].append(g)
    for lst in by_country.values():
        rng.shuffle(lst)
    total = sum(g["rows"] for g in groups)
    cap = max_share * target_rows
    quota = {c: min(cap, target_rows * sum(g["rows"] for g in lst) / total) for c, lst in by_country.items()}
    # Hand the rows removed by the cap to the uncapped countries, proportionally.
    spare = target_rows - sum(quota.values())
    open_ = [c for c in quota if quota[c] < cap]
    while spare > 1 and open_:
        weight = sum(quota[c] for c in open_)
        for c in open_:
            quota[c] = min(cap, quota[c] + spare * quota[c] / weight)
        spare = target_rows - sum(quota.values())
        open_ = [c for c in quota if quota[c] < cap - 1e-9]
    picked = []
    for c, lst in by_country.items():
        rows = 0
        for g in lst:
            if rows >= quota[c]:
                break
            picked.append(g)
            rows += g["rows"]
    return picked


def _read_group(fs, g, columns):
    # cache_type="none": each column chunk is one exact ranged request (no over-fetch).
    with fs.open(g["file"], "rb", cache_type="none") as fh:
        return pq.ParquetFile(fh).read_row_group(g["row_group"], columns=columns)


def fetch(fs, groups, columns, out_path, workers=8):
    """Fetch row groups in parallel (latency-bound requests), keep a deterministic order."""
    from concurrent.futures import ThreadPoolExecutor

    ordered = sorted(groups, key=lambda g: (g["file"], g["row_group"]))
    t0 = time.perf_counter()
    tables = [None] * len(ordered)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_read_group, fs, g, columns): i for i, g in enumerate(ordered)}
        for done, fut in enumerate(futures, 1):
            tables[futures[fut]] = fut.result()
            if done % 10 == 0 or done == len(ordered):
                print(f"  {out_path.stem}: {done}/{len(ordered)} row groups ({time.perf_counter() - t0:.0f} s)",
                      flush=True)
    table = pa.concat_tables(tables)
    pq.write_table(table, out_path, compression="zstd")
    return table.num_rows


def main(argv=None):
    from huggingface_hub import HfFileSystem

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    cfg = common.load_config(args.config)
    ds = cfg["dataset"]
    fs = HfFileSystem()
    rng = random.Random(ds["seed"])

    print("reading parquet footers ...", flush=True)
    groups = list_row_groups(fs, ds["repo"], set(ds["columns"]))
    plan = {}
    for split in SPLITS:
        picked = select([g for g in groups if g["split"] == split], ds["patches"][split],
                        ds["max_country_share"], rng)
        plan[split] = picked
        rows = sum(g["rows"] for g in picked)
        size = sum(g["bytes"] for g in picked)
        countries = collections.Counter()
        for g in picked:
            countries[g["country"]] += g["rows"]
        print(f"{split:10s} {rows:6d} patches, {len(picked)} row groups from "
              f"{len({g['file'] for g in picked})} shards, {size / 1e9:.3f} GB")
        print(f"           countries: {dict(countries.most_common())}")
    total = sum(g["bytes"] for p in plan.values() for g in p)
    print(f"total download: {total / 1e9:.3f} GB")
    if args.dry_run:
        return

    out = ds["subset_dir"]
    out.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        n = fetch(fs, plan[split], ds["columns"], out / f"{split}.parquet")
        print(f"saved {split}.parquet ({n} patches)")
    (out / "selection.json").write_text(json.dumps(
        {"repo": ds["repo"], "columns": ds["columns"], "seed": ds["seed"],
         "max_country_share": ds["max_country_share"],
         "row_groups": {s: [{k: g[k] for k in ("file", "row_group", "rows", "country")} for g in p]
                        for s, p in plan.items()}}, indent=1), encoding="utf-8")
    print(f"subset ready in {out}")


if __name__ == "__main__":
    sys.exit(main())
