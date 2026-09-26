# SatQuery AI Prototype

A functional prototype for analyzing satellite imagery using Google Earth Engine, FastAPI, and React.

## How the system works

**User**
↓
**React Frontend**
↓
**FastAPI Backend**
↓
**Google Earth Engine**
↓
**Sentinel-2**
↓
**Spectral Analysis**
↓
**NDVI / NDWI / Flood Detection**
↓
**Visualization Layer**
↓
**Results returned to Frontend**

## Prerequisites
- Python 3.9+
- Node.js 18+
- Google Earth Engine Account / Service Account

## Backend Setup (Windows PowerShell)

1. Create a virtual environment and install dependencies:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Configure environment variables:
```powershell
Copy-Item .env.example .env
```
| Variable | Default | Purpose |
|---|---|---|
| `GEE_PROJECT_ID` | `satquery-ai-508105` | Earth Engine cloud project |
| `GEE_SERVICE_ACCOUNT` | *(empty)* | Optional service-account email |
| `GEE_PRIVATE_KEY` | *(empty)* | Path to the service-account JSON key |
| `UPLOAD_DIR` | `<repo>/data/uploads` | Where accepted uploads are stored |
| `MAX_UPLOAD_MB` | `500` | Per-file upload size limit |
| `MODEL_CACHE_DIR` | `<repo>/data/models` | Model weights (git-ignored) |
| `REMOTECLIP_CHECKPOINT` | `<cache>/remoteclip/RemoteCLIP-ViT-B-32.pt` | RemoteCLIP weights |
| `VQA_HEAD_PATH` | `<cache>/vqa_head/rsvqa_lr_head.pt` | Trained VQA head |
| `LANDCOVER_PATCH_PATH` | `<cache>/landcover_patch/resnet18_4band_ben.pt` | BigEarthNet-fine-tuned 4-band land-cover classifier |

3. Authenticate with Earth Engine. For local development, run:
```powershell
earthengine authenticate
```
On a server, set `GEE_SERVICE_ACCOUNT` and `GEE_PRIVATE_KEY` instead.

4. Start the FastAPI server:
```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Running the tests

```powershell
cd backend
pip install -r requirements-dev.txt
pytest
```
The pytest suite needs no network or Earth Engine credentials.

`backend/test_backend.py` is a manual smoke script, not part of pytest: it needs a running server on port 8000 plus valid GEE credentials (`python test_backend.py`).

## Upload API (upload-based flow)

`POST /api/uploads` (multipart form):

| Field | Notes |
|---|---|
| `mode` | `single` (1 file), `optical_sar` (file_1 optical, file_2 SAR), `bi_temporal` (2 files) |
| `file_1`, `file_2` | GeoTIFF (`.tif`/`.tiff`); PNG/JPEG only with `benchmark_mode=true` |
| `date_1`, `date_2` | `YYYY-MM-DD`; required and different for `bi_temporal` |
| `sensor_1`, `sensor_2` | Optional: `auto` (default), `sentinel2`, `cartosat2s`, `bgrn`, `rgb`, `sar` |
| `band_roles_1`, `band_roles_2` | Optional explicit role per band, e.g. `blue,green,red,nir,swir1` or `vv,vh` (`-` ignores a band). Use this for Earth Engine exports, which drop band names. |
| `benchmark_mode` | `true` to allow PNG/JPEG |

Returns `201` with the upload id, per-file metadata (bands, dtype, CRS, bounds, resolution), band roles, pair checks and warnings; `422` with every rejection reason (`{code, message, file}`); or `413` if a file is too large. `GET /api/uploads/{upload_id}` returns the stored manifest.

```powershell
curl.exe -X POST http://localhost:8000/api/uploads -F mode=optical_sar -F file_1=@optical.tif -F file_2=@sar.tif
```

## Query API (agent controller)

`POST /api/query` with JSON `{"upload_id": "...", "question": "...", "params": {...}}` (`params` optional, validated against the tool's allow-list).

Pipeline: classify the question (rules, then a typo-tolerant keyword fallback) -> check the task fits the upload mode -> pick the tool from the registry -> validate params -> run.

| Task | Modes | Tool | Status |
|---|---|---|---|
| metadata (bands, CRS, resolution, size, extent, dates) | all | `image_metadata` | available |
| caption | single | `rs_caption` | RemoteCLIP zero-shot scene labels (needs the ML install) |
| vqa | single | `rs_vqa` | trained RSVQA-LR head if present, else zero-shot RemoteCLIP (presence, rural/urban) |
| water / built-up | optical_sar | `optical_sar_mapper` | available (numpy/rasterio, no model) |
| change | bi_temporal | `landcover_change` | available (numpy/rasterio, no model) |

The response has `status` (`OK`, `NOT_AVAILABLE`, `REJECTED`, `ERROR`), `answer`, `confidence` (task-classification confidence x tool confidence), `evidence_images` (URLs relative to the API host) and `trace` (task, tool + version, params, inputs, duration, status and per-step timings). `GET /api/tools` lists the registered tools.

```powershell
$body = @{ upload_id = "<id from /api/uploads>"; question = "How many bands does this image have?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/query -ContentType "application/json" -Body $body
```

## Optical + SAR water / built-up

`optical_sar_mapper` warps the SAR image onto the optical grid (downsampled to at most `max_size` px) and uses only pixels valid in both.

| Class | Optical signal | SAR signal (VV, else HH; linear converted to dB) |
|---|---|---|
| water | MNDWI (green, SWIR1), or NDWI (green, NIR) without SWIR, `> optical_water_threshold` (0) | `< sar_water_db` (-18 dB) |
| built-up | NDBI (SWIR1, NIR) `> optical_builtup_threshold` (0), or a labelled low-NDVI proxy (`< 0.2`) without SWIR | `> sar_builtup_db` (-6 dB) |

- **Fusion:** `and` (default) means both modalities must agree; `or` accepts either one. Built-up never overlaps the final water mask.
- **Output per class:** area % and km² (when the CRS allows it), the % flagged by optical only, SAR only and both, and an RGBA overlay coloured by those three groups.
- **Confidence:** modality agreement, i.e. pixels both modalities flag ÷ pixels either flags. It is a consensus measure, not a calibrated probability, and it is `null` if one modality lacks the needed bands.
- **Uncalibrated SAR:** values that don't look like calibrated sigma0 in dB are flagged in `warnings`.

All thresholds are validated parameters (see `GET /api/tools`).

## Bi-temporal land-cover change

`landcover_change` sorts the two files by date (earlier = before), puts both on the earlier grid and compares only pixels valid on both dates. It uses only the bands present on both dates.

| Class | Rule (in order) |
|---|---|
| water | MNDWI (green, SWIR1), or NDWI (green, NIR) without SWIR, `> water_threshold` (0) |
| vegetation | NDVI `> vegetation_ndvi` (0.3) |
| built-up | NDBI `> builtup_threshold` (0), or NDVI `< ndvi_max_builtup` (0.2) without SWIR (flagged in the answer) |
| other | everything else |

- **Per class:** % and km² on each date, the delta in percentage points and km², the relative change, and the largest from→to transitions. Evidence is one land-cover map per date; there is no change map.
- **Direction:** "increased" / "decreased" / "remained essentially unchanged" comes from the same rounded numbers that are printed. A change smaller than `unchanged_tolerance_pp` (1 pp) counts as unchanged. `details.short_answer` gives the canonical word when one class is asked about.
- **Confidence:** threshold robustness (the share of 27 runs with each index threshold shifted ±0.05 that reach the same conclusion) × a season factor. It is not a probability.
- **Season check:** index rules count dry bare fields as built-up. If the 90th-percentile NDVI differs by 0.05 or more between the dates, the answer warns, and confidence for built-up, vegetation and other is multiplied by `max(0, 1 - gap/0.15)`.

**Real-data check (Bengaluru, Sentinel-2 January–March composites):**
- **Against ESA WorldCover 2021** (four areas, 2021 composites): built-up F1 0.58–0.62 and overall accuracy 0.70–0.74.
- **Sarjapur Road, 2021 → 2025** (similar seasons): built-up 31.9% → 43.1%, "increased", confidence 1.0.
- **Sarjapur Road, 2019 → 2025:** 2019 was much drier (p90 NDVI 0.45 vs 0.58). The rules report built-up "decreased" (63.6% → 43.1%) and flag it with confidence 0.12 and the season warning. **Use images from the same season.**

## Local models (captioning and VQA)

Optional. Without these steps, captioning and VQA return `NOT_AVAILABLE` and everything else works.

```powershell
cd backend
pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-ml.txt
python scripts\download_remoteclip.py        # RemoteCLIP ViT-B/32, Apache-2.0, ~605 MB
python scripts\benchmark_remoteclip.py       # speed and RAM on this machine
```

To train the RSVQA-LR VQA head, see [ml/vqa_head/README.md](ml/vqa_head/README.md).

## Fine-tuned component: 4-band land-cover classifier (BigEarthNet)

[ml/landcover_patch](ml/landcover_patch/README.md) fine-tunes a B/G/R/NIR ResNet-18 (so it can run on Cartosat-2S too) on a BigEarthNet v2 subset. Training and evaluation dependencies are in `ml/requirements.txt`.

- **Before vs after on held-out BigEarthNet test** (linear probe -> full fine-tune): micro mAP 0.690 -> 0.806, macro mAP 0.506 -> 0.664, macro F1 0.410 -> 0.598.
- **Not wired into change analysis:** a check fixed in advance against ESA WorldCover 2021 on four Bengaluru areas showed no gain for built-up (holdout F1 -0.019). The model therefore stays a reported component; details and the domain-shift caveat are in its README.

## Frontend Setup

1. Install dependencies and configure the API URL:
```powershell
cd frontend
npm install
Copy-Item .env.example .env   # sets VITE_API_BASE_URL (default http://localhost:8000/api)
```

2. Start the React development server:
```powershell
npm run dev
```

The app will be available at `http://localhost:5173`. Make sure the backend is running at the URL in `VITE_API_BASE_URL`.

The header has two tabs:
- **Map Analysis:** the original Earth Engine flow, unchanged.
- **Upload Analysis:** the upload-based agent flow.
  - Pick a mode, upload files; validation results and rejection reasons appear inline.
  - Ask a question or click an example chip.
  - See the answer with a confidence bar and what the confidence means, the preview images with toggleable overlays, legends and an opacity slider, and the execution trace timeline.
  - Download a JSON or self-contained HTML report (evidence images are embedded).
  - Tools the server cannot run are shown as `NOT_AVAILABLE`.

Frontend unit tests (Node's built-in test runner, no extra packages): `npm test`

If another service already uses port 8000, run the backend on another port and set `VITE_API_BASE_URL` accordingly, e.g. `$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"; npm run dev`.

## Features
- **Real GEE Integration:** Performs calculations strictly within user-drawn AOIs.
- **Sentinel-2 Harmonized:** Uses the latest available cloud-free composites via Cloud Score+.
- **Landcover Validation:** Validates AOI context using ESA WorldCover.
- **Three Core Queries:** Vegetation (NDVI), Water (NDWI), and Potential Flood Detection.
