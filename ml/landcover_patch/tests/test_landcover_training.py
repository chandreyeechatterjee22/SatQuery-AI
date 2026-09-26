"""Tests for the BigEarthNet land-cover pipeline on tiny synthetic data (no downloads)."""
import io
import random

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from PIL import Image

import common
from data import N_CLASSES, Split, band_stats, decode, inverse_tone_map, multi_hot, torch_dataset
from download_bigearthnet_subset import select
from metrics import average_precision, evaluate

torch = pytest.importorskip("torch")


def forward_tone_map(dn):
    """Forward curve from the dataset card (used here only to build test inputs)."""
    scale, white, knee, gamma = 3500., 12000., 0.6, 2.2
    x = np.asarray(dn, dtype=float) / scale
    tw = (white / scale - knee) / (1 - knee)
    s = np.clip((x - knee) / (1 - knee), 0, None)
    y = np.where(x <= knee, x, knee + (1 - knee) * (s * (1 + s / tw ** 2) / (1 + s)))
    return np.round(255 * y ** (1 / 2.2)).astype(np.uint8)


def png(array, mode=None):
    buf = io.BytesIO()
    Image.fromarray(array, mode=mode).save(buf, format="PNG")
    return buf.getvalue()


def row(r_dn, g_dn, b_dn, nir, labels, size=8):
    rgb = np.stack([np.full((size, size), forward_tone_map(v)) for v in (r_dn, g_dn, b_dn)], axis=-1)
    return {"image": {"bytes": png(rgb), "path": None},
            "nir": {"bytes": png(np.full((size, size), nir, dtype=np.uint16)), "path": None},
            "labels": labels, "image_id": f"id{r_dn}", "country": "Testland"}


# --- decoding --------------------------------------------------------------------------

def test_inverse_tone_map_round_trip():
    dn = np.array([100, 500, 1000, 2000, 3000, 6000, 11000])
    back = inverse_tone_map(forward_tone_map(dn))
    assert np.all(np.abs(back - dn) / dn < 0.05)


def test_decode_band_order_and_scale():
    r = row(900, 800, 500, 3000, [2])
    x = decode(r["image"]["bytes"], r["nir"]["bytes"])
    assert x.shape == (4, 8, 8) and x.dtype == np.float32
    b, g, red, nir = x[:, 0, 0]
    assert abs(b - 500) < 25 and abs(g - 800) < 30 and abs(red - 900) < 30 and nir == 3000


def test_multi_hot():
    y = multi_hot([0, 18])
    assert y.shape == (N_CLASSES,) and y.sum() == 2 and y[0] == y[18] == 1


@pytest.fixture
def split(tmp_path):
    rows = [row(900 + i, 800, 500, 3000 + i, [i % N_CLASSES]) for i in range(6)]
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "s.parquet")
    return Split(tmp_path / "s.parquet")


def test_split_and_stats(split):
    assert len(split) == 6 and split.labels.shape == (6, N_CLASSES)
    mean, std = band_stats(split, n=6)
    assert len(mean) == 4 and 2900 < mean[3] < 3010


def test_torch_dataset_normalises_and_augments(split):
    ds = torch_dataset(split, [0, 0, 0, 3000], [1, 1, 1, 1000], augment=True)
    x, y = ds[0]
    assert x.shape == (4, 8, 8) and y.shape == (N_CLASSES,)
    assert torch.allclose(x[3], torch.zeros(8, 8))  # nir (3000 - 3000) / 1000


# --- metrics ----------------------------------------------------------------------------

def test_average_precision():
    assert average_precision([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2]) == 1.0
    assert average_precision([1, 0, 0, 1], [0.1, 0.9, 0.8, 0.2]) == pytest.approx((1 / 3 + 2 / 4) / 2)
    assert average_precision([0, 0], [0.3, 0.1]) is None


def test_evaluate_micro_macro_f1():
    names = ["a", "b", "c"]
    y = np.array([[1, 0, 0], [0, 1, 0], [1, 1, 0]])
    p = np.array([[0.9, 0.2, 0.1], [0.3, 0.8, 0.2], [0.7, 0.6, 0.3]])
    m = evaluate(y, p, names)
    assert m["per_class_ap"] == {"a": 1.0, "b": 1.0, "c": None}   # no positives for c
    assert m["macro_map"] == 1.0 and m["macro_f1"] == 1.0 and m["micro_map"] == 1.0


# --- subset selection -----------------------------------------------------------------------

def test_select_caps_dominant_country():
    groups = [{"country": "Big", "rows": 100, "file": f"f{i}", "row_group": i} for i in range(60)] + \
             [{"country": c, "rows": 100, "file": f"{c}{i}", "row_group": i} for c in "ABC" for i in range(20)]
    picked = select(groups, 2000, 0.25, random.Random(0))
    rows = {}
    for g in picked:
        rows[g["country"]] = rows.get(g["country"], 0) + g["rows"]
    assert rows["Big"] <= 500 and sum(rows.values()) >= 1900


def test_config_paths():
    cfg = common.load_config()
    assert cfg["checkpoint"].name == "resnet18_4band_ben.pt" and cfg["checkpoint"].is_absolute()
    assert cfg["dataset"]["columns"] == ["image", "nir", "labels", "image_id", "country"]  # no SWIR


# --- WorldCover evaluation helpers ---------------------------------------------------------

def test_model_veto_and_scoring():
    from eval_worldcover import BUILT, OTHER, score, with_model

    rules = np.array([[BUILT, BUILT], [OTHER, BUILT]], dtype="uint8")
    scores = np.array([[0.9, 0.1], [0.9, 0.6]])
    out = with_model(rules, scores, 0.5)
    assert out.tolist() == [[BUILT, OTHER], [OTHER, BUILT]]
    ref = np.array([[BUILT, OTHER], [OTHER, BUILT]], dtype="uint8")
    assert score(out, ref)["built_f1"] == 1.0
    assert score(rules, ref)["built_precision"] == pytest.approx(2 / 3, abs=1e-4)
