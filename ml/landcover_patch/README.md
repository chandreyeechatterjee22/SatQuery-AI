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

## Results (2026-09-26, i3-1115G4 CPU, 2 threads)

**Subset:** 15,501 train / 3,392 validation / 5,378 test patches, country-balanced with Finland
capped at 25%, from the official splits. The download was 1.06 GB (RGB + NIR + labels only).
Training took 82.7 min: 5 min for probe features, then 6 fine-tune epochs of about 12 min each.
Validation micro mAP was still rising at epoch 6 (0.808 -> 0.820), so the Colab run with more
data and epochs should do better.

**Before vs after on the held-out BigEarthNet test subset** (`eval.py`, 5,378 patches; macro over
the 18 classes that have test positives):

| metric | before (linear probe) | after (fine-tuned) | change |
|---|---|---|---|
| micro mAP | 0.6898 | 0.8059 | +0.1161 |
| macro mAP | 0.5057 | 0.6639 | +0.1582 |
| macro F1 @0.5 | 0.4101 | 0.5977 | +0.1876 |

Per-class AP improved for all 18 classes, for example urban_fabric 0.669 -> 0.827,
industrial_commercial_units 0.205 -> 0.320, inland_waters 0.577 -> 0.808 and
arable_land 0.888 -> 0.931. The full table is in `data/models/landcover_patch/eval_test.json`.

**Bengaluru check against ESA WorldCover 2021** (`eval_worldcover.py`). The criterion was fixed
before running: holdout mean built-up F1 gain of at least 0.03, with no holdout area worse.

| variant | tau (tuned) | Bellandur F1 | Hoskote F1 | holdout mean gain | result |
|---|---|---|---|---|---|
| rules with SWIR (Sentinel-2) | 0.55 | 0.604 -> 0.571 | 0.630 -> 0.627 | -0.019 | **fail** |
| rules without SWIR (Cartosat-like) | 0.40 | 0.667 -> 0.642 | 0.631 -> 0.631 | -0.012 | **fail** |

**Decision: the model is not wired into change analysis.** It stays a reported component.

- **Why it doesn't help as a veto:** it is reasonable at patch level. Its mean P(urban_fabric)
  over Sarjapur was 0.68 (2019), 0.59 (2021) and 0.88 (2025), following the urbanisation that
  the index rules got backwards. But almost every 1.2 km peri-urban patch in Bengaluru contains
  some urban area, so a patch score cannot remove bare-field pixels without also removing real
  built-up (recall drops in Bellandur).
- **The dry-season case is not fixed:** Sarjapur 2019 built-up went only 63.6% -> 59.7%.
- **Two reasons behind it:** BigEarthNet labels mark which classes are present, not how much
  area they cover, and the training data are European while the test areas are in India
  (domain shift).
- **6-band variant:** a 6-band (with SWIR) comparison was not run; it would cost ~0.23 GB of
  extra data and another ~1.3 h of training.
