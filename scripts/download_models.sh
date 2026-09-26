#!/usr/bin/env bash
# Download the SatQuery AI model files into data/models/ and verify their SHA256 checksums.
# Run once after cloning:  bash scripts/download_models.sh [--skip-remoteclip]
#
#   rsvqa_lr_head.pt       -> data/models/vqa_head/        (GitHub release asset)
#   resnet18_4band_ben.pt  -> data/models/landcover_patch/ (GitHub release asset)
#   RemoteCLIP-ViT-B-32.pt -> data/models/remoteclip/      (Hugging Face, via backend/scripts/download_remoteclip.py)
#
# Override the release location with SATQUERY_MODELS_URL. Checksums: scripts/models.sha256.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_URL="${SATQUERY_MODELS_URL:-https://github.com/chandreyeechatterjee22/SatQuery-AI/releases/download/v1.0-prototype}"
SKIP_CLIP="${1:-}"
cd "$ROOT"

sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
expected() { grep "  $1\$" scripts/models.sha256 | cut -d' ' -f1; }
valid() { [ -f "$1" ] && [ "$(sha "$1")" = "$(expected "$1")" ]; }

failed=0
for pair in "rsvqa_lr_head.pt:data/models/vqa_head/rsvqa_lr_head.pt" \
            "resnet18_4band_ben.pt:data/models/landcover_patch/resnet18_4band_ben.pt"; do
  name="${pair%%:*}"; rel="${pair#*:}"
  if valid "$rel"; then echo "ok (already present)  $rel"; continue; fi
  mkdir -p "$(dirname "$rel")"
  echo "downloading  $BASE_URL/$name"
  if curl -fL --retry 3 -o "$rel.part" "$BASE_URL/$name"; then mv "$rel.part" "$rel"; else
    rm -f "$rel.part"; echo "WARNING: download failed: $BASE_URL/$name" >&2; failed=1; continue; fi
  if valid "$rel"; then echo "ok (sha256 verified)  $rel"; else rm -f "$rel"; echo "WARNING: checksum mismatch, deleted: $rel" >&2; failed=1; fi
done

clip="data/models/remoteclip/RemoteCLIP-ViT-B-32.pt"
if [ "$SKIP_CLIP" != "--skip-remoteclip" ]; then
  if valid "$clip"; then echo "ok (already present)  $clip"; else
    py=python; [ -x .venv/bin/python ] && py=.venv/bin/python; [ -x .venv/Scripts/python.exe ] && py=.venv/Scripts/python.exe
    echo "downloading  RemoteCLIP from Hugging Face (~605 MB) with $py"
    "$py" backend/scripts/download_remoteclip.py
    if valid "$clip"; then echo "ok (sha256 verified)  $clip"; else echo "WARNING: RemoteCLIP missing or checksum mismatch" >&2; failed=1; fi
  fi
fi

if [ "$failed" -ne 0 ]; then echo "Some model files are missing or invalid." >&2; exit 1; fi
echo "All model files present and verified."
