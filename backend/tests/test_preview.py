import numpy as np
import rasterio

from raster.preview import preview_bands, render_preview
from tests.synthetic import make_geotiff


def read_png(path):
    with rasterio.open(path) as src:
        return src.read()


def test_preview_band_choice():
    assert preview_bands({"kind": "optical", "roles": {"blue": 1, "green": 2, "red": 3, "nir": 4}}) \
        == ([3, 2, 1], "rgb")
    assert preview_bands({"kind": "optical", "roles": {}}) == ([1], "gray")
    assert preview_bands({"kind": "sar", "roles": {"vv": 1, "vh": 2}}) == ([1], "sar_db")
    assert preview_bands({"kind": "sar", "roles": {"hv": 2}}) == ([2], "sar_db")


def test_rgb_preview_uses_role_order_and_stretch(tmp_path):
    data = np.zeros((4, 4, 4), dtype="uint16")
    data[0] = 100   # blue
    data[1] = 200   # green
    data[2, :, :2], data[2, :, 2:] = 0, 1000  # red: half dark, half bright
    src = make_geotiff(tmp_path / "a.tif", count=4, width=4, height=4, data=data)
    info = render_preview(src, {"kind": "optical", "roles": {"blue": 1, "green": 2, "red": 3}},
                          tmp_path / "p.png")

    png = read_png(tmp_path / "p.png")
    assert info == {"width": 4, "height": 4, "rendering": "rgb", "bands": [3, 2, 1]}
    assert png.shape == (4, 4, 4) and png.dtype == np.uint8
    assert png[0, 0, 0] == 0 and png[0, 0, 3] == 255     # red channel stretched 0..255
    assert (png[3] == 255).all()                          # fully opaque


def test_nodata_becomes_transparent(tmp_path):
    data = np.full((1, 4, 4), 500, dtype="int16")
    data[0, 0, 0] = -1
    src = make_geotiff(tmp_path / "a.tif", count=1, width=4, height=4, dtype="int16",
                       nodata=-1, data=data)
    render_preview(src, {"kind": "optical", "roles": {}}, tmp_path / "p.png")
    alpha = read_png(tmp_path / "p.png")[3]
    assert alpha[0, 0] == 0 and alpha[1, 1] == 255


def test_large_image_is_downsampled(tmp_path):
    src = make_geotiff(tmp_path / "big.tif", count=1, width=300, height=150)
    info = render_preview(src, {"kind": "optical", "roles": {}}, tmp_path / "p.png", max_size=100)
    assert (info["width"], info["height"]) == (100, 50)
    assert read_png(tmp_path / "p.png").shape == (4, 50, 100)


def test_sar_linear_converted_to_db(tmp_path):
    data = np.array([[[0.001, 0.01], [0.1, 1.0]]], dtype="float32")
    src = make_geotiff(tmp_path / "s.tif", count=1, width=2, height=2, dtype="float32", data=data)
    info = render_preview(src, {"kind": "sar", "roles": {"vv": 1}}, tmp_path / "p.png")
    png = read_png(tmp_path / "p.png")
    assert info["rendering"] == "sar_db"
    # dB spacing is even (-30, -20, -10, 0), so grey levels increase monotonically.
    grey = png[0].ravel()
    assert list(grey) == sorted(grey) and grey[0] < grey[-1]
    assert (png[0] == png[1]).all() and (png[1] == png[2]).all()


def test_constant_image_does_not_crash(tmp_path):
    data = np.full((1, 3, 3), 7, dtype="uint8")
    src = make_geotiff(tmp_path / "c.tif", count=1, width=3, height=3, dtype="uint8", data=data)
    render_preview(src, {"kind": "optical", "roles": {}}, tmp_path / "p.png")
    assert read_png(tmp_path / "p.png").shape == (4, 3, 3)
