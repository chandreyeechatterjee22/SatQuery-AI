# 4-band land-cover classifier fine-tuned on BigEarthNet v2

A ResNet-18 that takes **B, G, R, NIR** (reflectance x 10000 at 10 m), so it can also run on
Cartosat-2S MX, which has no SWIR. It predicts the 19 BigEarthNet (CORINE 2018) classes as
multi-label probabilities for 120 x 120 px (1.2 km) patches.

- **Network and input handling:** shared with the API through `backend/models/landcover_patch.py`.
  The first conv layer is initialised from ImageNet RGB weights in B/G/R order; NIR copies the red
  filter, and all are scaled by 3/4.
- **Resampling:** every input is resampled to 10 m before classification (Cartosat ~2 m gets
  averaged down, 20 m gets upsampled).
- **What the labels mean:** they say which classes are present in a patch, not how much area
  they cover.

| File | Purpose |
|---|---|
| `download_bigearthnet_subset.py` | Country-balanced sample of whole 100-patch row groups from each official split. Only RGB, NIR, labels, id and country are fetched (`--dry-run` shows the size first). |
| `config.yaml` | Subset sizes, seed, training settings, output paths |
| `train.py` | **Before:** frozen ImageNet backbone + linear head (linear probe). **After:** full fine-tune starting from the probe head. Validation picks the best epoch. |
| `eval.py` | Before vs after on the held-out **test** subset: micro/macro mAP, macro F1 @ 0.5, per-class AP |
| `download_worldcover_aois.py`, `eval_worldcover.py` | Bengaluru check against ESA WorldCover 2021: rules only vs rules + model (needs Earth Engine) |
| `colab_train_bigearthnet.ipynb` | The same scripts on a larger subset with a GPU |

Everything is written under the git-ignored `data/` folder.

## Data

[timm/bigearthnet-v2-rgb-nir-swir](https://huggingface.co/datasets/timm/bigearthnet-v2-rgb-nir-swir)
(CDLA-Permissive-1.0) is a mirror of reBEN, with the official geographic train / validation / test
splits and cloud/snow patches removed.
- **RGB:** stored tone-mapped to 8 bit. `data.py` inverts the documented curve back to reflectance.
- **NIR:** stored as raw 16-bit L2A values.

## Run (PowerShell, from the repo root)

```powershell
.\.venv\Scripts\python.exe ml\landcover_patch\download_bigearthnet_subset.py --dry-run
.\.venv\Scripts\python.exe ml\landcover_patch\download_bigearthnet_subset.py
.\.venv\Scripts\python.exe ml\landcover_patch\train.py
.\.venv\Scripts\python.exe ml\landcover_patch\eval.py
.\.venv\Scripts\python.exe ml\landcover_patch\download_worldcover_aois.py
.\.venv\Scripts\python.exe ml\landcover_patch\eval_worldcover.py
```

Tests (synthetic data, no downloads): `cd ml\landcover_patch; ..\..\.venv\Scripts\python.exe -m pytest`
