# SatQuery AI: demo guide

Every expected result below was produced by this code on an Intel i3-1115G4 CPU (2 threads,
7.8 GB RAM, no GPU), with the models trained in this repo. Numbers can differ slightly with other
model files.

## 1. Start (Windows PowerShell)

One-time setup, from the repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
# Optional ML stack. Without it, captioning / VQA / the land-cover model report NOT_AVAILABLE.
pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r backend\requirements-ml.txt
python backend\scripts\download_remoteclip.py          # RemoteCLIP ViT-B/32 weights (~605 MB)
# Trained heads (not in git): ml\vqa_head\train.py and ml\landcover_patch\train.py,
# or copy the .pt files into data\models\vqa_head\ and data\models\landcover_patch\.
cd frontend; npm install; cd ..
```

Run, in two terminals:

```powershell
# terminal 1: backend
cd backend; ..\.venv\Scripts\Activate.ps1
uvicorn main:app --host 127.0.0.1 --port 8000
# terminal 2: frontend
cd frontend
npm run dev          # http://localhost:5173 -> "Upload Analysis" tab
```

- **If port 8000 is taken:** start the backend with `--port 8001` and run
  `$env:VITE_API_BASE_URL="http://127.0.0.1:8001/api"` before `npm run dev`.
- **Check the tools:** `GET /api/tools` shows which tools are available on this machine.

In the UI, open **Advanced** in the upload form to enter band roles (see `samples/README.md`).

## 2. Scenarios (files in `samples/`)

| # | Mode | Files | Question (example chip) | Expected result |
|---|---|---|---|---|
| 1 | Single image | `rsvqa_lr_232.tif` | *Is it a rural or an urban area?* | **`urban`**, confidence ~0.99 (softmax), answered by `trained_head` (RSVQA-LR VQA head). *Describe this image* gives "A satellite image of an airport (43%). Also possible: farmland (19%), a meadow (13%)." |
| 2 | Single image | `bellandur_s2_2024q1.tif`, band roles `blue,green,red,nir,swir1` | *How many bands does this image have?* | "5 band(s), blue=band 1 ... swir1=band 5; resolution 10 x 10 metres", confidence 1.0 (read from file metadata), preview image as evidence |
| 3 | Optical + SAR | `bellandur_s2_2024q1.tif` (roles `blue,green,red,nir,swir1`) + `bellandur_s1_2024q1.tif` (roles `vv,vh`) | *Map water and built-up areas* | **Water 4.22%** (0.6246 km²; optical and SAR agree 67%), **Built-up 14.27%** (2.1105 km²; agreement 21%, because optical NDBI over-flags dry bare soil), confidence 0.44 (mean agreement). Two overlays coloured *optical + SAR agree / optical only / SAR only*, with a toggle and legend. |
| 4 | Two dates | `sarjapur_s2_2021q1.tif` (2021-02-15) + `sarjapur_s2_2025q1.tif` (2025-02-15), roles `blue,green,red,nir,swir1,swir2` | *Has built-up area increased, decreased or remained unchanged?* | **`increased`**, confidence 1.0. The land-cover model gives scene P(urban) 0.68 -> 0.94 and the pixel rules agree (31.87% -> 43.07%, +11.20 percentage points). Land-cover maps for both dates. |
| 5 | Two dates | `sarjapur_s2_2019q1.tif` (2019-02-15) + `sarjapur_s2_2025q1.tif` (2025-02-15), same roles | same question | **`increased`**, but with confidence **0.06**. The model gives P(urban) 0.72 -> 0.94. The answer states the **disagreement** (the pixel rules say "decreased", 63.63% -> 43.07%, because 2019 was a dry year and bare fields look built-up) and warns that the seasons differ (NDVI p90 0.45 vs 0.58). |

**Bonus, inline rejection:** optical + SAR with `sarjapur_s2_2021q1.tif` + `bellandur_s1_2024q1.tif`
gives "Upload rejected: `no_overlap` The two files do not overlap geographically (...)".

What to show in each scenario:
- the answer card: status, answer, confidence and what it means
- the image viewer: overlay on/off, opacity
- the execution trace: task, tool + version, params, inputs, per-step timing; for scenarios 4-5 the
  `landcover_model` entry with model name, version and bands
- **Report (JSON)** and **Report (HTML)** (self-contained, images embedded)

## 3. Same scenarios from the command line

```powershell
cd backend
python -m app.predict --input ..\samples\manifest.json --out ..\predictions.json
```

Expected status counts: `{'OK': 6, 'REJECTED': 1}`. The short answers are `urban`, the caption, the
metadata text, the water/built-up text, `increased`, `increased`, and `no_overlap` for the rejection.

## 4. Tests

```powershell
cd backend; pytest                                   # 376 tests
cd ..\ml\vqa_head; ..\..\.venv\Scripts\python.exe -m pytest
cd ..\landcover_patch; ..\..\.venv\Scripts\python.exe -m pytest
cd ..\..\frontend; npm test
```
