from datetime import date

import pytest

from ingest.validation import validate_upload
from tests.synthetic import UTM_43N, WGS84, make_geotiff, make_jpeg, make_png

TODAY = date(2026, 9, 26)


def codes(result):
    return [r["code"] for r in result["reasons"]]


def optical(tmp_path, name="optical.tif", **kw):
    kw.setdefault("count", 4)
    return (name, make_geotiff(tmp_path / name, **kw))


def sar(tmp_path, name="sar.tif", **kw):
    kw.setdefault("count", 2)
    kw.setdefault("dtype", "float32")
    return (name, make_geotiff(tmp_path / name, **kw))


def run(mode, files, **kw):
    kw.setdefault("today", TODAY)
    return validate_upload(mode, files, **kw)


# --- mode and file count -------------------------------------------------

def test_single_geotiff_accepted(tmp_path):
    res = run("single", [optical(tmp_path, count=13)])
    assert res["ok"], res["reasons"]
    f = res["files"][0]
    assert f["slot"] == 1 and f["kind"] == "optical"
    assert f["metadata"]["band_count"] == 13
    assert f["bands"]["sensor"] == "sentinel2"
    assert res["pair"] is None


def test_unknown_mode(tmp_path):
    assert codes(run("triple", [optical(tmp_path)])) == ["invalid_mode"]


@pytest.mark.parametrize("mode, n", [("single", 2), ("optical_sar", 1), ("bi_temporal", 1),
                                     ("single", 0)])
def test_wrong_file_count(tmp_path, mode, n):
    files = [optical(tmp_path, f"f{i}.tif") for i in range(n)]
    res = run(mode, files, dates=["2024-01-01", "2025-01-01"])
    assert codes(res) == ["file_count"]
    assert "exactly" in res["reasons"][0]["message"]


# --- formats ------------------------------------------------------------

def test_png_rejected_without_benchmark_mode(tmp_path):
    res = run("single", [("a.png", make_png(tmp_path / "a.png"))])
    assert codes(res) == ["image_requires_benchmark_mode"]


@pytest.mark.parametrize("maker, name", [(make_png, "a.png"), (make_jpeg, "a.jpg")])
def test_images_accepted_in_benchmark_mode(tmp_path, maker, name):
    res = run("single", [(name, maker(tmp_path / name))], benchmark_mode=True)
    assert res["ok"], res["reasons"]
    assert any("no CRS" in w for w in res["warnings"])


def test_unsupported_extension(tmp_path):
    p = tmp_path / "a.nc"
    p.write_bytes(b"x")
    res = run("single", [("a.nc", p)], benchmark_mode=True)
    assert codes(res) == ["unsupported_format"]


def test_garbage_tif_is_unreadable(tmp_path):
    p = tmp_path / "bad.tif"
    p.write_bytes(b"not a tiff")
    assert codes(run("single", [("bad.tif", p)])) == ["unreadable_raster"]


def test_png_renamed_to_tif_is_mismatch(tmp_path):
    p = make_png(tmp_path / "real.png")
    assert codes(run("single", [("fake.tif", p)])) == ["format_mismatch"]


def test_sensor_hint_mismatch(tmp_path):
    res = run("single", [optical(tmp_path, count=7)], sensors=["sentinel2"])
    assert codes(res) == ["sensor_mismatch"]


def test_single_geotiff_without_crs_only_warns(tmp_path):
    res = run("single", [optical(tmp_path, crs=None)])
    assert res["ok"]
    assert any("no CRS" in w for w in res["warnings"])


# --- optical_sar --------------------------------------------------------

def test_optical_sar_pair_accepted(tmp_path):
    res = run("optical_sar", [optical(tmp_path), sar(tmp_path)])
    assert res["ok"], res["reasons"]
    assert [f["kind"] for f in res["files"]] == ["optical", "sar"]
    assert res["pair"]["same_crs"] is True
    assert res["pair"]["overlap_fraction"] == 1.0


def test_optical_sar_crs_mismatch(tmp_path):
    res = run("optical_sar", [optical(tmp_path),
                              sar(tmp_path, crs=WGS84, origin=(77.5, 13.0), res=0.0001)])
    assert codes(res) == ["crs_mismatch"]
    assert "EPSG:32643" in res["reasons"][0]["message"]


def test_optical_sar_no_overlap(tmp_path):
    res = run("optical_sar", [optical(tmp_path),
                              sar(tmp_path, origin=(900000.0, 1440000.0))])
    assert codes(res) == ["no_overlap"]


def test_partial_overlap_warns(tmp_path):
    # 8x8 px at 10 m = 80 m square; shift by 60 m in x -> 25% overlap.
    res = run("optical_sar", [optical(tmp_path),
                              sar(tmp_path, origin=(780060.0, 1440000.0))])
    assert res["ok"]
    assert res["pair"]["overlap_fraction"] == 0.25
    assert any("overlap by only 25%" in w for w in res["warnings"])


def test_touching_edges_do_not_overlap(tmp_path):
    res = run("optical_sar", [optical(tmp_path),
                              sar(tmp_path, origin=(780080.0, 1440000.0))])
    assert codes(res) == ["no_overlap"]


def test_different_resolution_warns(tmp_path):
    res = run("optical_sar", [optical(tmp_path), sar(tmp_path, res=20.0, width=4, height=4)])
    assert res["ok"]
    assert res["pair"]["same_resolution"] is False
    assert any("resampled" in w for w in res["warnings"])


def test_files_in_wrong_order_are_rejected(tmp_path):
    res = run("optical_sar", [sar(tmp_path), optical(tmp_path)])
    assert codes(res) == ["wrong_modality", "wrong_modality"]
    assert "must be the SAR image" in res["reasons"][1]["message"]
    assert all(r["file"] in (1, 2) for r in res["reasons"])


def test_optical_slot_with_sar_descriptions(tmp_path):
    res = run("optical_sar", [optical(tmp_path, count=2, descriptions=["VV", "VH"]),
                              sar(tmp_path)])
    assert codes(res) == ["wrong_modality"]


def test_sar_slot_with_optical_descriptions(tmp_path):
    res = run("optical_sar", [optical(tmp_path),
                              sar(tmp_path, count=2, descriptions=["red", "nir"])])
    assert codes(res) == ["wrong_modality"]


def test_sar_slot_single_band(tmp_path):
    res = run("optical_sar", [optical(tmp_path), sar(tmp_path, count=1)])
    assert res["ok"]
    assert res["files"][1]["bands"]["roles"] == {"vv": 1}


def test_pair_missing_crs_rejected(tmp_path):
    res = run("optical_sar", [optical(tmp_path), sar(tmp_path, crs=None)])
    assert codes(res) == ["missing_crs"]
    assert "2" in res["reasons"][0]["message"]


# --- bi_temporal --------------------------------------------------------

def test_bi_temporal_accepted(tmp_path):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif"), optical(tmp_path, "t2.tif")],
              dates=["2023-03-01", "2025-03-01"])
    assert res["ok"], res["reasons"]
    assert [f["date"] for f in res["files"]] == ["2023-03-01", "2025-03-01"]


def test_bi_temporal_missing_dates(tmp_path):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif"), optical(tmp_path, "t2.tif")],
              dates=["2023-03-01", ""])
    assert codes(res) == ["missing_date"]
    assert res["reasons"][0]["file"] == 2


def test_bi_temporal_same_date(tmp_path):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif"), optical(tmp_path, "t2.tif")],
              dates=["2024-05-05", "2024-05-05"])
    assert codes(res) == ["same_date"]


@pytest.mark.parametrize("bad", ["2024-13-01", "05/05/2024", "yesterday"])
def test_bi_temporal_invalid_date(tmp_path, bad):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif"), optical(tmp_path, "t2.tif")],
              dates=["2024-01-01", bad])
    assert codes(res) == ["invalid_date"]


def test_future_date_rejected(tmp_path):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif"), optical(tmp_path, "t2.tif")],
              dates=["2024-01-01", "2027-01-01"])
    assert codes(res) == ["future_date"]


def test_reverse_chronological_order_warns(tmp_path):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif"), optical(tmp_path, "t2.tif")],
              dates=["2025-01-01", "2023-01-01"])
    assert res["ok"]
    assert any("chronological" in w for w in res["warnings"])


def test_bi_temporal_mixed_modalities_rejected(tmp_path):
    res = run("bi_temporal", [optical(tmp_path), sar(tmp_path)],
              dates=["2023-01-01", "2024-01-01"])
    assert codes(res) == ["modality_mismatch"]


def test_bi_temporal_band_count_difference_warns(tmp_path):
    res = run("bi_temporal", [optical(tmp_path, "t1.tif", count=13),
                              optical(tmp_path, "t2.tif", count=4)],
              dates=["2023-01-01", "2024-01-01"])
    assert res["ok"]
    assert any("Band counts differ" in w for w in res["warnings"])


def test_all_problems_reported_together(tmp_path):
    p = tmp_path / "bad.tif"
    p.write_bytes(b"junk")
    res = run("bi_temporal", [("bad.tif", p), optical(tmp_path, "t2.tif")],
              dates=["2024-01-01", "2024-01-01"])
    assert set(codes(res)) == {"same_date", "unreadable_raster"}


# --- benchmark pairs ------------------------------------------------------

def test_benchmark_png_pair_same_size(tmp_path):
    res = run("bi_temporal", [("a.png", make_png(tmp_path / "a.png")),
                              ("b.png", make_png(tmp_path / "b.png"))],
              dates=["2023-01-01", "2024-01-01"], benchmark_mode=True)
    assert res["ok"], res["reasons"]
    assert any("pixel-aligned" in w for w in res["warnings"])


def test_benchmark_png_pair_size_mismatch(tmp_path):
    res = run("bi_temporal", [("a.png", make_png(tmp_path / "a.png")),
                              ("b.png", make_png(tmp_path / "b.png", width=16))],
              dates=["2023-01-01", "2024-01-01"], benchmark_mode=True)
    assert codes(res) == ["size_mismatch"]


def test_utm_constant_is_used(tmp_path):
    # Guard: the synthetic helper really writes the CRS we assert on elsewhere.
    res = run("single", [optical(tmp_path)])
    assert res["files"][0]["metadata"]["crs"] == UTM_43N


# --- explicit band roles ------------------------------------------------------------

def test_band_roles_make_custom_layout_usable(tmp_path):
    res = run("single", [optical(tmp_path, count=5)], band_roles=["blue,green,red,nir,swir1"])
    assert res["ok"], res["reasons"]
    assert res["files"][0]["bands"]["roles"]["swir1"] == 5
    assert not any("could not infer" in w for w in res["warnings"])


def test_band_roles_for_sar_slot(tmp_path):
    res = run("optical_sar", [optical(tmp_path), sar(tmp_path)], band_roles=[None, "vh,vv"])
    assert res["ok"]
    assert res["files"][1]["bands"]["roles"] == {"vh": 1, "vv": 2}


def test_bad_band_roles_rejected(tmp_path):
    res = run("single", [optical(tmp_path, count=5)], band_roles=["blue,green,red"])
    assert codes(res) == ["invalid_band_roles"]
    assert "3 entries but the file has 5" in res["reasons"][0]["message"]


def test_optical_slot_with_sar_band_roles(tmp_path):
    res = run("optical_sar", [optical(tmp_path, count=2), sar(tmp_path)], band_roles=["vv,vh", None])
    assert codes(res) == ["wrong_modality"]


def test_webp_named_jpg_is_accepted_as_photo_with_warning(tmp_path):
    import numpy as np
    import rasterio

    path = tmp_path / "download.jpg"
    with rasterio.open(path, "w", driver="WEBP", width=16, height=16, count=3, dtype="uint8") as dst:
        dst.write(np.full((3, 16, 16), 120, dtype="uint8"))
    res = run("single", [("download.jpg", path)], benchmark_mode=True)
    assert res["ok"], res["reasons"]
    assert res["files"][0]["metadata"]["driver"] == "WEBP"
    assert any("is actually WEBP; read as a photo" in w for w in res["warnings"])
    # Without benchmark (photo) mode it is still rejected with a clear reason.
    assert codes(run("single", [("download.jpg", path)])) == ["image_requires_benchmark_mode"]


def test_files_without_extension_are_identified_by_content(tmp_path):
    import shutil

    tif = make_geotiff(tmp_path / "scene.tif", count=4)
    shutil.copyfile(tif, tmp_path / "scene")
    res = run("single", [("scene", tmp_path / "scene")])
    assert res["ok"], res["reasons"]
    assert any("no file extension; detected GTiff" in w for w in res["warnings"])

    png = make_png(tmp_path / "photo.png")
    shutil.copyfile(png, tmp_path / "photo")
    assert codes(run("single", [("photo", tmp_path / "photo")])) == ["image_requires_benchmark_mode"]
    res = run("single", [("photo", tmp_path / "photo")], benchmark_mode=True)
    assert res["ok"] and any("detected PNG" in w for w in res["warnings"])

    junk = tmp_path / "notes"
    junk.write_bytes(b"hello")
    assert codes(run("single", [("notes", junk)])) == ["unreadable_raster"]
