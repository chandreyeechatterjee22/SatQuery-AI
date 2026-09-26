"""Settings for the upload-based flow, read from env at call time (so tests can override)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UPLOAD_DIR = REPO_ROOT / "data" / "uploads"
DEFAULT_MAX_UPLOAD_MB = 500


def upload_dir():
    """Where accepted uploads are stored (env UPLOAD_DIR)."""
    return Path(os.getenv("UPLOAD_DIR") or DEFAULT_UPLOAD_DIR)


def model_cache_dir():
    """Where model weights live (env MODEL_CACHE_DIR, default <repo>/data/models, git-ignored)."""
    return Path(os.getenv("MODEL_CACHE_DIR") or REPO_ROOT / "data" / "models")


def remoteclip_checkpoint():
    """RemoteCLIP ViT-B/32 weights (env REMOTECLIP_CHECKPOINT)."""
    return Path(os.getenv("REMOTECLIP_CHECKPOINT")
                or model_cache_dir() / "remoteclip" / "RemoteCLIP-ViT-B-32.pt")


def vqa_head_path():
    """Trained RSVQA-LR VQA head (env VQA_HEAD_PATH)."""
    return Path(os.getenv("VQA_HEAD_PATH")
                or model_cache_dir() / "vqa_head" / "rsvqa_lr_head.pt")


def landcover_patch_path():
    """BigEarthNet-fine-tuned 4-band land-cover classifier (env LANDCOVER_PATCH_PATH)."""
    return Path(os.getenv("LANDCOVER_PATCH_PATH")
                or model_cache_dir() / "landcover_patch" / "resnet18_4band_ben.pt")


def max_upload_bytes():
    """Per-file size limit (env MAX_UPLOAD_MB)."""
    raw = os.getenv("MAX_UPLOAD_MB")
    try:
        mb = float(raw) if raw else DEFAULT_MAX_UPLOAD_MB
    except ValueError:
        mb = DEFAULT_MAX_UPLOAD_MB
    return int(mb * 1024 * 1024)


DEFAULT_PLAIN_CONFIDENCE_HIGH = 0.75
DEFAULT_PLAIN_CONFIDENCE_MEDIUM = 0.4


def plain_confidence_thresholds():
    """(high, medium) cut-offs that map a numeric confidence to High / Medium / Low
    in plain-language answers (env PLAIN_CONFIDENCE_HIGH, PLAIN_CONFIDENCE_MEDIUM)."""
    def read(name, default):
        try:
            return float(os.getenv(name) or default)
        except ValueError:
            return default
    high = read("PLAIN_CONFIDENCE_HIGH", DEFAULT_PLAIN_CONFIDENCE_HIGH)
    medium = read("PLAIN_CONFIDENCE_MEDIUM", DEFAULT_PLAIN_CONFIDENCE_MEDIUM)
    return (high, medium) if medium <= high else (DEFAULT_PLAIN_CONFIDENCE_HIGH, DEFAULT_PLAIN_CONFIDENCE_MEDIUM)
