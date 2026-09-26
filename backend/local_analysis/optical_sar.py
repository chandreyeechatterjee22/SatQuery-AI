"""Water and built-up mapping from an optical + SAR pair.

Optical and SAR each vote per pixel; the ``fusion`` rule ("and"/"or") combines
them. The SAR image is resampled onto the optical grid, and only pixels valid
in both are counted. Percentages are of that common valid area. Every number
in the text answer comes from the returned stats, so they cannot disagree.
"""
import numpy as np

from local_analysis.grid import area_km2, grid_for, pixel_area_m2, read_on_grid
from local_analysis.indices import normalized_difference, sar_to_db

CLASSES = ("water", "built_up")
CLASS_LABELS = {"water": "Water", "built_up": "Built-up"}

DEFAULTS = {
    "sar_water_db": -18.0,          # VV/HH below this -> smooth surface (water)
    "sar_builtup_db": -6.0,         # VV/HH above this -> double bounce (buildings)
    "optical_water_threshold": 0.0,  # MNDWI/NDWI above this -> water
    "optical_builtup_threshold": 0.0,  # NDBI above this -> built-up
    "ndvi_max_builtup": 0.2,        # low-NDVI proxy when there is no SWIR band
    "fusion": "and",
    "max_size": 1024,
}


def _sar_band(roles):
    for pol in ("vv", "hh", "vh", "hv"):
        if pol in roles:
            return pol, roles[pol]
    return None, None


def _optical_layers(optical_path, roles, grid, params, warnings):
    """Optical water / built-up masks (or None when the bands are missing), plus method names."""
    wanted = [r for r in ("green", "red", "nir", "swir1") if r in roles]
    arrays = dict(zip(wanted, read_on_grid(optical_path, [roles[r] for r in wanted], grid))) if wanted else {}
    valid = np.ones(grid.shape, dtype=bool)
    for arr in arrays.values():
        valid &= np.isfinite(arr)

    water = water_method = None
    if "green" in arrays and "swir1" in arrays:
        water_method = "MNDWI (green, SWIR1)"
        water = normalized_difference(arrays["green"], arrays["swir1"]) > params["optical_water_threshold"]
    elif "green" in arrays and "nir" in arrays:
        water_method = "NDWI (green, NIR)"
        water = normalized_difference(arrays["green"], arrays["nir"]) > params["optical_water_threshold"]
    else:
        warnings.append("Optical image has no green+NIR/SWIR bands; water is detected by SAR only.")

    built = built_method = None
    if "swir1" in arrays and "nir" in arrays:
        built_method = "NDBI (SWIR1, NIR)"
        built = normalized_difference(arrays["swir1"], arrays["nir"]) > params["optical_builtup_threshold"]
    elif "nir" in arrays and "red" in arrays:
        built_method = f"low NDVI (< {params['ndvi_max_builtup']:g}) proxy, no SWIR band"
        built = normalized_difference(arrays["nir"], arrays["red"]) < params["ndvi_max_builtup"]
        warnings.append("Optical image has no SWIR band, so optical built-up uses a low-NDVI proxy, "
                        "which also flags bare soil; SAR agreement matters more here.")
    else:
        warnings.append("Optical image has no NIR/red bands; built-up is detected by SAR only.")

    if water is not None:
        water &= valid
    if built is not None:
        built &= valid
        if water is not None:
            built &= ~water  # a pixel the optical image calls water is not optical built-up
    return valid, water, water_method, built, built_method


def _sar_layers(sar_path, roles, grid, params, warnings):
    pol, index = _sar_band(roles)
    if pol is None:
        warnings.append("SAR image has no recognised polarisation band; SAR is not used.")
        return np.ones(grid.shape, dtype=bool), None, None, None, None
    values = read_on_grid(sar_path, [index], grid)[0]
    db, was_linear, calibrated = sar_to_db(values)
    if not calibrated:
        warnings.append("SAR values do not look like calibrated backscatter (sigma0 in dB); "
                        "the dB thresholds may not apply.")
    valid = np.isfinite(db)
    band = f"{pol.upper()}{' (linear, converted to dB)' if was_linear else ' (dB)'}"
    water = (db < params["sar_water_db"]) & valid
    built = (db > params["sar_builtup_db"]) & valid
    return valid, water, built, band, calibrated


def map_water_builtup(optical_path, optical_bands, sar_path, sar_bands, params=None, classes=CLASSES):
    """Return {"grid", "stats", "masks", "methods", "warnings"} for the requested classes."""
    params = {**DEFAULTS, **(params or {})}
    warnings = []
    grid = grid_for(optical_path, params["max_size"])
    opt_valid, opt_water, water_method, opt_built, built_method = _optical_layers(
        optical_path, optical_bands["roles"], grid, params, warnings)
    sar_valid, sar_water, sar_built, sar_band, sar_calibrated = _sar_layers(
        sar_path, sar_bands["roles"], grid, params, warnings)

    valid = opt_valid & sar_valid
    n_valid = int(valid.sum())
    if n_valid == 0:
        raise ValueError("the optical and SAR images have no valid pixels in common")
    pixel_area = pixel_area_m2(grid)

    layers = {"water": (opt_water, sar_water), "built_up": (opt_built, sar_built)}
    masks, stats = {}, {}
    final_water = None
    for cls in CLASSES:  # water first: built-up never overlaps final water
        allowed = valid if cls == "water" or final_water is None else valid & ~final_water
        optical, sar = (None if m is None else m & allowed for m in layers[cls])
        final = _fuse(optical, sar, params["fusion"])
        if cls == "water":
            final_water = final
        if cls not in classes:
            continue
        masks[cls] = {"final": final, "optical": optical, "sar": sar}
        stats[cls] = _class_stats(final, optical, sar, valid, n_valid, pixel_area)

    return {
        "grid": grid,
        "stats": stats,
        "masks": masks,
        "valid_pixels": n_valid,
        "sar_calibrated": sar_calibrated,
        "valid_area_km2": _round(area_km2(valid, pixel_area), 4),
        "methods": {"optical_water": water_method, "optical_built_up": built_method,
                    "sar_band": sar_band, "fusion": params["fusion"],
                    "thresholds": {k: params[k] for k in ("sar_water_db", "sar_builtup_db",
                                                          "optical_water_threshold",
                                                          "optical_builtup_threshold",
                                                          "ndvi_max_builtup")}},
        "warnings": warnings,
    }


def _fuse(optical, sar, rule):
    if optical is None and sar is None:
        return None
    if optical is None:
        return sar.copy()
    if sar is None:
        return optical.copy()
    return (optical & sar) if rule == "and" else (optical | sar)


def _class_stats(final, optical, sar, valid, n_valid, pixel_area):
    def pct(mask):
        return None if mask is None else round(100.0 * int(mask.sum()) / n_valid, 2)

    both = optical & sar if optical is not None and sar is not None else None
    either = optical | sar if both is not None else None
    s = {
        "percent": pct(final),
        "pixels": None if final is None else int(final.sum()),
        "area_km2": None if final is None else _round(area_km2(final, pixel_area), 4),
        "both_percent": pct(both),
        "optical_only_percent": pct(optical & ~sar) if both is not None else None,
        "sar_only_percent": pct(sar & ~optical) if both is not None else None,
        "optical_percent": pct(optical),
        "sar_percent": pct(sar),
        # Agreement = pixels both modalities flag / pixels either flags. Two empty masks agree.
        "agreement": None if both is None else (
            round(int(both.sum()) / int(either.sum()), 4) if either.any() else 1.0),
    }
    s["detected_by"] = [m for m, key in (("optical", "optical_percent"), ("sar", "sar_percent"))
                        if s[key]]
    return s


def _round(value, digits):
    return None if value is None else round(value, digits)
