"""Deterministic stand-ins for the CLIP encoder (no torch, no weights)."""
import hashlib

import numpy as np

DIM = 8


def unit(seed_text, dim=DIM):
    rng = np.random.default_rng(int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16))
    v = rng.normal(size=dim)
    return (v / np.linalg.norm(v)).astype("float32")


class FakeEncoder:
    """Text embeddings are fixed per string; ``image_vector`` is what every image embeds to."""
    model_id = "fake-clip"
    logit_scale = 100.0
    dim = DIM

    def __init__(self, image_vector=None, texts=None):
        self.image_vector = unit("image") if image_vector is None else image_vector
        self.texts = texts or {}
        self.text_calls = 0
        self.image_calls = 0

    def encode_images(self, images):
        self.image_calls += 1
        return np.stack([self.image_vector for _ in images])

    def encode_texts(self, texts):
        self.text_calls += 1
        return np.stack([self.texts.get(t, unit(t)) for t in texts])
