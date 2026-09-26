"""Does the fine-tuned patch model improve built-up mapping in Bengaluru? Rules-only vs rules + model.

Usage (PowerShell, from the repo root, after download_worldcover_aois.py and train.py):
    .\\.venv\\Scripts\\python.exe ml\\landcover_patch\\eval_worldcover.py

Reference: ESA WorldCover 2021 (50 built-up, 80 water, 60 bare -> other, the rest vegetation).
Rules: backend/local_analysis/landcover_change.py. Rules + model: a rule built-up pixel stays
built-up only if the model's built-up score (max P(urban_fabric), P(industrial_commercial_units))
for the 1.2 km patch around it is >= tau; otherwise it becomes "other".

tau is tuned on TUNE areas and applied to HOLDOUT areas. The decision rule was fixed before
running: wire the model in only if HOLDOUT mean built-up F1 improves by >= MIN_GAIN and no
HOLDOUT area gets worse. BigEarthNet is European and these areas are in India, so this is
also a domain-shift test.
"""
import json
import sys

import numpy as np

import common
from download_worldcover_aois import OUT as DATA

from local_analysis.grid import grid_for  # noqa: E402
from local_analysis.landcover_change import CLASS_CODES, DEFAULTS, classify, read_indices  # noqa: E402
from models.landcover_patch import PatchClassifier, prepare_input, resize_nearest  # noqa: E402
from raster.band_adapter import resolve_bands  # noqa: E402
from raster.metadata import read_metadata  # noqa: E402

TUNE, HOLDOUT = ["sarjapur", "yelahanka"], ["bellandur", "hoskote"]
MIN_GAIN = 0.03
TAUS = [round(t, 2) for t in np.arange(0.05, 0.96, 0.05)]
ROLES = ["blue", "green", "red", "nir", "swir1", "swir2"]
BUILT, OTHER = CLASS_CODES["built_up"], CLASS_CODES["other"]


def reference(path):
    import rasterio

    with rasterio.open(path) as src:
        wc = src.read(1)
    ref = np.full(wc.shape, 255, dtype="uint8")
    ref[wc == 80] = CLASS_CODES["water"]
    ref[wc == 50] = BUILT
    ref[np.isin(wc, [10, 20, 30, 40, 90, 95, 100])] = CLASS_CODES["vegetation"]
    ref[wc == 60] = OTHER
    return ref


def rule_map(path, use_swir):
    meta = read_metadata(path)
    bands = resolve_bands(meta, band_roles=ROLES)
    use = [r for r in ROLES if use_swir or not r.startswith("swir")]
    grid = grid_for(path, max_size=100_000)
    idx = read_indices(path, bands["roles"], use, grid)
    return classify(idx, idx["valid"], DEFAULTS), meta, bands


def built_scores(clf, path, meta, bands, shape):
    image, _ = prepare_input(path, meta, bands)
    scores, _ = clf.score_map(image)
    return resize_nearest(scores, shape)


def with_model(rules, scores, tau):
    out = rules.copy()
    out[(rules == BUILT) & (scores < tau)] = OTHER
    return out


def score(pred, ref):
    m = ref != 255
    p, r = pred[m], ref[m]
    tp = int(((p == BUILT) & (r == BUILT)).sum())
    prec = tp / max(1, int((p == BUILT).sum()))
    rec = tp / max(1, int((r == BUILT).sum()))
    return {"built_f1": round(2 * prec * rec / max(1e-9, prec + rec), 4), "built_precision": round(prec, 4),
            "built_recall": round(rec, 4), "overall_accuracy": round(float((p == r).mean()), 4),
            "built_percent_pred": round(float((p == BUILT).mean() * 100), 2),
            "built_percent_ref": round(float((r == BUILT).mean() * 100), 2)}


def evaluate_variant(clf, use_swir):
    areas = {}
    for name in TUNE + HOLDOUT:
        rules, meta, bands = rule_map(DATA / f"{name}_s2_2021.tif", use_swir)
        areas[name] = {"rules": rules, "ref": reference(DATA / f"{name}_wc.tif"),
                       "scores": built_scores(clf, DATA / f"{name}_s2_2021.tif", meta, bands, rules.shape)}
    tau = max(TAUS, key=lambda t: np.mean([score(with_model(areas[a]["rules"], areas[a]["scores"], t),
                                                 areas[a]["ref"])["built_f1"] for a in TUNE]))
    per_area = {a: {"rules_only": score(v["rules"], v["ref"]),
                    "rules_plus_model": score(with_model(v["rules"], v["scores"], tau), v["ref"])}
                for a, v in areas.items()}
    gains = {a: round(per_area[a]["rules_plus_model"]["built_f1"] - per_area[a]["rules_only"]["built_f1"], 4)
             for a in HOLDOUT}
    mean_gain = round(float(np.mean(list(gains.values()))), 4)
    return {"tau": tau, "per_area": per_area, "holdout_f1_gain": gains, "holdout_mean_f1_gain": mean_gain,
            "passes": mean_gain >= MIN_GAIN and all(g >= 0 for g in gains.values())}


def season_case(clf, tau):
    out = {}
    for year in (2019, 2021, 2025):
        path = DATA / (f"sarjapur_s2_{year}.tif" if year != 2021 else "sarjapur_s2_2021.tif")
        rules, meta, bands = rule_map(path, use_swir=True)
        scores = built_scores(clf, path, meta, bands, rules.shape)
        out[year] = {"rules_only_built_percent": round(float((rules == BUILT).mean() * 100), 2),
                     "rules_plus_model_built_percent": round(float((with_model(rules, scores, tau) == BUILT).mean() * 100), 2)}
    return out


def main():
    cfg = common.load_config()
    clf = PatchClassifier.load(cfg["checkpoint"])
    report = {"reference": "ESA WorldCover 2021", "min_gain": MIN_GAIN, "tune": TUNE, "holdout": HOLDOUT,
              "model": clf.trace_info,
              "primary (Sentinel-2 rules with SWIR)": evaluate_variant(clf, use_swir=True),
              "secondary (4-band rules, no SWIR, Cartosat-like)": evaluate_variant(clf, use_swir=False)}
    primary = report["primary (Sentinel-2 rules with SWIR)"]
    report["decision"] = {"wire_into_change_analysis": primary["passes"], "tau": primary["tau"]}
    report["season_case_sarjapur"] = season_case(clf, primary["tau"])
    (cfg["output_dir"] / "eval_worldcover.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    for variant in ("primary (Sentinel-2 rules with SWIR)", "secondary (4-band rules, no SWIR, Cartosat-like)"):
        v = report[variant]
        print(f"\n{variant}: tau={v['tau']} (tuned on {', '.join(TUNE)})")
        print("| area | split | F1 rules | F1 rules+model | precision | recall | built% pred/ref |")
        print("|---|---|---|---|---|---|---|")
        for a in TUNE + HOLDOUT:
            r, m = v["per_area"][a]["rules_only"], v["per_area"][a]["rules_plus_model"]
            print(f"| {a} | {'tune' if a in TUNE else 'holdout'} | {r['built_f1']:.3f} | {m['built_f1']:.3f} | "
                  f"{r['built_precision']:.3f} -> {m['built_precision']:.3f} | {r['built_recall']:.3f} -> "
                  f"{m['built_recall']:.3f} | {r['built_percent_pred']:.1f} -> {m['built_percent_pred']:.1f} / "
                  f"{r['built_percent_ref']:.1f} |")
        print(f"holdout mean F1 gain {v['holdout_mean_f1_gain']:+.4f} (need >= {MIN_GAIN}, no area worse) "
              f"-> {'PASS' if v['passes'] else 'FAIL'}")
    print(f"\ndecision: wire into change analysis = {report['decision']['wire_into_change_analysis']}")
    print("season case (Sarjapur built-up %):", json.dumps(report["season_case_sarjapur"]))


if __name__ == "__main__":
    sys.exit(main())
