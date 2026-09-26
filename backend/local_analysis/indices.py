"""Spectral indices and SAR scaling. Inputs are float arrays with NaN for nodata."""
import numpy as np


def normalized_difference(a, b):
    """(a - b) / (a + b); NaN where the denominator is 0 or either input is NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = a + b
        out = (a - b) / denom
    out[denom == 0] = np.nan
    return out


def sar_to_db(values):
    """Return (dB array, was_linear, looks_calibrated).

    All-non-negative data is treated as linear power and converted (zeros become
    NaN, as they are border nodata in GRD products). Data with negatives is taken
    as dB already. ``looks_calibrated`` is False when the median is outside
    [-40, 10] dB, i.e. probably uncalibrated DNs where the thresholds do not apply.
    """
    finite = values[np.isfinite(values)]
    was_linear = bool(finite.size) and float(finite.min()) >= 0
    if was_linear:
        with np.errstate(divide="ignore", invalid="ignore"):
            db = 10 * np.log10(np.where(values > 0, values, np.nan))
    else:
        db = values.copy()
    finite_db = db[np.isfinite(db)]
    looks_calibrated = bool(finite_db.size) and -40.0 <= float(np.median(finite_db)) <= 10.0
    return db, was_linear, looks_calibrated
