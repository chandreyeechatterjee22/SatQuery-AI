"""Download the RemoteCLIP ViT-B/32 checkpoint (Apache-2.0) into the model cache.

Usage (PowerShell, from backend/):
    ..\\.venv\\Scripts\\python.exe scripts\\download_remoteclip.py

The target is settings.remoteclip_checkpoint() (env REMOTECLIP_CHECKPOINT or
MODEL_CACHE_DIR), which is git-ignored.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import settings  # noqa: E402

REPO_ID = "chendelong/RemoteCLIP"
FILENAME = "RemoteCLIP-ViT-B-32.pt"


def main():
    from huggingface_hub import hf_hub_download

    target = settings.remoteclip_checkpoint()
    if target.is_file():
        print(f"already present: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    downloaded = Path(hf_hub_download(REPO_ID, FILENAME, local_dir=target.parent))
    if downloaded != target:
        downloaded.replace(target)
    print(f"saved {target} ({target.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
