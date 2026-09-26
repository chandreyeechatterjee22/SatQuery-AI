"""Bi-temporal land-cover change: classify each date, compare, report per-class deltas.

Classes: water, built_up, vegetation, other (rule-based on spectral indices).
Both dates are put on the earlier date's grid and only pixels valid on both
dates are compared. All reported numbers are rounded first and deltas are
computed from the rounded values, so the text, the numbers and the direction
words ("increased" / "decreased" / "unchanged") always agree.
"""
import itertools

import numpy as np

from local_analysis.grid import grid_for, pixel_area_m2, read_on_grid
from local_analysis.indices import normalized_difference

CLASSES = ("water", "built_up", "vegetation", "other")
CLASS_LABELS = {"water": "Water", "built_up": "Built-up", "vegetation": "Vegetation", "other": "Other"}
CLASS_CODES = {c: i for i, c in enumerate(CLASSES)}
NODATA_CODE = 255

DEFAULTS = {
    "water_threshold": 0.0,        # MNDWI / NDWI above -> water
    "vegetation_ndvi": 0.3,        # NDVI above -> vegetation
    "builtup_threshold": 0.0,      # NDBI above -> built-up (with SWIR)
    "ndvi_max_builtup": 0.2,       # without SWIR: NDVI below -> built-up proxy
    "unchanged_tolerance_pp": 1.0,  # |delta| below this (percentage points) -> unchanged
    "max_size": 1024,
}
ROBUSTNESS_SHIFT = 0.05
REQUIRED_ROLES = ("green", "red", "nir")

# Season check. Index rules count dry bare fields as built-up, so two dates in a
# different state of greenness produce fake built-up/vegetation change (e.g. Sarjapur
# Road, Bengaluru, Jan-Mar composites: built-up 63.6% in dry 2019 vs 31.9% in 2021,
# against 26.3% in ESA WorldCover 2021). The 90th-percentile NDVI (the greenest
# pixels) moves with season/rainfall but barely with real conversion of some
# vegetation to built-up. These constants are heuristics.
SEASON_NDVI_PERCENTILE = 90
SEASON_WARNING_GAP = 0.05
SEASON_ZERO_CONFIDENCE_GAP = 0.15
SEASON_SENSITIVE = ("built_up", "vegetation", "other")

INCREASED, DECREASED, UNCHANGED = "increased", "decreased", "unchanged"


class MissingBands(ValueError):
    """The images lack the bands needed to classify land cover."""


def common_roles(bands_a, bands_b):
    return sorted(set(bands_a["roles"]) & set(bands_b["roles"]))


def read_indices(path, roles, use_roles, grid):
    """Index arrays for one date on ``grid``: ndvi, water index, built-up index (or None)."""
    wanted = [r for r in ("green", "red", "nir", "swir1") if r in use_roles]
    arrays = dict(zip(wanted, read_on_grid(path, [roles[r] for r in wanted], grid)))
    valid = np.ones(grid.shape, dtype=bool)
    for arr in arrays.values():
        valid &= np.isfinite(arr)
    has_swir = "swir1" in arrays
    return {
        "valid": valid,
        "ndvi": normalized_difference(arrays["nir"], arrays["red"]),
        "water": normalized_difference(arrays["green"], arrays["swir1" if has_swir else "nir"]),
        "built": normalized_difference(arrays["swir1"], arrays["nir"]) if has_swir else None,
    }


def classify(idx, valid, params):
    """Per-pixel class codes (uint8), NODATA_CODE outside ``valid``."""
    water = idx["water"] > params["water_threshold"]
    veg = ~water & (idx["ndvi"] > params["vegetation_ndvi"])
    if idx["built"] is not None:
        built_signal = idx["built"] > params["builtup_threshold"]
    else:
        built_signal = idx["ndvi"] < params["ndvi_max_builtup"]
    built = ~water & ~veg & built_signal
    out = np.full(valid.shape, CLASS_CODES["other"], dtype="uint8")
    out[built] = CLASS_CODES["built_up"]
    out[veg] = CLASS_CODES["vegetation"]
    out[water] = CLASS_CODES["water"]
    out[~valid] = NODATA_CODE
    return out


def direction(delta_pp, tolerance_pp):
    if abs(delta_pp) < tolerance_pp:
        return UNCHANGED
    return INCREASED if delta_pp > 0 else DECREASED


def analyse_change(before, after, params=None):
    """``before``/``after``: dicts with path, bands (band profile) and date (ISO string).

    Returns {"grid", "maps", "classes", "transitions", "changed_percent", "valid_pixels",
    "valid_area_km2", "methods", "warnings", "robustness"}.
    """
    params = {**DEFAULTS, **(params or {})}
    warnings = []
    shared = common_roles(before["bands"], after["bands"])
    missing = [r for r in REQUIRED_ROLES if r not in shared]
    if missing:
        raise MissingBands(f"both dates need {', '.join(REQUIRED_ROLES)} bands; missing on at least "
                           f"one date: {', '.join(missing)}")
    if "swir1" not in shared:
        warnings.append("No SWIR band on both dates: built-up uses a low-NDVI proxy, which also "
                        "counts bare soil as built-up.")
    extra = sorted((set(before["bands"]["roles"]) | set(after["bands"]["roles"])) - set(shared))
    if extra:
        warnings.append(f"Bands only present on one date were ignored: {', '.join(extra)}.")

    grid = grid_for(before["path"], params["max_size"])
    idx_b = read_indices(before["path"], before["bands"]["roles"], shared, grid)
    idx_a = read_indices(after["path"], after["bands"]["roles"], shared, grid)
    valid = idx_b["valid"] & idx_a["valid"]
    n_valid = int(valid.sum())
    if n_valid == 0:
        raise ValueError("the two dates have no valid pixels in common")

    season = season_check(idx_b["ndvi"], idx_a["ndvi"], valid)
    if season["gap"] >= SEASON_WARNING_GAP:
        warnings.append(
            f"The dates differ in overall greenness (NDVI p{SEASON_NDVI_PERCENTILE} "
            f"{season['before']:.2f} vs {season['after']:.2f}). Index rules count dry bare fields as "
            "built-up, so built-up / vegetation / other changes may reflect season or rainfall rather "
            "than real land-cover change. Compare images from the same season.")
    map_b, map_a = classify(idx_b, valid, params), classify(idx_a, valid, params)
    pixel_area = pixel_area_m2(grid)
    class_stats = {c: _class_change(map_b, map_a, CLASS_CODES[c], valid, n_valid, pixel_area,
                                    params["unchanged_tolerance_pp"]) for c in CLASSES}
    transitions = _transitions(map_b, map_a, valid, n_valid)
    changed = round(100.0 * int(((map_b != map_a) & valid).sum()) / n_valid, 2)

    return {
        "grid": grid,
        "maps": {"before": map_b, "after": map_a},
        "classes": class_stats,
        "transitions": transitions,
        "changed_percent": changed,
        "valid_pixels": n_valid,
        "valid_area_km2": None if pixel_area is None else round(float((valid * pixel_area).sum() / 1e6), 4),
        "dates": {"before": before["date"], "after": after["date"]},
        "methods": {
            "water_index": "MNDWI (green, SWIR1)" if "swir1" in shared else "NDWI (green, NIR)",
            "built_up_index": "NDBI (SWIR1, NIR)" if "swir1" in shared else "low-NDVI proxy (no SWIR)",
            "vegetation_index": "NDVI (NIR, red)",
            "bands_used": shared,
            "thresholds": {k: params[k] for k in ("water_threshold", "vegetation_ndvi",
                                                  "builtup_threshold", "ndvi_max_builtup")},
            "unchanged_tolerance_pp": params["unchanged_tolerance_pp"],
        },
        "robustness": _robustness(idx_b, idx_a, valid, n_valid, params, class_stats),
        "season": season,
        "warnings": warnings,
    }


def season_check(ndvi_before, ndvi_after, valid):
    """Greenness of the greenest pixels on each date and the resulting confidence factor."""
    before = float(np.nanpercentile(ndvi_before[valid], SEASON_NDVI_PERCENTILE))
    after = float(np.nanpercentile(ndvi_after[valid], SEASON_NDVI_PERCENTILE))
    gap = round(abs(after - before), 4)
    factor = round(max(0.0, 1.0 - gap / SEASON_ZERO_CONFIDENCE_GAP), 4)
    return {"percentile": SEASON_NDVI_PERCENTILE, "before": round(before, 4), "after": round(after, 4),
            "gap": gap, "factor": factor, "affects": list(SEASON_SENSITIVE)}


def class_confidence(result, cls):
    """Threshold robustness, times the season factor for greenness-sensitive classes."""
    conf = result["robustness"]["per_class"][cls]
    if cls in SEASON_SENSITIVE:
        conf *= result["season"]["factor"]
    return round(conf, 4)


def _class_change(map_b, map_a, code, valid, n_valid, pixel_area, tolerance):
    before_px, after_px = int((map_b == code).sum()), int((map_a == code).sum())
    before_pct = round(100.0 * before_px / n_valid, 2)
    after_pct = round(100.0 * after_px / n_valid, 2)
    delta_pp = round(after_pct - before_pct, 2)
    s = {"before_percent": before_pct, "after_percent": after_pct, "delta_pp": delta_pp,
         "relative_change_percent": round(100.0 * delta_pp / before_pct, 1) if before_pct else None,
         "before_pixels": before_px, "after_pixels": after_px,
         "direction": direction(delta_pp, tolerance),
         "before_km2": None, "after_km2": None, "delta_km2": None}
    if pixel_area is not None:
        s["before_km2"] = round(float(((map_b == code) * pixel_area).sum() / 1e6), 4)
        s["after_km2"] = round(float(((map_a == code) * pixel_area).sum() / 1e6), 4)
        s["delta_km2"] = round(s["after_km2"] - s["before_km2"], 4)
    return s


def _transitions(map_b, map_a, valid, n_valid):
    """Off-diagonal from->to shares of the valid area, largest first."""
    out = []
    for src, dst in itertools.permutations(CLASSES, 2):
        n = int(((map_b == CLASS_CODES[src]) & (map_a == CLASS_CODES[dst]) & valid).sum())
        if n:
            out.append({"from": src, "to": dst, "percent": round(100.0 * n / n_valid, 2), "pixels": n})
    return sorted(out, key=lambda t: -t["pixels"])


def _robustness(idx_b, idx_a, valid, n_valid, params, class_stats):
    """Share of threshold perturbations (±ROBUSTNESS_SHIFT on each index threshold,
    27 combinations) that give the same direction per class as the main run."""
    keys = ["water_threshold", "vegetation_ndvi",
            "builtup_threshold" if idx_b["built"] is not None else "ndvi_max_builtup"]
    shifts = (-ROBUSTNESS_SHIFT, 0.0, ROBUSTNESS_SHIFT)
    agree = {c: 0 for c in CLASSES}
    runs = 0
    for combo in itertools.product(shifts, repeat=len(keys)):
        p = {**params, **{k: params[k] + s for k, s in zip(keys, combo)}}
        mb, ma = classify(idx_b, valid, p), classify(idx_a, valid, p)
        runs += 1
        for c in CLASSES:
            code = CLASS_CODES[c]
            b = round(100.0 * int((mb == code).sum()) / n_valid, 2)
            a = round(100.0 * int((ma == code).sum()) / n_valid, 2)
            if direction(round(a - b, 2), params["unchanged_tolerance_pp"]) == class_stats[c]["direction"]:
                agree[c] += 1
    return {"per_class": {c: round(agree[c] / runs, 4) for c in CLASSES}, "runs": runs,
            "shift": ROBUSTNESS_SHIFT, "perturbed": keys}
