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
