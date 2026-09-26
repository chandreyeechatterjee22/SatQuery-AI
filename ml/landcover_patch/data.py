"""Decode the BigEarthNet subset into 4-band (B, G, R, NIR) reflectance x 10000 patches."""
import io

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

import common  # noqa: F401  (backend imports)
from models.landcover_patch import CLASS_NAMES

N_CLASSES = len(CLASS_NAMES)


def inverse_tone_map(v):
    """8-bit tone-mapped RGB -> approximate L2A reflectance DN (from the dataset card)."""
    scale, white, knee, gamma = 3500., 12000., 0.6, 2.2
    x = (np.asarray(v, dtype=np.float64) / 255) ** gamma
    tw = (white / scale - knee) / (1 - knee)
    s = np.clip((x - knee) / (1 - knee), 0, None)
    a = 1 / tw ** 2
    t = (-(1 - s) + np.sqrt((1 - s) ** 2 + 4 * a * s)) / (2 * a)
    x = np.where(x <= knee, x, knee + (1 - knee) * t)
    return x * scale


def decode(image_bytes, nir_bytes):
    """-> float32 (4, 120, 120) in B, G, R, NIR order, reflectance x 10000."""
    rgb = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))          # R, G, B
    nir = np.asarray(Image.open(io.BytesIO(nir_bytes)), dtype=np.float32)
    refl = inverse_tone_map(rgb).astype(np.float32)
    return np.stack([refl[..., 2], refl[..., 1], refl[..., 0], nir])


def multi_hot(labels):
    y = np.zeros(N_CLASSES, dtype=np.float32)
    y[list(labels)] = 1.0
    return y


class Split:
    """Rows of one split, decoded lazily."""

    def __init__(self, path):
        table = pq.read_table(path, columns=["image", "nir", "labels", "image_id", "country"])
        self.images = [r["bytes"] for r in table.column("image").to_pylist()]
        self.nirs = [r["bytes"] for r in table.column("nir").to_pylist()]
        self.labels = np.stack([multi_hot(l) for l in table.column("labels").to_pylist()])
        self.ids = table.column("image_id").to_pylist()
        self.countries = table.column("country").to_pylist()

    def __len__(self):
        return len(self.ids)

    def x(self, i):
        return decode(self.images[i], self.nirs[i])


def band_stats(split, n=2000, seed=0):
    """Per-band mean / std over a random sample of patches."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(split), size=min(n, len(split)), replace=False)
    px = np.stack([split.x(i) for i in idx]).transpose(1, 0, 2, 3).reshape(4, -1)
    return px.mean(axis=1).tolist(), px.std(axis=1).tolist()


def torch_dataset(split, mean, std, augment=False, seed=0):
    import torch

    mean = np.asarray(mean, dtype=np.float32)[:, None, None]
    std = np.asarray(std, dtype=np.float32)[:, None, None]

    class _DS(torch.utils.data.Dataset):
        def __init__(self):
            self.rng = np.random.default_rng(seed)

        def __len__(self):
            return len(split)

        def __getitem__(self, i):
            x = (split.x(i) - mean) / std
            if augment:
                if self.rng.random() < 0.5:
                    x = x[:, :, ::-1]
                if self.rng.random() < 0.5:
                    x = x[:, ::-1, :]
                x = np.rot90(x, k=int(self.rng.integers(4)), axes=(1, 2))
            return torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(split.labels[i])

    return _DS()
