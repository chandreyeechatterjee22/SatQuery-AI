"""RemoteCLIP ViT-B/32 (Apache-2.0) image/text encoder, loaded lazily on CPU.

torch and open_clip are optional dependencies (requirements-ml.txt). If they
or the checkpoint are missing, ``availability()`` says why and tools report
NOT_AVAILABLE instead of failing.
"""
import importlib.util
import threading

import numpy as np

import settings

ARCH = "ViT-B-32"
MODEL_ID = "RemoteCLIP-ViT-B-32"


class ModelNotAvailable(RuntimeError):
    """The model cannot be used (missing dependency, weights, or failed load)."""


_lock = threading.Lock()
_encoder = None
_load_error = None


def availability():
    """Cheap check (no loading): return (available, reason_if_not)."""
    for module in ("torch", "open_clip"):
        if importlib.util.find_spec(module) is None:
            return False, (f"Python package '{module}' is not installed "
                           "(pip install -r requirements-ml.txt).")
    checkpoint = settings.remoteclip_checkpoint()
    if not checkpoint.is_file():
        return False, (f"RemoteCLIP weights not found at {checkpoint} "
                       "(run scripts/download_remoteclip.py).")
    if _load_error:
        return False, f"RemoteCLIP failed to load: {_load_error}"
    return True, None


def get_encoder():
    """Return the shared ClipEncoder, loading it on first use."""
    global _encoder, _load_error
    if _encoder is not None:
        return _encoder
    with _lock:
        if _encoder is None:
            ok, reason = availability()
            if not ok:
                raise ModelNotAvailable(reason)
            try:
                _encoder = ClipEncoder(settings.remoteclip_checkpoint())
            except Exception as exc:  # corrupt weights, version mismatch, OOM...
                _load_error = f"{type(exc).__name__}: {exc}"
                raise ModelNotAvailable(f"RemoteCLIP failed to load: {_load_error}") from exc
    return _encoder


class ClipEncoder:
    """Wraps an open_clip model; returns L2-normalised float32 numpy embeddings."""
    model_id = MODEL_ID

    def __init__(self, checkpoint, arch=ARCH):
        import open_clip
        import torch

        self._torch = torch
        model, _, preprocess = open_clip.create_model_and_transforms(arch)
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        model.eval()
        self.model = model
        self.preprocess = preprocess
        self.tokenizer = open_clip.get_tokenizer(arch)
        self.logit_scale = float(model.logit_scale.exp().item())
        self.dim = int(model.text_projection.shape[1])

    def encode_images(self, images, batch_size=32):
        """``images``: list of PIL RGB images."""
        out = []
        with self._torch.inference_mode():
            for i in range(0, len(images), batch_size):
                batch = self._torch.stack([self.preprocess(im) for im in images[i:i + batch_size]])
                out.append(self._normalise(self.model.encode_image(batch)))
        return np.concatenate(out) if out else np.zeros((0, self.dim), dtype="float32")

    def encode_texts(self, texts, batch_size=256):
        out = []
        with self._torch.inference_mode():
            for i in range(0, len(texts), batch_size):
                tokens = self.tokenizer(list(texts[i:i + batch_size]))
                out.append(self._normalise(self.model.encode_text(tokens)))
        return np.concatenate(out) if out else np.zeros((0, self.dim), dtype="float32")

    def _normalise(self, features):
        features = features / features.norm(dim=-1, keepdim=True)
        return features.float().cpu().numpy()


def softmax_scores(encoder, image_embedding, text_embeddings):
    """CLIP-style probabilities of one image over several texts."""
    logits = encoder.logit_scale * (text_embeddings @ image_embedding)
    logits = logits - logits.max()
    exp = np.exp(logits)
    return exp / exp.sum()


def _reset_for_tests():
    global _encoder, _load_error
    _encoder, _load_error = None, None
