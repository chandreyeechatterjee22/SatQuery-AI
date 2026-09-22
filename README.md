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

## Backend Setup

1. Create a virtual environment and install dependencies:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Authenticate with Earth Engine:
If you are testing locally, run:
```bash
earthengine authenticate
```

If you are deploying to a server, set environment variables:
`GEE_SERVICE_ACCOUNT`
`GEE_PRIVATE_KEY`

3. Start the FastAPI server:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Start the React development server:
```bash
npm run dev
```

The app will be available at `http://localhost:5173`. Make sure the backend is running on `http://localhost:8000`.

## Features
- **Real GEE Integration:** Performs calculations strictly within user-drawn AOIs.
- **Sentinel-2 Harmonized:** Uses the latest available cloud-free composites via Cloud Score+.
- **Landcover Validation:** Validates AOI context using ESA WorldCover.
- **Three Core Queries:** Vegetation (NDVI), Water (NDWI), and Potential Flood Detection.
