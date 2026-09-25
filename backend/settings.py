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


def max_upload_bytes():
    """Per-file size limit (env MAX_UPLOAD_MB)."""
    raw = os.getenv("MAX_UPLOAD_MB")
    try:
        mb = float(raw) if raw else DEFAULT_MAX_UPLOAD_MB
    except ValueError:
        mb = DEFAULT_MAX_UPLOAD_MB
    return int(mb * 1024 * 1024)
