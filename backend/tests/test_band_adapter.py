import pytest

from raster.band_adapter import BandAdapterError, resolve_bands


def meta(count, descriptions=None, driver="GTiff"):
    return {"band_count": count, "band_descriptions": descriptions or [None] * count,
            "driver": driver}


@pytest.mark.parametrize("count, nir, swir1", [(13, 8, 12), (12, 8, 11), (10, 7, 9)])
def test_sentinel2_auto_by_count(count, nir, swir1):
    p = resolve_bands(meta(count))
    assert p["sensor"] == "sentinel2" and p["kind"] == "optical"
    assert p["roles"]["nir"] == nir
    assert p["roles"]["swir1"] == swir1
    assert p["source"] == "band_count"


def test_sentinel2_13_band_roles():
    roles = resolve_bands(meta(13))["roles"]
    assert roles == {"blue": 2, "green": 3, "red": 4, "nir": 8, "swir1": 12, "swir2": 13}


def test_four_band_defaults_to_bgrn_with_warning():
    p = resolve_bands(meta(4))
    assert p["roles"] == {"blue": 1, "green": 2, "red": 3, "nir": 4}
    assert p["warnings"] and "Cartosat-2S" in p["warnings"][0]


def test_cartosat_hint_has_no_warning():
    p = resolve_bands(meta(4), sensor="cartosat2s")
    assert p["sensor"] == "cartosat2s"
    assert p["roles"] == {"blue": 1, "green": 2, "red": 3, "nir": 4}
    assert p["warnings"] == []


def test_sentinel2_four_band_hint():
    p = resolve_bands(meta(4), sensor="sentinel2")
    assert p["band_names"] == ["B2", "B3", "B4", "B8"]
    assert p["roles"] == {"blue": 1, "green": 2, "red": 3, "nir": 4}


@pytest.mark.parametrize("count, roles", [(1, {"vv": 1}), (2, {"vv": 1, "vh": 2})])
def test_sar_auto(count, roles):
    p = resolve_bands(meta(count))
    assert p["kind"] == "sar" and p["roles"] == roles
    assert p["warnings"]


def test_sar_from_descriptions():
    p = resolve_bands(meta(2, ["HH", "HV"]))
    assert p["kind"] == "sar"
    assert p["roles"] == {"hh": 1, "hv": 2}
    assert p["source"] == "descriptions"
    assert p["warnings"] == []


def test_generic_descriptions_win_over_count():
    p = resolve_bands(meta(4, ["Red", "Green", "Blue", "Near Infrared"]))
    assert p["roles"] == {"red": 1, "green": 2, "blue": 3, "nir": 4}
    assert p["warnings"] == []


def test_sentinel2_codes_in_descriptions():
    names = ["B02", "B03", "B04", "B08", "B11", "B12"]
    p = resolve_bands(meta(6, names))
    assert p["sensor"] == "sentinel2"
    assert p["roles"] == {"blue": 1, "green": 2, "red": 3, "nir": 4, "swir1": 5, "swir2": 6}


def test_ambiguous_b_codes_are_not_treated_as_sentinel2():
    # A 4-band file labelled B1..B4 (as Cartosat does) must not get S2 roles,
    # where B2 would be blue; here B2 is green.
    p = resolve_bands(meta(4, ["B1", "B2", "B3", "B4"]))
    assert p["sensor"] == "bgrn"
    assert p["roles"]["green"] == 2


def test_png_rgb_has_no_warning():
    p = resolve_bands(meta(3, driver="PNG"))
    assert p["sensor"] == "rgb" and p["warnings"] == []
    assert p["roles"] == {"red": 1, "green": 2, "blue": 3}


def test_unknown_band_count_is_unresolved():
    p = resolve_bands(meta(7))
    assert p["source"] == "unresolved" and p["roles"] == {}
    assert p["warnings"]


def test_expected_sar_slot_forces_sar():
    assert resolve_bands(meta(1), expected_kind="sar")["kind"] == "sar"


def test_expected_optical_slot_does_not_force_sar():
    assert resolve_bands(meta(1), expected_kind="optical")["kind"] == "optical"


@pytest.mark.parametrize("sensor, count, match", [
    ("sentinel2", 7, "sentinel2 expects"),
    ("sar", 3, "1 or 2 bands"),
    ("cartosat2s", 3, "cartosat2s expects 4"),
    ("rgb", 4, "rgb expects 3"),
    ("landsat", 7, "unknown sensor"),
])
def test_hint_mismatch_raises(sensor, count, match):
    with pytest.raises(BandAdapterError, match=match):
        resolve_bands(meta(count), sensor=sensor)
