"""Build tiny synthetic rasters for tests. Nothing here touches real data."""
import warnings

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_origin

UTM_43N = "EPSG:32643"  # covers Bengaluru
WGS84 = "EPSG:4326"


def make_geotiff(path, count=4, width=8, height=8, dtype="uint16", crs=UTM_43N,
                 origin=(780000.0, 1440000.0), res=10.0, descriptions=None,
                 nodata=None, data=None):
    """Write a small GeoTIFF and return its path.

    ``crs=None`` writes a GeoTIFF with no CRS and an identity transform.
    """
    if data is None:
        rng = np.random.default_rng(0)
        data = rng.integers(0, 3000, size=(count, height, width)).astype(dtype)
    profile = {
        "driver": "GTiff", "width": width, "height": height, "count": count,
        "dtype": dtype, "nodata": nodata,
    }
    if crs is not None:
        profile["crs"] = crs
        profile["transform"] = from_origin(origin[0], origin[1], res, res)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data)
            for i, desc in enumerate(descriptions or [], start=1):
                dst.set_band_description(i, desc)
    return path


def _write(path, profile, data):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(data)
    return path


def make_png(path, count=3, width=8, height=8):
    data = np.full((count, height, width), 128, dtype="uint8")
    profile = {"driver": "PNG", "width": width, "height": height, "count": count, "dtype": "uint8"}
    return _write(path, profile, data)


def make_jpeg(path, width=8, height=8):
    data = np.full((3, height, width), 128, dtype="uint8")
    profile = {"driver": "JPEG", "width": width, "height": height, "count": 3, "dtype": "uint8"}
    return _write(path, profile, data)
