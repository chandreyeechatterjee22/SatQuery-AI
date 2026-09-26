"""Synthetic optical + SAR scenes with known answers (8 x 8 pixels, 10 m, UTM 43N)."""
import numpy as np

# Linear sigma0 values: -23 dB (water), -3 dB (built-up), -13 dB (vegetation).
SAR_WATER, SAR_BUILT, SAR_VEG = 0.005, 0.5, 0.05


def optical_sar_scene():
    """Return (optical BGRN uint16 (4,8,8), SAR VV float32 (1,8,8), expected pixel counts).

    Rows 0-1: water (optical NDWI > 0, SAR -23 dB)        -> 16 px both
    Rows 2-3: built-up (low NDVI, SAR -3 dB)              -> 16 px optical, 15 px SAR
              pixel (3, 7) has vegetation-level SAR        -> 1 px optical-only built-up
    Rows 4-7: vegetation (high NDVI, SAR -13 dB)
              pixel (7, 7) has water-level SAR             -> 1 px SAR-only water
    """
    blue = np.full((8, 8), 500)
    green = np.full((8, 8), 600)
    red = np.full((8, 8), 400)
    nir = np.full((8, 8), 3000)
    green[0:2], red[0:2], nir[0:2] = 1000, 300, 200     # water
    green[2:4], red[2:4], nir[2:4] = 800, 900, 1000      # built-up: NDVI ~ 0.05
    optical = np.stack([blue, green, red, nir]).astype("uint16")

    sar = np.full((8, 8), SAR_VEG, dtype="float32")
    sar[0:2] = SAR_WATER
    sar[2:4] = SAR_BUILT
    sar[3, 7] = SAR_VEG
    sar[7, 7] = SAR_WATER
    return optical, sar[None]


# Land-cover pixel recipes (blue, green, red, nir) for 4-band BGRN images without SWIR.
LC_WATER = (500, 1000, 300, 200)    # NDWI 0.67
LC_VEG = (500, 600, 400, 3000)      # NDVI 0.76
LC_BUILT = (500, 800, 900, 1000)    # NDVI 0.05 (< 0.2 low-NDVI proxy)
LC_OTHER = (500, 800, 900, 1500)    # NDVI 0.25 (between 0.2 and 0.3), NDWI < 0


def landcover_image(rows):
    """8 x 8 BGRN uint16 image from 8 row recipes."""
    img = np.zeros((4, 8, 8), dtype="uint16")
    for r, recipe in enumerate(rows):
        for band, value in enumerate(recipe):
            img[band, r, :] = value
    return img


def bitemporal_scene():
    """Before: 2 rows water, 2 built-up, 4 vegetation.
    After:  2 rows water, 3 built-up, 2 vegetation, 1 other.
    -> water 25 -> 25 (unchanged), built-up 25 -> 37.5, vegetation 50 -> 25, other 0 -> 12.5.
    """
    before = landcover_image([LC_WATER] * 2 + [LC_BUILT] * 2 + [LC_VEG] * 4)
    after = landcover_image([LC_WATER] * 2 + [LC_BUILT] * 3 + [LC_VEG] * 2 + [LC_OTHER])
    return before, after
