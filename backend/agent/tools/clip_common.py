"""Shared helpers for tools that use the RemoteCLIP encoder."""
import numpy as np

from agent.registry import ToolNotAvailable
from models import remoteclip
from models.image_input import load_model_image
from models.zero_shot import ZeroShot

_zero_shot = {}


def encoder_or_unavailable():
    try:
        return remoteclip.get_encoder()
    except remoteclip.ModelNotAvailable as exc:
        raise ToolNotAvailable(str(exc)) from exc


def zero_shot_for(encoder):
    key = id(encoder)
    if key not in _zero_shot:
        _zero_shot[key] = ZeroShot(encoder)
    return _zero_shot[key]


def image_embedding(ctx, encoder, slot=1):
    """Embed an uploaded file once and cache the vector next to the upload."""
    cache = ctx.folder / "embeddings" / f"file_{slot}_{encoder.model_id}.npy"
    if cache.is_file():
        return np.load(cache)
    image, _ = load_model_image(ctx.path(slot), ctx.file(slot)["bands"])
    embedding = encoder.encode_images([image])[0]
    cache.parent.mkdir(exist_ok=True)
    np.save(cache, embedding)
    return embedding


def preview_evidence(ctx, slot=1):
    ctx.preview_path(slot)
    f = ctx.file(slot)
    return {"id": f"preview_{slot}", "kind": "preview",
            "label": f"File {slot} preview ({f['filename']})", "url": ctx.preview_url(slot)}
