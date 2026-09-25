import numpy as np
import pytest
import rasterio

from local_analysis.grid import area_km2, grid_for, pixel_area_m2, read_on_grid
from local_analysis.indices import normalized_difference, sar_to_db
from local_analysis.optical_sar import map_water_builtup
from local_analysis.overlays import hex_to_rgba, render_overlay
from raster.band_adapter import resolve_bands
from raster.metadata import read_metadata
from tests.scenes import optical_sar_scene
from tests.synthetic import WGS84, make_geotiff

pytestmark = pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")


# --- indices ----------------------------------------------------------------

def test_normalized_difference_handles_zero_and_nan():
    a = np.array([3.0, 0.0, np.nan, 1.0])
    b = np.array([1.0, 0.0, 1.0, 3.0])
    out = normalized_difference(a, b)
    assert out[0] == 0.5 and np.isnan(out[1]) and np.isnan(out[2]) and out[3] == -0.5


def test_sar_linear_to_db():
    db, linear, calibrated = sar_to_db(np.array([0.01, 0.1, 1.0, 0.0]))
    assert linear and calibrated
    assert np.allclose(db[:3], [-20, -10, 0]) and np.isnan(db[3])


def test_sar_already_db_is_kept():
    db, linear, calibrated = sar_to_db(np.array([-20.0, -5.0, 1.0]))
    assert not linear and calibrated and db.tolist() == [-20.0, -5.0, 1.0]


def test_sar_uncalibrated_dn_is_flagged():
    _, linear, calibrated = sar_to_db(np.array([5000.0, 20000.0, 64000.0]))
    assert linear and not calibrated


# --- grid ---------------------------------------------------------------------

def test_grid_downsamples_and_averages(tmp_path):
    p = make_geotiff(tmp_path / "a.tif", count=1, data=np.arange(64, dtype="uint16").reshape(1, 8, 8))
    g = grid_for(p, max_size=4)
    assert g.shape == (4, 4) and g.transform.a == 20.0
    assert read_on_grid(p, [1], g)[0, 0, 0] == 4.5  # mean of 0, 1, 8, 9
    assert pixel_area_m2(g)[0, 0] == 400.0


def test_other_raster_is_reprojected_with_nan_outside(tmp_path):
    a = make_geotiff(tmp_path / "a.tif", count=1)
    b = make_geotiff(tmp_path / "b.tif", count=1, dtype="float32", origin=(780040.0, 1440000.0),
                     data=np.ones((1, 8, 8), dtype="float32"))
    row = read_on_grid(b, [1], grid_for(a))[0, 0]
    assert np.isnan(row[:4]).all() and (row[4:] == 1).all()


def test_geographic_pixel_area_is_approximate_but_sane(tmp_path):
    p = make_geotiff(tmp_path / "g.tif", count=1, crs=WGS84, origin=(77.5, 13.0), res=0.0001)
    area = pixel_area_m2(grid_for(p))
    assert 115 < area[0, 0] < 125  # ~0.0001 deg at 13 N is ~10.8 m x 11.1 m


def test_no_crs_has_no_area(tmp_path):
    p = make_geotiff(tmp_path / "n.tif", count=1, crs=None)
    g = grid_for(p)
    assert pixel_area_m2(g) is None and area_km2(np.ones(g.shape, bool), None) is None


# --- overlays -------------------------------------------------------------------

def test_overlay_png(tmp_path):
    mask_a = np.zeros((2, 2), bool)
    mask_a[0, 0] = True
    mask_b = np.zeros((2, 2), bool)
    mask_b[1, 1] = True
    out = render_overlay([(mask_a, "#ff0000", 200), (mask_b, "#0000ff", 100)], (2, 2), tmp_path / "o.png")
    with rasterio.open(out) as src:
        rgba = src.read()
    assert rgba[:, 0, 0].tolist() == [255, 0, 0, 200]
    assert rgba[:, 1, 1].tolist() == [0, 0, 255, 100]
    assert rgba[3, 0, 1] == 0
    assert hex_to_rgba("#1f6feb", 5) == (31, 111, 235, 5)


# --- water / built-up ----------------------------------------------------------------

@pytest.fixture
def scene(tmp_path):
    optical, sar = optical_sar_scene()
    opt = make_geotiff(tmp_path / "opt.tif", count=4, data=optical)
    s = make_geotiff(tmp_path / "sar.tif", count=1, dtype="float32", data=sar)
    return (opt, resolve_bands(read_metadata(opt), "cartosat2s"),
            s, resolve_bands(read_metadata(s), expected_kind="sar"))


def test_water_and_builtup_with_and_fusion(scene):
    res = map_water_builtup(*scene)
    w, b = res["stats"]["water"], res["stats"]["built_up"]

    assert res["valid_pixels"] == 64 and res["valid_area_km2"] == 0.0064
    assert w == {"percent": 25.0, "pixels": 16, "area_km2": 0.0016, "both_percent": 25.0,
                 "optical_only_percent": 0.0, "sar_only_percent": 1.56, "optical_percent": 25.0,
                 "sar_percent": 26.56, "agreement": round(16 / 17, 4), "detected_by": ["optical", "sar"]}
    assert b["pixels"] == 15 and b["percent"] == 23.44
    assert b["optical_percent"] == 25.0 and b["sar_percent"] == 23.44
    assert b["optical_only_percent"] == 1.56 and b["sar_only_percent"] == 0.0
    assert b["agreement"] == round(15 / 16, 4)
    assert res["methods"]["optical_water"] == "NDWI (green, NIR)"
    assert res["methods"]["optical_built_up"].startswith("low NDVI")
    assert res["methods"]["sar_band"] == "VV (linear, converted to dB)"
    assert any("no SWIR band" in w for w in res["warnings"])


def test_or_fusion_takes_either_modality(scene):
    res = map_water_builtup(*scene, params={"fusion": "or"})
    assert res["stats"]["water"]["pixels"] == 17
    assert res["stats"]["built_up"]["pixels"] == 16


def test_builtup_never_overlaps_final_water(scene):
    res = map_water_builtup(*scene, params={"fusion": "or", "sar_builtup_db": -30, "sar_water_db": -35})
    water, built = res["masks"]["water"]["final"], res["masks"]["built_up"]["final"]
    assert not (water & built).any()


def test_thresholds_change_results(scene):
    strict = map_water_builtup(*scene, params={"sar_water_db": -25})
    assert strict["stats"]["water"]["sar_percent"] == 0.0
    assert strict["stats"]["water"]["percent"] == 0.0


def test_only_requested_classes_returned(scene):
    res = map_water_builtup(*scene, classes=("water",))
    assert set(res["stats"]) == {"water"} and set(res["masks"]) == {"water"}


def test_rgb_optical_falls_back_to_sar_only(tmp_path):
    optical, sar = optical_sar_scene()
    opt = make_geotiff(tmp_path / "rgb.tif", count=3, data=optical[:3])
    s = make_geotiff(tmp_path / "sar.tif", count=1, dtype="float32", data=sar)
    res = map_water_builtup(opt, resolve_bands(read_metadata(opt)), s,
                            resolve_bands(read_metadata(s), expected_kind="sar"))
    w = res["stats"]["water"]
    assert w["pixels"] == 17 and w["detected_by"] == ["sar"]
    assert w["both_percent"] is None and w["agreement"] is None
    assert res["methods"]["optical_water"] is None
    assert any("SAR only" in x for x in res["warnings"])


def test_sentinel2_bands_use_mndwi_and_ndbi(tmp_path):
    optical, sar = optical_sar_scene()
    s2 = np.zeros((10, 8, 8), dtype="uint16")      # 10-band S2 layout: B2 B3 B4 B5 B6 B7 B8 B8A B11 B12
    s2[0], s2[1], s2[2], s2[6] = optical            # blue, green, red, nir
    s2[8] = np.where(np.arange(8)[:, None] < 2, 100, 1500)  # SWIR1: low on water rows
    s2[8][2:4] = 2000                                # SWIR1 > NIR on built-up rows -> NDBI > 0
    opt = make_geotiff(tmp_path / "s2.tif", count=10, data=s2)
    sp = make_geotiff(tmp_path / "sar.tif", count=1, dtype="float32", data=sar)
    res = map_water_builtup(opt, resolve_bands(read_metadata(opt)), sp,
                            resolve_bands(read_metadata(sp), expected_kind="sar"))
    assert res["methods"]["optical_water"] == "MNDWI (green, SWIR1)"
    assert res["methods"]["optical_built_up"] == "NDBI (SWIR1, NIR)"
    assert res["stats"]["water"]["optical_percent"] == 25.0
    assert res["stats"]["built_up"]["optical_percent"] == 25.0


def test_sar_nodata_reduces_valid_area(tmp_path):
    optical, sar = optical_sar_scene()
    sar = sar.copy()
    sar[0, :, :4] = 0.0  # left half zero = GRD border nodata
    opt = make_geotiff(tmp_path / "o.tif", count=4, data=optical)
    sp = make_geotiff(tmp_path / "s.tif", count=1, dtype="float32", data=sar)
    res = map_water_builtup(opt, resolve_bands(read_metadata(opt)), sp,
                            resolve_bands(read_metadata(sp), expected_kind="sar"))
    assert res["valid_pixels"] == 32
    assert res["stats"]["water"]["percent"] == 25.0  # 8 of the 32 valid pixels


def test_no_common_valid_pixels_raises(tmp_path):
    optical, sar = optical_sar_scene()
    opt = make_geotiff(tmp_path / "o.tif", count=4, data=optical)
    sp = make_geotiff(tmp_path / "s.tif", count=1, dtype="float32", data=np.zeros_like(sar))
    with pytest.raises(ValueError, match="no valid pixels in common"):
        map_water_builtup(opt, resolve_bands(read_metadata(opt)), sp,
                          resolve_bands(read_metadata(sp), expected_kind="sar"))
