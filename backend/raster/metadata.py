"""Read raster metadata with rasterio, independent of sensor or band count."""
import math
import warnings
from pathlib import Path

import rasterio
from rasterio.errors import NotGeoreferencedWarning, RasterioIOError

GEOTIFF_DRIVER = "GTiff"
IMAGE_DRIVERS = {"PNG", "JPEG"}


class RasterReadError(ValueError):
    """The file could not be opened as a raster."""


def read_metadata(path):
    """Return a JSON-serialisable metadata dict for the raster at ``path``.

    Raises RasterReadError if rasterio cannot open the file.
    """
    path = Path(path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(path) as src:
                return _describe(src)
    except RasterioIOError as exc:
        raise RasterReadError(f"not a readable raster ({exc})") from exc


def _describe(src):
    crs = src.crs
    georeferenced = crs is not None and not src.transform.is_identity
    left, bottom, right, top = src.bounds
    res_x, res_y = src.res
    return {
        "driver": src.driver,
        "width": src.width,
        "height": src.height,
        "band_count": src.count,
        "dtypes": list(src.dtypes),
        "nodata": _json_number(src.nodata),
        "band_descriptions": [d or None for d in src.descriptions],
        "crs": crs.to_string() if crs else None,
        "epsg": crs.to_epsg() if crs else None,
        "crs_is_geographic": bool(crs.is_geographic) if crs else None,
        "bounds": {"left": left, "bottom": bottom, "right": right, "top": top},
        "resolution": {"x": abs(res_x), "y": abs(res_y), "units": _units(crs)},
        "georeferenced": georeferenced,
    }


def _json_number(value):
    """JSON cannot hold NaN/inf (e.g. Earth Engine exports use nodata=-inf); keep them as strings."""
    if value is None or math.isfinite(value):
        return value
    return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")


def _units(crs):
    if crs is None:
        return "pixels"
    if crs.is_geographic:
        return "degrees"
    units = crs.linear_units
    return "metres" if units in ("metre", "meter") else (units or "unknown")
