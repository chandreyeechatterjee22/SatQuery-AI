"""Validate an upload: file count per mode, format, CRS, overlap and dates.

Every problem found is reported (not just the first) so the user can fix
everything in one go. Rejection reasons carry a stable ``code`` for the UI.
"""
from datetime import date
from pathlib import Path

from raster.band_adapter import BandAdapterError, parse_band_roles, resolve_bands
from raster.metadata import GEOTIFF_DRIVER, IMAGE_DRIVERS, RasterReadError, read_metadata

MODES = {"single": 1, "optical_sar": 2, "bi_temporal": 2}
SLOT_KINDS = {"single": [None], "optical_sar": ["optical", "sar"], "bi_temporal": [None, None]}
GEOTIFF_EXTS = {".tif", ".tiff"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_PHOTO_DRIVER = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
LOW_OVERLAP_WARNING = 0.5


def reason(code, message, slot=None):
    r = {"code": code, "message": message}
    if slot is not None:
        r["file"] = slot
    return r


def validate_upload(mode, files, dates=None, sensors=None, benchmark_mode=False, today=None,
                    band_roles=None):
    """Validate an upload.

    ``files`` is a list of ``(original_filename, path_on_disk)``; ``dates`` and
    ``sensors`` are lists aligned with ``files`` (entries may be None).
    ``band_roles`` is also aligned: comma-separated role strings such as
    "blue,green,red,nir,swir1" (or None).
    Returns ``{"ok", "reasons", "warnings", "files", "pair"}``.
    """
    reasons, warnings = [], []
    dates = list(dates or [])
    sensors = list(sensors or [])
    band_roles = list(band_roles or [])

    if mode not in MODES:
        return _result([reason("invalid_mode",
                               f"Unknown mode '{mode}'. Use one of: {', '.join(MODES)}.")])
    expected = MODES[mode]
    if len(files) != expected:
        return _result([reason("file_count",
                               f"Mode '{mode}' needs exactly {expected} file(s); got {len(files)}.")])

    parsed_dates = _check_dates(mode, dates, expected, today or date.today(), reasons)

    described = []
    for i, (filename, path) in enumerate(files):
        slot = i + 1
        sensor = sensors[i] if i < len(sensors) and sensors[i] else "auto"
        roles = parse_band_roles(band_roles[i]) if i < len(band_roles) else None
        info = _check_file(slot, filename, path, sensor, SLOT_KINDS[mode][i],
                           benchmark_mode, reasons, warnings, roles)
        if info is not None:
            info["date"] = parsed_dates[i].isoformat() if parsed_dates[i] else None
            described.append(info)

    pair = None
    if expected == 2 and len(described) == 2:
        pair = _check_pair(mode, described, benchmark_mode, reasons, warnings)
        if mode == "bi_temporal" and all(parsed_dates) and parsed_dates[0] > parsed_dates[1]:
            warnings.append("File 1 is dated after file 2; change analysis will compare "
                            "them in chronological order.")

    return _result(reasons, warnings, described, pair)


def _result(reasons, warnings=None, files=None, pair=None):
    return {"ok": not reasons, "reasons": reasons, "warnings": warnings or [],
            "files": files or [], "pair": pair}


def _check_dates(mode, dates, expected, today, reasons):
    parsed = [None] * expected
    for i in range(expected):
        raw = dates[i].strip() if i < len(dates) and dates[i] else ""
        slot = i + 1
        if not raw:
            if mode == "bi_temporal":
                reasons.append(reason("missing_date",
                                      f"File {slot} needs an acquisition date (YYYY-MM-DD).", slot))
            continue
        try:
            parsed[i] = date.fromisoformat(raw)
        except ValueError:
            reasons.append(reason("invalid_date",
                                  f"File {slot} date '{raw}' is not a valid YYYY-MM-DD date.", slot))
            continue
        if parsed[i] > today:
            reasons.append(reason("future_date",
                                  f"File {slot} date {raw} is in the future.", slot))
    if mode == "bi_temporal" and parsed[0] and parsed[0] == parsed[1]:
        reasons.append(reason("same_date",
                              f"Both files have the same date ({parsed[0]}); "
                              "bi_temporal needs two different dates."))
    return parsed


def _check_file(slot, filename, path, sensor, expected_kind, benchmark_mode, reasons, warnings,
                band_roles=None):
    ext = Path(filename or "").suffix.lower()
    if ext in IMAGE_EXTS and not benchmark_mode:
        reasons.append(reason("image_requires_benchmark_mode",
                              f"File {slot} ({filename}) is {ext.lstrip('.').upper()}; "
                              "only GeoTIFF is accepted unless benchmark_mode=true.", slot))
        return None
    if ext not in GEOTIFF_EXTS | IMAGE_EXTS:
        allowed = ".tif/.tiff" + (", .png, .jpg/.jpeg" if benchmark_mode else "")
        reasons.append(reason("unsupported_format",
                              f"File {slot} ({filename}) has unsupported type '{ext or 'none'}'. "
                              f"Allowed: {allowed}.", slot))
        return None

    try:
        meta = read_metadata(path)
    except RasterReadError as exc:
        reasons.append(reason("unreadable_raster", f"File {slot} ({filename}) is {exc}.", slot))
        return None

    expected_driver = GEOTIFF_DRIVER if ext in GEOTIFF_EXTS else None
    if expected_driver and meta["driver"] != expected_driver:
        reasons.append(reason("format_mismatch",
                              f"File {slot} ({filename}) is named {ext} but is actually "
                              f"{meta['driver']}.", slot))
        return None
    if not expected_driver and meta["driver"] not in IMAGE_DRIVERS:
        reasons.append(reason("format_mismatch",
                              f"File {slot} ({filename}) is named {ext} but is actually "
                              f"{meta['driver']}.", slot))
        return None
    if not expected_driver and meta["driver"] != _PHOTO_DRIVER[ext]:
        # e.g. a WebP saved from a website under a .jpg name: still an ordinary photo.
        warnings.append(f"File {slot} ({filename}) is named {ext} but is actually {meta['driver']}; "
                        "read as a photo.")

    try:
        bands = resolve_bands(meta, sensor=sensor, expected_kind=expected_kind, band_roles=band_roles)
    except BandAdapterError as exc:
        if band_roles is not None:
            code = "invalid_band_roles"
        elif expected_kind == "sar" and sensor == "auto":
            code = "wrong_modality"
        else:
            code = "sensor_mismatch"
        prefix = "must be the SAR image; " if code == "wrong_modality" else ""
        reasons.append(reason(code, f"File {slot} ({filename}) {prefix}{exc}.", slot))
        return None

    if expected_kind == "optical" and (bands["kind"] == "sar" or meta["band_count"] < 3):
        reasons.append(reason("wrong_modality",
                              f"File {slot} ({filename}) must be the optical image (3+ bands); "
                              f"it has {meta['band_count']} band(s)"
                              + (" that look like SAR." if bands["kind"] == "sar" else "."), slot))
        return None
    if expected_kind == "sar" and bands["kind"] != "sar":
        reasons.append(reason("wrong_modality",
                              f"File {slot} ({filename}) must be the SAR image; its band "
                              "descriptions look optical.", slot))
        return None

    if not meta["georeferenced"]:
        warnings.append(f"File {slot} ({filename}) has no CRS/geotransform; areas will be "
                        "reported in pixels, not m².")
    warnings.extend(f"File {slot}: {w}" for w in bands["warnings"])
    return {"slot": slot, "filename": filename, "kind": bands["kind"],
            "metadata": meta, "bands": bands}


def _check_pair(mode, described, benchmark_mode, reasons, warnings):
    a, b = (d["metadata"] for d in described)
    pair = {"same_crs": None, "overlap_fraction": None, "intersection": None,
            "same_resolution": _same_res(a, b)}

    if mode == "bi_temporal" and described[0]["kind"] != described[1]["kind"]:
        reasons.append(reason("modality_mismatch",
                              "bi_temporal needs two images of the same kind; got "
                              f"{described[0]['kind']} and {described[1]['kind']}."))

    if not (a["georeferenced"] and b["georeferenced"]):
        if not benchmark_mode:
            missing = [str(d["slot"]) for d in described if not d["metadata"]["georeferenced"]]
            reasons.append(reason("missing_crs",
                                  f"File(s) {', '.join(missing)} have no CRS, so the pair cannot "
                                  "be checked for overlap. Upload georeferenced GeoTIFFs."))
        elif (a["width"], a["height"]) != (b["width"], b["height"]):
            reasons.append(reason("size_mismatch",
                                  "Benchmark images without a CRS must have the same pixel size; "
                                  f"got {a['width']}x{a['height']} and {b['width']}x{b['height']}."))
        else:
            warnings.append("Pair has no CRS; assuming the two images are pixel-aligned.")
        return pair

    pair["same_crs"] = a["crs"] == b["crs"]
    if not pair["same_crs"]:
        reasons.append(reason("crs_mismatch",
                              f"The two files use different CRS ({a['crs']} vs {b['crs']}). "
                              "Reproject one so both match."))
        return pair

    inter = _intersection(a["bounds"], b["bounds"])
    if inter is None:
        reasons.append(reason("no_overlap",
                              "The two files do not overlap geographically "
                              f"(bounds {_fmt(a['bounds'])} vs {_fmt(b['bounds'])})."))
        return pair
    smaller = min(_area(a["bounds"]), _area(b["bounds"]))
    pair["intersection"] = inter
    pair["overlap_fraction"] = round(_area(inter) / smaller, 4) if smaller else 0.0
    if pair["overlap_fraction"] < LOW_OVERLAP_WARNING:
        warnings.append(f"The files overlap by only {pair['overlap_fraction']:.0%} of the "
                        "smaller image; analysis uses the overlapping area only.")
    if not pair["same_resolution"]:
        warnings.append(f"Resolutions differ ({_res(a)} vs {_res(b)}); the second image will "
                        "be resampled onto the first.")
    if mode == "bi_temporal" and a["band_count"] != b["band_count"]:
        warnings.append(f"Band counts differ ({a['band_count']} vs {b['band_count']}); only "
                        "band roles present in both dates can be compared.")
    return pair


def _intersection(a, b):
    left, right = max(a["left"], b["left"]), min(a["right"], b["right"])
    bottom, top = max(a["bottom"], b["bottom"]), min(a["top"], b["top"])
    if left >= right or bottom >= top:
        return None
    return {"left": left, "bottom": bottom, "right": right, "top": top}


def _area(bounds):
    return (bounds["right"] - bounds["left"]) * (bounds["top"] - bounds["bottom"])


def _same_res(a, b, rel_tol=1e-6):
    ra, rb = a["resolution"], b["resolution"]
    return all(abs(ra[k] - rb[k]) <= rel_tol * max(abs(ra[k]), abs(rb[k]), 1e-12) for k in ("x", "y"))


def _res(meta):
    r = meta["resolution"]
    return f"{r['x']:g}x{r['y']:g} {r['units']}"


def _fmt(bounds):
    return f"[{bounds['left']:g}, {bounds['bottom']:g}, {bounds['right']:g}, {bounds['top']:g}]"
