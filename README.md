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
| water / built-up | optical_sar | `optical_sar_mapper` | `NOT_AVAILABLE` (not built yet) |
| change | bi_temporal | `landcover_change` | `NOT_AVAILABLE` (not built yet) |

The response has `status` (`OK`, `NOT_AVAILABLE`, `REJECTED`, `ERROR`), `answer`, `confidence` (task-classification confidence x tool confidence), `evidence_images` (URLs relative to the API host) and `trace` (task, tool + version, params, inputs, duration, status and per-step timings). `GET /api/tools` lists the registered tools.

```powershell
$body = @{ upload_id = "<id from /api/uploads>"; question = "How many bands does this image have?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/query -ContentType "application/json" -Body $body
```

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

## Features
- **Real GEE Integration:** Performs calculations strictly within user-drawn AOIs.
- **Sentinel-2 Harmonized:** Uses the latest available cloud-free composites via Cloud Score+.
- **Landcover Validation:** Validates AOI context using ESA WorldCover.
- **Three Core Queries:** Vegetation (NDVI), Water (NDWI), and Potential Flood Detection.
