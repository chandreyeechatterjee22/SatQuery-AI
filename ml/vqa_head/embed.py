"""Compute (and cache) frozen RemoteCLIP embeddings for one RSVQA-LR split.

Images go through the backend's own upload path (metadata -> band adapter ->
stretched RGB), so the head is trained on exactly what it sees at serve time.
"""
import time

import numpy as np

import common  # noqa: F401  (sets up backend imports)
from data import image_path
from models.image_input import load_model_image
from raster.band_adapter import resolve_bands
from raster.metadata import read_metadata


def split_embeddings(cfg, split, records, encoder):
    """Return (image_index {img_id: row}, image_emb, question_index {text: row}, question_emb)."""
    cache = cfg["cache_dir"] / f"{split}_{encoder.model_id}.npz"
    img_ids = sorted({r["img_id"] for r in records})
    questions = sorted({r["question"] for r in records})

    if cache.is_file():
        data = np.load(cache)
        if data["img_ids"].tolist() == img_ids and data["questions"].tolist() == questions:
            return _index(img_ids), data["img_emb"], _index(questions), data["q_emb"]

    t = time.perf_counter()
    images = []
    for img_id in img_ids:
        path = image_path(cfg["data_dir"], img_id)
        bands = resolve_bands(read_metadata(path))
        images.append(load_model_image(path, bands)[0])
    img_emb = encoder.encode_images(images)
    print(f"[{split}] embedded {len(img_ids)} images in {time.perf_counter() - t:.0f} s")

    t = time.perf_counter()
    q_emb = encoder.encode_texts(questions)
    print(f"[{split}] embedded {len(questions)} unique questions in {time.perf_counter() - t:.0f} s")

    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache, img_ids=np.array(img_ids), img_emb=img_emb,
             questions=np.array(questions), q_emb=q_emb)
    return _index(img_ids), img_emb, _index(questions), q_emb


def features(records, img_index, img_emb, q_index, q_emb):
    """Per-record image and question embedding matrices."""
    img = img_emb[[img_index[r["img_id"]] for r in records]]
    q = q_emb[[q_index[r["question"]] for r in records]]
    return img.astype("float32"), q.astype("float32")


def _index(keys):
    return {k: i for i, k in enumerate(keys)}
