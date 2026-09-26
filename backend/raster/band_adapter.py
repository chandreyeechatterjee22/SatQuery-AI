"""Map a raster's bands to semantic roles (blue, green, red, nir, swir1, vv, ...).

This is the ONLY module that knows sensor-specific band names. Every tool
downstream asks for roles, never for "B4" or "B8".
"""
import re

SENSORS = ("auto", "sentinel2", "cartosat2s", "bgrn", "rgb", "sar")
OPTICAL_ROLES = ("blue", "green", "red", "nir", "swir1", "swir2")
SAR_ROLES = ("vv", "vh", "hh", "hv")

# Sentinel-2 band layouts by band count, and which bands carry a role.
_S2_LAYOUTS = {
    13: ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B10", "B11", "B12"],
    12: ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B9", "B11", "B12"],
    10: ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"],
    4: ["B2", "B3", "B4", "B8"],
}
_S2_ROLES = {"B2": "blue", "B3": "green", "B4": "red", "B8": "nir", "B11": "swir1", "B12": "swir2"}
_S2_CODE = re.compile(r"^B0?(\d{1,2}A?)$", re.IGNORECASE)
# Bands only a Sentinel-2 stack has; used to recognise S2 from descriptions.
_S2_ONLY = {"B8A", "B9", "B10", "B11", "B12"}

_FIXED_LAYOUTS = {
    "cartosat2s": ["blue", "green", "red", "nir"],  # Cartosat-2S MX
    "bgrn": ["blue", "green", "red", "nir"],
    "rgb": ["red", "green", "blue"],
}

_ALIASES = {
    "blue": "blue", "green": "green", "red": "red",
    "nir": "nir", "nearinfrared": "nir",
    "swir1": "swir1", "swir2": "swir2",
    "vv": "vv", "vh": "vh", "hh": "hh", "hv": "hv",
}


class BandAdapterError(ValueError):
    """The declared sensor does not fit the file's bands."""


IGNORE_ROLE = "-"


def parse_band_roles(text):
    """Parse a user list like "blue, green, red, nir, swir1" (use "-" to ignore a band)."""
    if text is None or not text.strip():
        return None
    return [r.strip().lower() for r in text.split(",")]


def resolve_bands(meta, sensor="auto", expected_kind=None, band_roles=None):
    """Return a band profile for a raster metadata dict (see raster.metadata).

    ``expected_kind`` ("optical" or "sar") is set when the upload slot already
    says what the file must be, e.g. the second file of an optical_sar pair.
    ``band_roles`` is an explicit per-band role list from the user; it wins over
    everything else (e.g. for Earth Engine exports, which drop band names).
    """
    if sensor not in SENSORS:
        raise BandAdapterError(f"unknown sensor {sensor!r}; choose one of {', '.join(SENSORS)}")
    count = meta["band_count"]
    if band_roles is not None:
        if sensor != "auto":
            raise BandAdapterError("give either a sensor or explicit band roles, not both")
        return _from_user_roles(band_roles, count)
    if sensor != "auto":
        return _from_sensor(sensor, count, "sensor_hint")

    from_desc = _from_descriptions(meta.get("band_descriptions") or [None] * count)
    if from_desc:
        return from_desc
    if expected_kind == "sar" or (expected_kind is None and count <= 2):
        return _from_sensor("sar", count, "band_count")
    if count in (10, 12, 13):
        return _from_sensor("sentinel2", count, "band_count")
    if count == 4:
        return _profile("bgrn", "optical", _FIXED_LAYOUTS["bgrn"], "band_count",
                        ["4 bands assumed to be blue, green, red, NIR (e.g. Cartosat-2S MX); "
                         "set sensor to override"])
    if count == 3:
        warnings = [] if meta.get("driver") in ("PNG", "JPEG") else [
            "3 bands assumed to be red, green, blue; set sensor to override"]
        return _profile("rgb", "optical", _FIXED_LAYOUTS["rgb"], "band_count", warnings)
    return _profile("unknown", expected_kind or "optical", [None] * count, "unresolved",
                    [f"could not infer band roles for {count} bands; "
                     "spectral-index tools will not be available"])


def _from_sensor(sensor, count, source):
    if sensor == "sentinel2":
        if count not in _S2_LAYOUTS:
            raise BandAdapterError(
                f"sentinel2 expects {sorted(_S2_LAYOUTS)} bands, file has {count}")
        names = _S2_LAYOUTS[count]
        return _profile("sentinel2", "optical", [_S2_ROLES.get(n) for n in names], source,
                        band_names=names)
    if sensor == "sar":
        if count not in (1, 2):
            raise BandAdapterError(f"SAR images must have 1 or 2 bands, file has {count}")
        roles = ["vv", "vh"][:count]
        return _profile("sar", "sar", roles, source,
                        [f"SAR bands assumed to be {', '.join(r.upper() for r in roles)}; "
                         "set band descriptions to override"])
    layout = _FIXED_LAYOUTS[sensor]
    if count != len(layout):
        raise BandAdapterError(f"{sensor} expects {len(layout)} bands, file has {count}")
    return _profile(sensor, "optical", layout, source)


def _from_user_roles(roles, count):
    if len(roles) != count:
        raise BandAdapterError(f"band roles list has {len(roles)} entries but the file has {count} bands")
    allowed = set(OPTICAL_ROLES) | set(SAR_ROLES) | {IGNORE_ROLE}
    bad = [r for r in roles if r not in allowed]
    if bad:
        raise BandAdapterError(f"unknown band roles {bad}; use {', '.join(sorted(allowed))}")
    used = [r for r in roles if r != IGNORE_ROLE]
    if not used:
        raise BandAdapterError("band roles list marks every band as ignored")
    if len(set(used)) != len(used):
        raise BandAdapterError("each band role may appear only once")
    sar = [r in SAR_ROLES for r in used]
    if any(sar) and not all(sar):
        raise BandAdapterError("band roles mix optical and SAR bands in one file")
    kind = "sar" if all(sar) else "optical"
    return _profile("user", kind, [None if r == IGNORE_ROLE else r for r in roles], "user_roles")


def _from_descriptions(descriptions):
    norm = [_normalise(d) for d in descriptions]
    s2_codes = [_s2_code(d) for d in norm]
    if all(s2_codes) and (_S2_ONLY & set(s2_codes) or len(s2_codes) >= 10):
        return _profile("sentinel2", "optical", [_S2_ROLES.get(c) for c in s2_codes],
                        "descriptions", band_names=s2_codes)
    roles = [_ALIASES.get(d) for d in norm]
    found = [r for r in roles if r]
    if not found:
        return None
    kind = "sar" if all(r in SAR_ROLES for r in found) else "optical"
    return _profile("described", kind, roles, "descriptions")


def _normalise(desc):
    return re.sub(r"[\s_\-]", "", desc).lower() if desc else ""


def _s2_code(desc):
    m = _S2_CODE.match(desc)
    return f"B{m.group(1).upper()}" if m else None


def _profile(sensor, kind, roles_by_band, source, warnings=None, band_names=None):
    roles = {}
    for index, role in enumerate(roles_by_band, start=1):
        if role and role not in roles:
            roles[role] = index
    return {
        "sensor": sensor,
        "kind": kind,
        "roles": roles,
        "band_names": band_names or [r or f"band_{i}" for i, r in enumerate(roles_by_band, start=1)],
        "source": source,
        "warnings": warnings or [],
    }
