"""A common processing grid: the first image's extent, downsampled, with others resampled onto it."""
import warnings
from dataclasses import dataclass

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning
from rasterio.warp import reproject

DEFAULT_MAX_SIZE = 1024
_M_PER_DEG_LAT = 110_574.0
_M_PER_DEG_LON_EQUATOR = 111_320.0


@dataclass
class Grid:
    width: int
    height: int
    crs: object          # rasterio CRS or None
    transform: object    # affine transform of the (downsampled) grid, or None
    georeferenced: bool

    @property
    def shape(self):
        return (self.height, self.width)


def _open(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        return rasterio.open(path)


def grid_for(path, max_size=DEFAULT_MAX_SIZE):
    """Grid covering ``path``'s full extent, at most ``max_size`` pixels on the long side."""
    with _open(path) as src:
        scale = max(1.0, max(src.width, src.height) / max_size)
        width, height = max(1, round(src.width / scale)), max(1, round(src.height / scale))
        georef = src.crs is not None and not src.transform.is_identity
        transform = src.transform * Affine.scale(src.width / width, src.height / height) if georef else None
        return Grid(width, height, src.crs if georef else None, transform, georef)


def read_on_grid(path, indexes, grid):
    """Read bands (1-based ``indexes``) resampled onto ``grid`` as float64 with NaN for nodata.

    Georeferenced inputs are reprojected (average resampling); otherwise the
    image is assumed pixel-aligned and simply resized.
    """
    out = np.full((len(indexes),) + grid.shape, np.nan, dtype="float64")
    with _open(path) as src:
        src_georef = src.crs is not None and not src.transform.is_identity
        if grid.georeferenced and src_georef:
            for i, band in enumerate(indexes):
                # Warp straight from the file so GDAL streams it; a full-size band
                # is never loaded into memory.
                reproject(source=rasterio.band(src, band), destination=out[i],
                          src_nodata=src.nodata, dst_transform=grid.transform, dst_crs=grid.crs,
                          dst_nodata=np.nan, resampling=Resampling.average)
        else:
            data = src.read(list(indexes), out_shape=(len(indexes),) + grid.shape, masked=True,
                            resampling=Resampling.average)
            out[:] = data.astype("float64").filled(np.nan)
    return out


def pixel_area_m2(grid):
    """Per-row pixel area in m² (shape (H, 1)), or None when the grid has no usable CRS.

    Projected CRS in metres: exact. Geographic CRS: spherical approximation per row.
    """
    if not grid.georeferenced:
        return None
    t = grid.transform
    if grid.crs.is_geographic:
        rows = np.arange(grid.height) + 0.5
        lat = t.f + rows * t.e
        widths = abs(t.a) * _M_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat))
        return (widths * abs(t.e) * _M_PER_DEG_LAT)[:, None]
    if grid.crs.linear_units not in ("metre", "meter"):
        return None
    return np.full((grid.height, 1), abs(t.a * t.e))


def area_km2(mask, pixel_area):
    if pixel_area is None:
        return None
    return float((mask * pixel_area).sum() / 1e6)

