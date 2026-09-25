"""Shared setup for ml/vqa_head scripts: repo paths, backend imports, config loading."""
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(__file__).with_name("config.yaml")

# The head's network, question types and image preprocessing live in the backend,
# so training and serving share one implementation.
_BACKEND = str(REPO_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

PATH_KEYS = ("data_dir", "cache_dir", "output")


def load_config(path=None):
    with open(path or CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for key in PATH_KEYS:
        p = Path(cfg[key])
        cfg[key] = p if p.is_absolute() else REPO_ROOT / p
    return cfg
