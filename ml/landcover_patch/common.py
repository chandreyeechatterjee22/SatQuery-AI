"""Shared setup for ml/landcover_patch scripts: repo paths, backend imports, config."""
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("config.yaml")

# The network, band handling and preprocessing live in backend/models/landcover_patch.py
# so training and serving share one implementation.
_BACKEND = str(REPO_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _resolve(p):
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def load_config(path=None):
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["dataset"]["subset_dir"] = _resolve(cfg["dataset"]["subset_dir"])
    cfg["output_dir"] = _resolve(cfg["output_dir"])
    cfg["checkpoint"] = _resolve(cfg["checkpoint"])
    return cfg
