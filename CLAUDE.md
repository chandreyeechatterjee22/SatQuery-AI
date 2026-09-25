# SatQuery AI — working rules for Claude

## Project
- FastAPI backend in `/backend`, React + Vite + Tailwind frontend in `/frontend`, ML code in `/ml`.
- The existing Earth Engine flow (Sentinel-2 NDVI/NDWI/flood on a map-drawn AOI: `/api/sentinel`, `/api/analyze`, `gee_service.py`, `analysis/`, `intent.py`, map UI) **stays as-is. Do not delete or change it.**
- We are adding a new **upload-based agentic flow** alongside it: the user uploads satellite image(s) and asks a natural-language question. The backend picks a tool, runs it, and returns answer + confidence + evidence images + execution trace.

## Scope: build only these 6 things
1. **Upload + validation**: `POST /api/uploads` takes 1–2 GeoTIFF/TIFF files (PNG/JPEG only when `benchmark_mode=true`). Modes: `single`, `optical_sar`, `bi_temporal`. Read metadata with rasterio (bands, dtype, CRS, bounds, resolution). Check the file count matches the mode, the pair has the same CRS and overlapping bounds, and bi_temporal has two different user-entered dates. Give clear rejection reasons. Handle any band count (Sentinel-2, Cartosat-2S 4-band, SAR 1–2 band). Sentinel band names only inside a small band adapter.
2. **Agent controller + trace**: `POST /api/query {upload_id, question}`. Classify the task (rules first, simple fallback) → check the task fits the upload mode → pick a tool from the registry → validate params against that tool's allow-list → run → return `{answer, confidence, evidence_images, trace}`. The trace has task, tool name + version, params, inputs, duration and status. **Never output chain-of-thought.**
3. **Single-image VQA + captioning**: small open RS-capable VLM or CLIP-style model that runs locally. Propose 2–3 candidates (size, VRAM, licence) and **wait for the user's choice**.
4. **Optical + SAR**: water (low SAR backscatter + optical water index) and built-up (high SAR backscatter + optical features). Per-class PNG mask overlays, area %, and which modality detected what.
5. **Change analysis (bi_temporal)**: land cover per date (water / built-up / vegetation / other) → compare → answer "What changed?" and "Has built-up increased/decreased/unchanged?" with per-class area deltas. **The answer text must match the numbers.**
6. **One fine-tuned component** in `/ml`: download script, config, train script, eval script, on a BigEarthNet subset. Report before-vs-after accuracy.

**Frontend:** a new "Upload Analysis" tab next to the map UI with: mode picker, file upload + validation result, question box + example chips, image viewer with overlay toggle, answer + confidence card, trace timeline, "Download report" (JSON + HTML). **No `alert()`. Show errors inline.**

**Skip:** grounding, change maps, PDF reports, benchmark harness, Docker, and any change to the Earth Engine features.

## Hard rules
- **Honesty:** never fake model outputs or metrics. If a model isn't loaded, return status `NOT_AVAILABLE` and show that in the UI.
- **Config:** everything comes from env. Keep `backend/.env.example` and `frontend/.env.example` (`VITE_API_BASE_URL`). No hard-coded keys or URLs.
  - GEE project id comes from env `GEE_PROJECT_ID`, default `satquery-ai-508105`.
  - Frontend API URL comes from `VITE_API_BASE_URL`, default `http://localhost:8000/api`.
  - These defaults exist so **the old map flow works exactly as before** with no `.env` present.
- **Hygiene:** root `.gitignore` covers Python, Node, `.venv`, `.env`, `data/`, weights, outputs. No `__pycache__` in git.
- **Never commit** datasets, model weights, `.env`, outputs or `data/`.
- **Tests:** pytest for every backend module, using small synthetic GeoTIFFs generated inside the tests. **Run the tests before every commit.**
- **Environment:** the user is on Windows. Give PowerShell commands.

## Git workflow
- Base branch: `develop` (exists locally and on origin). **Never commit to `main`.**
- Tag `original-prototype` marks the old version. **Never move or delete it.**
- One branch per step, each cut from the **latest** `develop`, in this order:
  `chore/hygiene`, `feature/upload-validation`, `feature/agent-controller`, `feature/vqa-caption`, `feature/optical-sar`, `feature/change-analysis`, `feature/finetune-bigearthnet`, `feature/frontend-upload-flow`.
- Conventional commits, small and focused, e.g. `feat(upload): validate optical_sar pair CRS`.
- At the end of each branch: run the tests, give the user a summary + how to test it, then **STOP and wait for their OK before merging into `develop`**.
- **Never push without asking.**
