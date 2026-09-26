"""Fetch analysis-ready GeoTIFFs from Google Earth Engine into a normal upload.

Every image of one fetch is exported on the SAME explicit grid (UTM zone of the area,
10 m pixels, identical transform and dimensions), so optical/SAR and two-date pairs line
up pixel for pixel. Sentinel-2 uses the Cloud Score+ masked collection from gee_service.
The rest of the app never needs Earth Engine; without credentials, status() says so.
"""
import math
import socket
import urllib.error
import urllib.request
from datetime import date

from rasterio.warp import transform_bounds

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
CS_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S1_COLLECTION = "COPERNICUS/S1_GRD"
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
S2_ROLES = "blue,green,red,nir,swir1,swir2"
S1_BANDS = ["VV", "VH"]
S1_ROLES = "vv,vh"
SCALE_M = 10
MAX_SIDE_KM = 10.0
DOWNLOAD_TIMEOUT_S = 180
_M_PER_DEG = 111_320.0


class FetchError(Exception):
    """A user-facing fetch problem with an HTTP status."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


# --- Earth Engine availability ---------------------------------------------------------------

_status = None


def status(refresh=False):
    """{"configured": bool, "reason": str|None}; initialises Earth Engine once and caches the result."""
    global _status
    if _status is None or refresh:
        try:
            import gee_service
            gee_service.initialize_gee()
            _status = {"configured": True, "reason": None, "detail": None}
        except Exception as exc:  # no credentials, no project, no network...
            _status = {"configured": False,
                       "reason": "Earth Engine not configured — use samples/ or upload GeoTIFFs.",
                       "detail": f"{type(exc).__name__}: {exc}"[:300]}
    return _status


# --- area and grid ---------------------------------------------------------------------------

def bbox_size_km(bbox):
    west, south, east, north = bbox
    mid_lat = math.radians((south + north) / 2)
    return ((east - west) * _M_PER_DEG * math.cos(mid_lat) / 1000, (north - south) * _M_PER_DEG / 1000)


def check_bbox(bbox):
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise FetchError(422, "The area must be [west, south, east, north] in degrees.")
    west, south, east, north = map(float, bbox)
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise FetchError(422, "The area is not a valid [west, south, east, north] box.")
    w_km, h_km = bbox_size_km((west, south, east, north))
    if w_km > MAX_SIDE_KM + 0.05 or h_km > MAX_SIDE_KM + 0.05:
        raise FetchError(422, f"The area is {w_km:.1f} x {h_km:.1f} km; the maximum is "
                              f"{MAX_SIDE_KM:g} x {MAX_SIDE_KM:g} km. Draw a smaller rectangle or pick a smaller size.")
    return west, south, east, north


def utm_epsg(lon, lat):
    zone = min(60, int((lon + 180) // 6) + 1)
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def grid_for_bbox(bbox, scale=SCALE_M):
    """Explicit export grid shared by every image of a fetch."""
    west, south, east, north = bbox
    crs = utm_epsg((west + east) / 2, (south + north) / 2)
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", crs, west, south, east, north)
    xmin, ymin = math.floor(xmin / scale) * scale, math.floor(ymin / scale) * scale
    xmax, ymax = math.ceil(xmax / scale) * scale, math.ceil(ymax / scale) * scale
    width, height = int(round((xmax - xmin) / scale)), int(round((ymax - ymin) / scale))
    return {"crs": crs, "crs_transform": [scale, 0, xmin, 0, -scale, ymax],
            "dimensions": f"{width}x{height}", "scale": scale}


def check_range(r):
    try:
        start, end = date.fromisoformat(r[0]), date.fromisoformat(r[1])
    except (TypeError, ValueError, IndexError):
        raise FetchError(422, f"Date range {r!r} must be two YYYY-MM-DD dates.")
    if start >= end:
        raise FetchError(422, f"Date range {r[0]} to {r[1]}: the start must be before the end.")
    if start > date.today():
        raise FetchError(422, f"Date range {r[0]} to {r[1]} is in the future.")
    return start.isoformat(), end.isoformat()


def mid_date(r):
    start, end = date.fromisoformat(r[0]), date.fromisoformat(r[1])
    return date.fromordinal((start.toordinal() + end.toordinal()) // 2).isoformat()


# --- Earth Engine images (small functions so tests can replace them) ---------------------------

def s2_composite(aoi, start, end):
    """Cloud Score+ masked Sentinel-2 L2A median. Returns (image, scene_count)."""
    import gee_service
    col = gee_service.get_s2_sr_cld_col(aoi, start, end)
    return col.median().select(S2_BANDS).toUint16(), col.size().getInfo()


def s1_composite(aoi, start, end):
    """Sentinel-1 GRD IW median, VV + VH in dB. Returns (image, scene_count)."""
    import ee
    col = (ee.ImageCollection(S1_COLLECTION).filterBounds(aoi).filterDate(start, end)
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
           .select(S1_BANDS))
    return col.median().toFloat(), col.size().getInfo()


def aoi_geometry(bbox):
    import ee
    return ee.Geometry.Rectangle(list(bbox))


def download(image, grid, target):
    """Export ``image`` on ``grid`` as a GeoTIFF file at ``target``."""
    url = image.getDownloadURL({"crs": grid["crs"], "crs_transform": grid["crs_transform"],
                                "dimensions": grid["dimensions"], "format": "GEO_TIFF"})
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as resp, open(target, "wb") as out:
            while block := resp.read(1 << 20):
                out.write(block)
    except (socket.timeout, TimeoutError):
        raise FetchError(504, f"Earth Engine download timed out after {DOWNLOAD_TIMEOUT_S} s. "
                              "Try a smaller area or a shorter date range.")
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise FetchError(504, f"Earth Engine download timed out after {DOWNLOAD_TIMEOUT_S} s.")
        raise FetchError(502, f"Earth Engine download failed: {exc.reason}")


# --- the fetch ---------------------------------------------------------------------------------

def plan(mode, date_ranges):
    """What to fetch per mode: list of (slot, product, date_range)."""
    if mode == "single":
        return [(1, "s2", date_ranges[0])]
    if mode == "optical_sar":
        return [(1, "s2", date_ranges[0]), (2, "s1", date_ranges[0])]
    if mode == "bi_temporal":
        if len(date_ranges) < 2:
            raise FetchError(422, "Two dates needs two date ranges.")
        return [(1, "s2", date_ranges[0]), (2, "s2", date_ranges[1])]
    raise FetchError(422, f"Unknown mode '{mode}'.")


def fetch(mode, bbox, date_ranges):
    """Fetch, validate and store; returns the accepted upload manifest (with a ``source`` block)."""
    from ingest import store
    from ingest.validation import validate_upload

    bbox = check_bbox(bbox)
    ranges = [check_range(r) for r in date_ranges]
    if not ranges:
        raise FetchError(422, "Give at least one date range.")
    steps = plan(mode, ranges)
    st = status()
    if not st["configured"]:
        raise FetchError(503, st["reason"])

    grid = grid_for_bbox(bbox)
    aoi = aoi_geometry(bbox)
    upload_id = store.new_upload_id()
    staged = store.staging_dir(upload_id)
    try:
        files, products = [], []
        for slot, product, (start, end) in steps:
            image, count = (s2_composite if product == "s2" else s1_composite)(aoi, start, end)
            name = "Sentinel-2 L2A" if product == "s2" else "Sentinel-1 GRD"
            if not count:
                raise FetchError(422, f"No {name} images for this area between {start} and {end}. "
                                      "Widen the date range (e.g. 2-3 months) or move the area.")
            target = staged / f"file_{slot}.tif"
            download(image, grid, target)
            label = f"{'s2' if product == 's2' else 's1'}_{start}_{end}.tif"
            files.append((label, target))
            products.append({"slot": slot, "product": name,
                             "collection": [S2_COLLECTION, CS_COLLECTION] if product == "s2" else [S1_COLLECTION],
                             "date_range": [start, end], "scenes": count,
                             "bands": S2_BANDS if product == "s2" else S1_BANDS,
                             "processing": "median of Cloud Score+ masked scenes (cs_cdf >= 0.6)" if product == "s2"
                             else "median of IW scenes, VV/VH backscatter in dB"})
        roles = [S2_ROLES if p == "s2" else S1_ROLES for _, p, _ in steps]
        dates = [mid_date(r) for _, _, r in steps] if mode == "bi_temporal" else None
        result = validate_upload(mode, files, dates=dates, band_roles=roles)
        if not result["ok"]:
            raise FetchError(422, "Fetched images failed validation: "
                                  + "; ".join(r["message"] for r in result["reasons"]))
        for info, (_, target) in zip(result["files"], files):
            info["stored_as"] = target.name
        manifest = {"upload_id": upload_id, "status": "accepted", "mode": mode, "benchmark_mode": False,
                    "files": result["files"], "pair": result["pair"], "warnings": result["warnings"],
                    "source": {"provider": "Google Earth Engine", "bbox": list(bbox), "crs": grid["crs"],
                               "scale_m": grid["scale"], "dimensions": grid["dimensions"],
                               "products": products}}
        store.commit(upload_id, manifest)
        return manifest
    finally:
        store.discard(upload_id)
