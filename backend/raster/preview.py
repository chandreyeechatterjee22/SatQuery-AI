"""Render a quicklook PNG (RGBA, uint8) of an uploaded raster for display.

Optical: true colour from the red/green/blue band roles when present,
otherwise the first band in grey. SAR: first polarisation in dB, grey.
Each band gets a 2-98 percentile stretch; nodata becomes transparent.
"""
import warnings

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import NotGeoreferencedWarning

MAX_PREVIEW_SIZE = 1024


def preview_bands(bands):
    """Pick (band indexes, rendering) for a band profile from raster.band_adapter."""
    roles = bands.get("roles", {})
    if bands.get("kind") == "sar":
        for pol in ("vv", "hh", "vh", "hv"):
            if pol in roles:
                return [roles[pol]], "sar_db"
        return [1], "sar_db"
    if all(r in roles for r in ("red", "green", "blue")):
        return [roles["red"], roles["green"], roles["blue"]], "rgb"
    return [1], "gray"


def display_rgb(src_path, bands, max_size=MAX_PREVIEW_SIZE):
    """Read and stretch a raster for display or model input.

    Returns (rgb uint8 array (3, H, W), valid mask (H, W), rendering, band indexes).
    """
    indexes, rendering = preview_bands(bands)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(src_path) as src:
            scale = max(src.width, src.height) / max_size
            height, width = src.height, src.width
            if scale > 1:
                height, width = max(1, round(src.height / scale)), max(1, round(src.width / scale))
            data = src.read(indexes, out_shape=(len(indexes), height, width), masked=True,
                            resampling=Resampling.average).astype("float64")

    valid = ~np.ma.getmaskarray(data).any(axis=0) & np.isfinite(data.filled(np.nan)).all(axis=0)
    if rendering == "sar_db":
        data = to_db_if_linear(data, valid)
    channels = [stretch(band, valid) for band in data]
    if len(channels) == 1:
        channels = channels * 3
    return np.stack(channels), valid, rendering, indexes


def render_preview(src_path, bands, out_path, max_size=MAX_PREVIEW_SIZE):
    rgb, valid, rendering, indexes = display_rgb(src_path, bands, max_size)
    alpha = np.where(valid, 255, 0).astype("uint8")
    write_png(out_path, np.concatenate([rgb, alpha[None]]))
    return {"width": rgb.shape[2], "height": rgb.shape[1], "rendering": rendering, "bands": indexes}


def write_png(out_path, rgba):
    """Write a (4, H, W) uint8 array as an RGBA PNG."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(out_path, "w", driver="PNG", width=rgba.shape[2],
                           height=rgba.shape[1], count=4, dtype="uint8") as dst:
            dst.write(rgba)


def to_db_if_linear(data, valid):
    """Convert linear SAR backscatter to dB. Values already in dB (negatives) are kept."""
    values = data.filled(np.nan)[:, valid]
    if values.size and np.nanmin(values) >= 0:
        return np.ma.masked_array(10 * np.log10(np.maximum(data.filled(0), 1e-6)), mask=data.mask)
    return data


def stretch(band, valid, low=2, high=98):
    out = np.zeros(band.shape, dtype="uint8")
    values = band.filled(np.nan)[valid]
    if values.size == 0:
        return out
    lo, hi = np.percentile(values, [low, high])
    if hi <= lo:
        hi = lo + 1
    scaled = np.clip((band.filled(lo) - lo) / (hi - lo), 0, 1) * 255
    out[valid] = scaled[valid].round().astype("uint8")
    return out
