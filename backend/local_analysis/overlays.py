"""Colour boolean masks into RGBA PNG overlays (transparent where nothing is flagged)."""
import numpy as np

from raster.preview import write_png


def hex_to_rgba(hex_colour, alpha):
    h = hex_colour.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def render_overlay(layers, shape, out_path):
    """``layers``: list of (bool mask, "#rrggbb", alpha); later layers paint over earlier ones."""
    rgba = np.zeros((4,) + tuple(shape), dtype="uint8")
    for mask, colour, alpha in layers:
        for channel, value in enumerate(hex_to_rgba(colour, alpha)):
            rgba[channel][mask] = value
    write_png(out_path, rgba)
    return out_path
