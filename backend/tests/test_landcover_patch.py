import numpy as np
import pytest

from models import landcover_patch as lp
from raster.band_adapter import resolve_bands
from raster.metadata import read_metadata
from tests.synthetic import WGS84, make_geotiff

torch = pytest.importorskip("torch")
pytest.importorskip("torchvision")


def bgrn_file(tmp_path, name="img.tif", res=10.0, size=60, values=(500, 800, 900, 3000), dtype="uint16", **kw):
    data = np.stack([np.full((size, size), v) for v in values]).astype(dtype)
    path = make_geotiff(tmp_path / name, count=4, width=size, height=size, res=res, data=data, dtype=dtype, **kw)
    meta = read_metadata(path)
    return path, meta, resolve_bands(meta, sensor="cartosat2s")


# --- resampling to 10 m ---------------------------------------------------------------

def test_cartosat_like_2m_image_is_resampled_to_10m(tmp_path):
    path, meta, bands = bgrn_file(tmp_path, res=2.0, size=60)   # 120 m x 120 m at 2 m
    image, info = lp.prepare_input(path, meta, bands)
    assert image.shape == (4, 12, 12)                             # 120 m / 10 m
    assert info["resampled_to_m"] == 10.0 and info["source_resolution_m"] == 2.0
    assert info["shape_10m"] == [12, 12]
    assert np.allclose(image[:, 0, 0], [500, 800, 900, 3000])     # averaging keeps values


def test_2m_average_resampling_mixes_subpixels(tmp_path):
    data = np.zeros((4, 10, 10), dtype="uint16")
    data[:, :, :5] = 1000                                         # left half bright
    data[:, :, 5:] = 3000
    path = make_geotiff(tmp_path / "half.tif", count=4, width=10, height=10, res=2.0, data=data)
    meta = read_metadata(path)
    image, _ = lp.prepare_input(path, meta, resolve_bands(meta, sensor="cartosat2s"))
    assert image.shape == (4, 2, 2)
    assert np.allclose(image[0], [[1000, 3000], [1000, 3000]])


def test_20m_image_is_upsampled_to_10m(tmp_path):
    path, meta, bands = bgrn_file(tmp_path, res=20.0, size=6)
    image, info = lp.prepare_input(path, meta, bands)
    assert image.shape == (4, 12, 12) and info["source_resolution_m"] == 20.0


def test_10m_image_keeps_its_size(tmp_path):
    path, meta, bands = bgrn_file(tmp_path, res=10.0, size=30)
    assert lp.prepare_input(path, meta, bands)[0].shape == (4, 30, 30)


def test_geographic_crs_resolution_in_metres(tmp_path):
    # 0.00009 deg ~ 10 m at 13 N (x ~9.75 m, y ~10.0 m) -> roughly the same size
    path, meta, bands = bgrn_file(tmp_path, res=0.00009, size=40, crs=WGS84, origin=(77.5, 13.0))
    (h, w), src = lp.target_shape(meta)
    assert abs(h - 40) <= 1 and abs(w - 39) <= 1 and 9.5 < src < 10.5


def test_no_crs_is_assumed_10m(tmp_path):
    path, meta, bands = bgrn_file(tmp_path, crs=None, size=20)
    (h, w), src = lp.target_shape(meta)
    assert (h, w) == (20, 20) and src is None


# --- scale detection and band checks ------------------------------------------------------------

def test_reflectance_0_to_1_is_rescaled(tmp_path):
    path, meta, bands = bgrn_file(tmp_path, values=(0.05, 0.08, 0.09, 0.3), dtype="float32", size=12)
    image, info = lp.prepare_input(path, meta, bands)
    assert np.allclose(image[:, 0, 0], [500, 800, 900, 3000], atol=0.1)
    assert info["in_distribution"] and "rescaled" in info["input_scale"]


def test_dn_out_of_range_is_flagged(tmp_path):
    path, meta, bands = bgrn_file(tmp_path, values=(30000, 31000, 32000, 40000), size=12)
    _, info = lp.prepare_input(path, meta, bands)
    assert not info["in_distribution"] and "out of distribution" in info["input_scale"]


def test_missing_bands(tmp_path):
    path = make_geotiff(tmp_path / "rgb.tif", count=3)
    meta = read_metadata(path)
    with pytest.raises(lp.MissingBands, match="missing: nir"):
        lp.prepare_input(path, meta, resolve_bands(meta))


# --- network, windows, classifier ------------------------------------------------------------

def test_adapt_rgb_conv_maps_filters_to_bgrn():
    w = torch.arange(3 * 2 * 1 * 1, dtype=torch.float32).reshape(2, 3, 1, 1)  # R, G, B filters
    out = lp.adapt_rgb_conv(w)
    assert out.shape == (2, 4, 1, 1)
    assert torch.allclose(out[:, 0], w[:, 2] * 0.75)   # blue
    assert torch.allclose(out[:, 2], w[:, 0] * 0.75)   # red
    assert torch.allclose(out[:, 3], w[:, 0] * 0.75)   # NIR copies red


def test_network_takes_four_bands():
    net = lp.build_network().eval()
    with torch.inference_mode():
        assert net(torch.zeros(2, 4, 120, 120)).shape == (2, 19)


@pytest.mark.parametrize("h, w, n", [(120, 120, 1), (240, 120, 3), (250, 130, 8), (50, 50, 1)])
def test_windows_cover_image(h, w, n):
    corners = lp.windows(h, w)
    assert len(corners) == n
    covered = np.zeros((max(h, 120), max(w, 120)), bool)
    for r, c in corners:
        covered[r:r + 120, c:c + 120] = True
    assert covered[:h, :w].all()


def test_resize_nearest():
    a = np.array([[1, 2], [3, 4]])
    assert lp.resize_nearest(a, (4, 4)).tolist() == [[1, 1, 2, 2], [1, 1, 2, 2], [3, 3, 4, 4], [3, 3, 4, 4]]


def make_checkpoint(path, urban_bias=10.0):
    torch.manual_seed(0)
    net = lp.build_network()
    with torch.no_grad():
        net.fc.weight.zero_()
        net.fc.bias.fill_(-10.0)
        net.fc.bias[lp.CLASS_NAMES.index("urban_fabric")] = urban_bias
    torch.save({"format": lp.ARTIFACT_FORMAT, "arch": "resnet18", "bands": list(lp.BANDS),
                "class_names": lp.CLASS_NAMES, "mean": [1000.0] * 4, "std": [500.0] * 4,
                "state_dict": net.state_dict(),
                "meta": {"version": "9.9.9", "trained_on": "unit-test"}}, path)
    return path


def test_classifier_scores_and_trace(tmp_path):
    clf = lp.PatchClassifier.load(make_checkpoint(tmp_path / "m.pt"))
    probs = clf.predict_patches(np.zeros((3, 4, 120, 120), dtype="float32"))
    assert probs.shape == (3, 19) and probs[0, lp.CLASS_NAMES.index("urban_fabric")] > 0.99
    scores, n = clf.score_map(np.zeros((4, 50, 70), dtype="float32"))   # smaller than a patch: padded
    assert scores.shape == (50, 70) and n == 1 and np.all(scores > 0.99)
    assert clf.trace_info == {"model": "resnet18-4band-bigearthnet", "version": "9.9.9",
                              "bands": ["blue", "green", "red", "nir"], "trained_on": "unit-test"}


def test_checkpoint_with_other_bands_is_rejected(tmp_path):
    path = make_checkpoint(tmp_path / "m.pt")
    art = torch.load(path, weights_only=True)
    art["bands"] = ["red", "green", "blue", "nir", "swir1", "swir2"]
    torch.save(art, path)
    with pytest.raises(ValueError, match="checkpoint bands"):
        lp.PatchClassifier.load(path)


def test_availability_and_get_model(tmp_path, monkeypatch):
    path = tmp_path / "lc.pt"
    monkeypatch.setenv("LANDCOVER_PATCH_PATH", str(path))
    ok, reason = lp.availability()
    assert not ok and "ml/landcover_patch/train.py" in reason and lp.get_model() is None
    make_checkpoint(path)
    assert lp.availability() == (True, None)
    assert lp.get_model() is lp.get_model()
