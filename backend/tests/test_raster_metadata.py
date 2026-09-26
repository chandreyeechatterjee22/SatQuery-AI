import pytest

from raster.metadata import RasterReadError, read_metadata
from tests.synthetic import WGS84, make_geotiff, make_png


def test_reads_multiband_geotiff(tmp_path):
    path = make_geotiff(tmp_path / "s2.tif", count=13, width=10, height=6, res=10.0)
    meta = read_metadata(path)

    assert meta["driver"] == "GTiff"
    assert meta["band_count"] == 13
    assert meta["width"] == 10 and meta["height"] == 6
    assert meta["dtypes"] == ["uint16"] * 13
    assert meta["epsg"] == 32643
    assert meta["crs_is_geographic"] is False
    assert meta["resolution"] == {"x": 10.0, "y": 10.0, "units": "metres"}
    assert meta["bounds"] == {"left": 780000.0, "bottom": 1439940.0,
                              "right": 780100.0, "top": 1440000.0}
    assert meta["georeferenced"] is True


@pytest.mark.parametrize("count, dtype", [(1, "float32"), (2, "float32"), (4, "uint16")])
def test_any_band_count(tmp_path, count, dtype):
    meta = read_metadata(make_geotiff(tmp_path / "x.tif", count=count, dtype=dtype))
    assert meta["band_count"] == count
    assert meta["dtypes"] == [dtype] * count


def test_band_descriptions_and_nodata(tmp_path):
    path = make_geotiff(tmp_path / "sar.tif", count=2, dtype="float32",
                        descriptions=["VV", "VH"], nodata=-9999.0)
    meta = read_metadata(path)
    assert meta["band_descriptions"] == ["VV", "VH"]
    assert meta["nodata"] == -9999.0


def test_missing_descriptions_are_none(tmp_path):
    meta = read_metadata(make_geotiff(tmp_path / "x.tif", count=3))
    assert meta["band_descriptions"] == [None, None, None]


def test_geographic_crs_units(tmp_path):
    path = make_geotiff(tmp_path / "geo.tif", count=1, crs=WGS84,
                        origin=(77.5, 13.0), res=0.0001)
    meta = read_metadata(path)
    assert meta["epsg"] == 4326
    assert meta["crs_is_geographic"] is True
    assert meta["resolution"]["units"] == "degrees"


def test_geotiff_without_crs_is_not_georeferenced(tmp_path):
    meta = read_metadata(make_geotiff(tmp_path / "nocrs.tif", crs=None))
    assert meta["crs"] is None
    assert meta["georeferenced"] is False
    assert meta["resolution"]["units"] == "pixels"


def test_png_reads_as_image(tmp_path):
    meta = read_metadata(make_png(tmp_path / "a.png"))
    assert meta["driver"] == "PNG"
    assert meta["band_count"] == 3
    assert meta["georeferenced"] is False


def test_garbage_file_raises(tmp_path):
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"this is not a tiff")
    with pytest.raises(RasterReadError, match="not a readable raster"):
        read_metadata(bad)


@pytest.mark.parametrize("nodata, expected", [(float("-inf"), "-inf"), (float("nan"), "nan"),
                                              (float("inf"), "inf"), (0.0, 0.0)])
def test_non_finite_nodata_is_json_safe(tmp_path, nodata, expected):
    import json

    meta = read_metadata(make_geotiff(tmp_path / "x.tif", count=1, dtype="float32", nodata=nodata))
    assert meta["nodata"] == expected
    json.dumps(meta, allow_nan=False)  # must not raise
