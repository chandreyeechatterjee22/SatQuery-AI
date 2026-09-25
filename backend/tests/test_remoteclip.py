import numpy as np
import pytest

import settings
from models import remoteclip


def test_missing_checkpoint_is_not_available(tmp_path, monkeypatch):
    monkeypatch.setenv("REMOTECLIP_CHECKPOINT", str(tmp_path / "nope.pt"))
    ok, reason = remoteclip.availability()
    assert not ok and "download_remoteclip.py" in reason
    with pytest.raises(remoteclip.ModelNotAvailable, match="weights not found"):
        remoteclip.get_encoder()


def test_missing_package_is_not_available(monkeypatch):
    monkeypatch.setattr(remoteclip.importlib.util, "find_spec",
                        lambda name: None if name == "open_clip" else object())
    ok, reason = remoteclip.availability()
    assert not ok and "'open_clip' is not installed" in reason


def test_corrupt_checkpoint_reports_load_error(tmp_path, monkeypatch):
    pytest.importorskip("open_clip")
    bad = tmp_path / "bad.pt"
    bad.write_bytes(b"not a checkpoint")
    monkeypatch.setenv("REMOTECLIP_CHECKPOINT", str(bad))
    with pytest.raises(remoteclip.ModelNotAvailable, match="failed to load"):
        remoteclip.get_encoder()
    ok, reason = remoteclip.availability()
    assert not ok and "failed to load" in reason


def test_model_paths_follow_cache_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("REMOTECLIP_CHECKPOINT")
    monkeypatch.delenv("VQA_HEAD_PATH")
    monkeypatch.setenv("MODEL_CACHE_DIR", str(tmp_path))
    assert settings.remoteclip_checkpoint() == tmp_path / "remoteclip" / "RemoteCLIP-ViT-B-32.pt"
    assert settings.vqa_head_path() == tmp_path / "vqa_head" / "rsvqa_lr_head.pt"


REAL_CHECKPOINT = settings.REPO_ROOT / "data" / "models" / "remoteclip" / "RemoteCLIP-ViT-B-32.pt"


@pytest.mark.skipif(not REAL_CHECKPOINT.is_file(), reason="real RemoteCLIP weights not downloaded")
def test_real_encoder_embeddings(monkeypatch):
    """Integration check with the real weights (skipped on machines without them)."""
    from PIL import Image

    monkeypatch.setenv("REMOTECLIP_CHECKPOINT", str(REAL_CHECKPOINT))
    enc = remoteclip.get_encoder()
    img = enc.encode_images([Image.new("RGB", (64, 64), (30, 90, 30))])
    txt = enc.encode_texts(["a satellite image of a forest.", "a satellite image of a desert."])
    assert img.shape == (1, 512) and txt.shape == (2, 512)
    assert np.allclose(np.linalg.norm(img, axis=1), 1.0, atol=1e-4)
    assert 1.0 < enc.logit_scale <= 100.0
    assert remoteclip.get_encoder() is enc
