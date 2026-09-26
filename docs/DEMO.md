# SatQuery AI: demo guide

Every expected result below was produced by this code on an Intel i3-1115G4 CPU (2 threads,
7.8 GB RAM, no GPU), with the models trained in this repo. Numbers can differ slightly with other
model files.

## 1. Start (Windows PowerShell)

One-time setup, from the repo root.

> **Windows path length:** clone into a short path such as `C:\dev\SatQuery-AI`. torch has deeply
> nested files, and if Windows long paths are disabled (the default), `pip install torch` fails
> inside deep folders with `OSError: [Errno 2] No such file or directory ... torch\include\...`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
# Optional ML stack. Without it, captioning / VQA / the land-cover model report NOT_AVAILABLE.
pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r backend\requirements-ml.txt
# Run this once after cloning: downloads the trained heads (GitHub release v1.0-prototype)
# and RemoteCLIP (Hugging Face, ~605 MB) into data\models\ and checks SHA256 checksums.
powershell -ExecutionPolicy Bypass -File scripts\download_models.ps1
cd frontend; npm ci; cd ..
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

The table shows the technical results. In the UI the **plain-language answer** comes first (see below);
the technical answer, raw numbers and trace are under **Technical details** (closed by default).

What to show in each scenario:
- the answer card: large headline, "what it means", key numbers, a coloured confidence badge
  (green High / amber Medium / red Low) with its reason, caveats in a soft warning box, and a clickable
  next question
- the image viewer: overlay on/off, opacity
- **Technical details**: the full technical answer and confidence basis, **Raw numbers**, and the execution
  trace (task, tool + version, params, inputs, per-step timing; for scenarios 4-5 the `landcover_model`
  entry with model name, version and bands)
- **Report (JSON)** and **Report (HTML)** (self-contained, images embedded): plain answer at the top,
  technical details below

### What the plain-language answers say

They are filled in from templates (no language model), using only the tool's own numbers and direction
words. High / Medium / Low comes from the numeric confidence (`PLAIN_CONFIDENCE_HIGH` = 0.75,
`PLAIN_CONFIDENCE_MEDIUM` = 0.4 in `backend/.env`).

| # | Headline | Confidence badge |
|---|---|---|
| 1 | This looks like an urban area (a town or city). | High — the model gave this answer a 99% chance. |
| 1 | *Describe this image*: This looks like an airport. | Medium — the best match got only 43%, so other kinds of place are also possible. |
| 2 | Here are the basic facts about your image. (Layers: 5 (blue, green, red, near-infrared, short-wave infrared light); Each pixel covers: 10 × 10 m on the ground) | High — these facts are read straight from the file. |
| 3 | About 4.2% of the area is water and 14.3% of the area is built-up (buildings and roads). | Medium — the radar and the normal image agree on only 21% of the built-up spots they found. |
| 4 | Yes — the built-up area has increased. | High — the result stays the same when we adjust our detection settings, and both methods agree. |
| 5 | The built-up area probably increased, but our two methods disagree. | Low — the two methods we used don't agree. |

Scenario 4 (Sarjapur, 2021 → 2025) in full:

> **Yes — the built-up area has increased.**
>
> Between 15 Feb 2021 and 15 Feb 2025, more of this area became buildings and roads. About 31.9% of the
> area was built-up before; now it's about 43.1%. Our AI model sees the scene as more city-like on
> 15 Feb 2025 than on 15 Feb 2021 (68 → 94 out of 100).
>
> Key numbers
> - Built-up: 31.87% → 43.07% of the area (4.73 km² → 6.39 km²)
> - How city-like the scene looks to our AI model: 68 → 94 out of 100
> - Area compared: 14.84 km²
>
> **High confidence** — the result stays the same when we adjust our detection settings, and both methods agree.
>
> How we know: We compared the satellite images from both dates and sorted every spot into water, plants,
> buildings and roads, or other land, based on how each surface reflects different colours of light. For
> buildings we also asked an AI model, trained on thousands of labelled satellite images, how city-like
> each image looks.
>
> Next, you could ask: *What changed?*

Scenario 3 (Bellandur optical + SAR) in full:

> **About 4.2% of the area is water and 14.3% of the area is built-up (buildings and roads).**
>
> We looked for water and built-up (buildings and roads) in the 14.79 km² both images cover. Water covers
> 0.62 km² (about 4.2%). Built-up covers 2.11 km² (about 14.3%). A spot only counts when both the normal
> image and the radar image agree.
>
> Key numbers
> - Water: 4.22% of the area (0.62 km²)
> - Built-up: 14.27% of the area (2.11 km²)
> - Water found by the normal image 6.08%, by radar 4.44%, by both 4.22%
> - Built-up found by the normal image 62.54%, by radar 19.78%, by both 14.27%
>
> **Medium confidence** — the radar and the normal image agree on only 21% of the built-up spots they found.
>
> How we know: We used two kinds of satellite image: a normal (optical) image that records sunlight
> reflected from the ground, and a radar (SAR) image that records how the surface bounces back radar
> signals. Calm water looks dark to radar; buildings reflect radar strongly, and the normal image adds
> colour clues.

Scenario 5 adds the caveat *"The two images differ in how green the land is (for example a dry year versus
a wet year). Dry bare fields can look like buildings, so some of this change may be season or rainfall
rather than real change. Images from the same season give a fairer comparison."* Answers that cannot be
given (NOT_AVAILABLE) say in plain words what went wrong and what to do next, for example *"The radar
image is an ordinary picture, not real radar measurements ..."* followed by *"Upload a real Sentinel-1
radar file (GeoTIFF), or use 'Fetch from Earth Engine' ..."*.

**Scenario 6: Fetch from Earth Engine** (needs Earth Engine auth, the same as the Map Analysis tab):
1. In **Upload Analysis**, open **Fetch from Earth Engine**, choose **Optical + SAR**, pick **Draw rectangle** and
   draw a box of a few km around Bellandur Lake (the mini map opens there), or use
   `POST /api/gee/fetch` with bbox `[77.640, 12.915, 77.680, 12.945]`.
2. Set the dates to 2024-01-01 to 2024-03-31 and click **Fetch from Earth Engine**.
3. Expected result:
   - **Upload:** accepted in about 10-25 s, with a Sentinel-2 L2A (6 bands, 18 cloud-masked scenes) and a
     Sentinel-1 GRD (VV/VH dB, 6 scenes) GeoTIFF on one grid (EPSG:32643, 10 m, 439 x 337 px for that bbox,
     100% overlap). Band roles are set automatically.
   - **Answer:** *Map water and built-up areas* gives water **4.29%** and built-up **13.68%**. The
     committed sample pair gives 4.22% / 14.27%, because it was made with a simpler cloud filter.
   - **Source:** the trace and reports show `Google Earth Engine`, the collection IDs, date ranges, bands and scale.
   - **Limits:** boxes over 10 x 10 km are refused with a message. Without Earth Engine credentials the
     button is disabled with "Earth Engine not configured - use samples/ or upload GeoTIFFs".

**Scenario 7: anywhere in India** (dropdowns only; the list works offline, the fetch needs Earth Engine):
1. **Map Analysis** sidebar: **State / UT** lists all 36 states and UTs. After picking one, **District / City**
   shows "Major cities" (capital + biggest) and then "All districts". Picking a district flies the map there,
   framing the whole district: West Bengal → Kolkata (zoom 12), Assam → Guwahati / Dispur (Kamrup
   Metropolitan, zoom 10), Ladakh → Leh (zoom 7), Rajasthan → Jaipur (zoom 8), Kerala → Thiruvananthapuram (zoom 10).
2. **Fetch from Earth Engine**: choose **Optical + SAR**, **State / UT and district**, West Bengal → Kolkata,
   box 5 km, dates 2024-01-01 to 2024-03-31. A small preview map flies to Kolkata and shows the box.
   Large districts are only partly covered by the box; use **Draw rectangle** for a specific spot.
3. Expected result (run on 2026-09-26):
   - **Upload:** accepted in about 16 s: Sentinel-2 L2A (6 bands, 36 cloud-masked scenes) + Sentinel-1 GRD
     (VV/VH dB, 14 scenes), EPSG:32645, 10 m, 506 x 502 px, 100% overlap.
   - **Answer:** *Map water and built-up areas* gives "About 4.0% of the area is water and 34.5% of the
     area is built-up (buildings and roads)." (water 3.98%, 1.01 km²; built-up 34.48%, 8.76 km² of 25.40 km²),
     Medium confidence: the radar and the normal image agree on only 49% of the built-up spots they found.

## 3. Same scenarios from the command line

```powershell
cd backend
python -m app.predict --input ..\samples\manifest.json --out ..\predictions.json
```

Expected status counts: `{'OK': 6, 'REJECTED': 1}`. The short answers are `urban`, the caption, the
metadata text, the water/built-up text, `increased`, `increased`, and `no_overlap` for the rejection.
The CLI keeps these short canonical answers for benchmark scoring; it does not include the
plain-language answers.

## 4. Tests

```powershell
cd backend; pytest                                   # 460 tests
cd ..\ml\vqa_head; ..\..\.venv\Scripts\python.exe -m pytest
cd ..\landcover_patch; ..\..\.venv\Scripts\python.exe -m pytest
cd ..\..\frontend; npm test
```
