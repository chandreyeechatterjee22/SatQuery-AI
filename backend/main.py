from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import ee
from datetime import datetime, timedelta

from gee_service import initialize_gee, get_s2_sr_cld_col, get_map_tile_url, get_thumb_url
from intent import classify_intent
from analysis.landcover import analyze_landcover
from analysis.vegetation import analyze_vegetation
from analysis.water import analyze_water
from analysis.flood import analyze_flood
from ingest.router import router as uploads_router
from agent.router import router as agent_router

app = FastAPI(title="SatQuery AI API")
app.include_router(uploads_router)
app.include_router(agent_router)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    try:
        initialize_gee()
    except Exception as e:
        print(f"GEE Initialization failed: {e}")

class AOIRequest(BaseModel):
    state: str
    area: str
    geometry: Dict[str, Any]  # GeoJSON dict

class AnalyzeRequest(BaseModel):
    state: str
    area: str
    geometry: Dict[str, Any]
    query: str

# Sample Location Data (India) - centroid + zoom level used to fly the map to the selected district
LOCATIONS = {
    "Karnataka": {
        "Bengaluru Urban": {"lat": 12.9716, "lon": 77.5946, "zoom": 11},
        "Bengaluru Rural": {"lat": 13.2846, "lon": 77.5946, "zoom": 10},
        "Mysuru": {"lat": 12.2958, "lon": 76.6394, "zoom": 11},
        "Mandya": {"lat": 12.5242, "lon": 76.8958, "zoom": 10},
        "Tumakuru": {"lat": 13.3379, "lon": 77.1173, "zoom": 10},
        "Mangaluru": {"lat": 12.9141, "lon": 74.8560, "zoom": 11},
        "Shivamogga": {"lat": 13.9299, "lon": 75.5681, "zoom": 10},
    },
    "Maharashtra": {
        "Mumbai": {"lat": 19.0760, "lon": 72.8777, "zoom": 11},
        "Pune": {"lat": 18.5204, "lon": 73.8567, "zoom": 11},
        "Nagpur": {"lat": 21.1458, "lon": 79.0882, "zoom": 11},
        "Nashik": {"lat": 19.9975, "lon": 73.7898, "zoom": 11},
    },
    "Tamil Nadu": {
        "Chennai": {"lat": 13.0827, "lon": 80.2707, "zoom": 11},
        "Coimbatore": {"lat": 11.0168, "lon": 76.9558, "zoom": 11},
        "Madurai": {"lat": 9.9252, "lon": 78.1198, "zoom": 11},
    },
}

@app.get("/api/states")
def get_states():
    return {"states": list(LOCATIONS.keys())}

@app.get("/api/areas/{state}")
def get_areas(state: str):
    if state not in LOCATIONS:
        raise HTTPException(status_code=404, detail="State not found")
    return {"areas": list(LOCATIONS[state].keys())}

@app.get("/api/location/{state}/{area}")
def get_location(state: str, area: str):
    if state not in LOCATIONS or area not in LOCATIONS[state]:
        raise HTTPException(status_code=404, detail="Location not found")
    return LOCATIONS[state][area]

def dict_to_ee_geometry(geom_dict: Dict[str, Any]) -> ee.Geometry:
    """Converts a GeoJSON dictionary to an Earth Engine Geometry."""
    try:
        # Assuming Polygon or MultiPolygon GeoJSON geometry dict
        return ee.Geometry(geom_dict)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid geometry format: {e}")

@app.post("/api/sentinel")
def get_sentinel_info(request: AOIRequest):
    aoi = dict_to_ee_geometry(request.geometry)
    
    # 12-month lookback
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Get S2 collection
    s2_col = get_s2_sr_cld_col(aoi, start_date_str, end_date_str)
    
    # Get the most recent image (or median composite if preferred. Let's use most recent clear image or a short median)
    # To keep it simple and robust, let's take the median over the last 30 available days, or just the median of the entire collection?
    # The requirement: "By default, use the most recent suitable imagery available within the previous 12 months... If a multi-image median/composite is used, display it as an analysis period/range"
    # We will use a 3-month median composite from the most recent available data to ensure full coverage of AOI
    
    recent_col = s2_col.filterDate((end_date - timedelta(days=90)).strftime('%Y-%m-%d'), end_date_str)
    
    # Check if there are images
    count = recent_col.size().getInfo()
    if count == 0:
        # Fallback to whole year
        recent_col = s2_col
        period_str = f"{start_date_str} to {end_date_str}"
    else:
        period_str = f"{(end_date - timedelta(days=90)).strftime('%Y-%m-%d')} to {end_date_str}"

    s2_median = recent_col.median().clip(aoi)

    # True Color visualization
    vis_params = {
        'bands': ['B4', 'B3', 'B2'],
        'min': 0,
        'max': 3000,
        'gamma': 1.4
    }
    
    tile_url = get_map_tile_url(s2_median, vis_params)
    thumb_url = get_thumb_url(s2_median, vis_params, aoi)

    # Validate Landcover
    landcover_stats = analyze_landcover(aoi)

    return {
        "satellite": "Sentinel-2 (Harmonized)",
        "source": "Google Earth Engine",
        "analysis_period": period_str,
        "tile_url": tile_url,
        "thumb_url": thumb_url,
        "landcover": landcover_stats
    }

@app.post("/api/analyze")
def run_analysis(request: AnalyzeRequest):
    aoi = dict_to_ee_geometry(request.geometry)
    intent = classify_intent(request.query)
    
    if intent == "unknown":
        raise HTTPException(status_code=400, detail="Unable to understand the query. Please ask about vegetation, water, or floods.")

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=365)
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    s2_col = get_s2_sr_cld_col(aoi, start_date_str, end_date_str)
    # Using 3 month composite as baseline for analysis
    recent_col = s2_col.filterDate((end_date - timedelta(days=90)).strftime('%Y-%m-%d'), end_date_str)
    
    # Need to handle empty collection case appropriately in production
    
    s2_image = recent_col.median().clip(aoi)
    period_str = f"{(end_date - timedelta(days=90)).strftime('%Y-%m-%d')} to {end_date_str}"
    
    result = {
        "intent": intent,
        "analysis_period": period_str,
        "stats": {},
        "explanation": "",
        "tile_url": ""
    }
    
    if intent == "vegetation":
        veg_res = analyze_vegetation(s2_image, aoi)
        result["stats"] = veg_res["stats"]
        result["explanation"] = (
            f"Estimated vegetation covers approximately {veg_res['stats']['percentage_coverage']}% "
            f"({veg_res['stats']['area']} {veg_res['stats']['area_unit']}) of the selected area, "
            f"based on NDVI analysis (mean NDVI: {veg_res['stats']['mean_ndvi']})."
        )
        result["tile_url"] = veg_res["tile_url"]
        result["thumb_url"] = veg_res["thumb_url"]
        result["index"] = "NDVI"

    elif intent == "water":
        water_res = analyze_water(s2_image, aoi)
        result["stats"] = water_res["stats"]
        result["explanation"] = (
            f"Estimated water bodies cover approximately {water_res['stats']['percentage_coverage']}% "
            f"({water_res['stats']['area']} {water_res['stats']['area_unit']}) of the selected area, "
            f"based on NDWI analysis (mean NDWI: {water_res['stats']['mean_ndwi']})."
        )
        result["tile_url"] = water_res["tile_url"]
        result["thumb_url"] = water_res["thumb_url"]
        result["index"] = "NDWI"

    elif intent == "flood":
        flood_res = analyze_flood(s2_col, s2_image, aoi)
        result["stats"] = flood_res["stats"]
        result["explanation"] = (
            f"Potential Flooded Areas detected over approximately {flood_res['stats']['percentage_coverage']}% "
            f"({flood_res['stats']['area']} {flood_res['stats']['area_unit']}) of the selected area. "
            f"{flood_res['method_note']}"
        )
        result["tile_url"] = flood_res["tile_url"]
        result["thumb_url"] = flood_res["thumb_url"]
        result["index"] = "Potential Flood Proxy"

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
