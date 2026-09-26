"""HTTP routes for fetching imagery from Google Earth Engine into an upload."""
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import gee_fetch

router = APIRouter(prefix="/api/gee", tags=["earth-engine"])


class FetchRequest(BaseModel):
    mode: str = Field(..., description="single | optical_sar | bi_temporal")
    bbox: List[float] = Field(..., description="[west, south, east, north] in degrees, max ~10 x 10 km")
    date_ranges: List[List[str]] = Field(..., description="[[start, end]] (two ranges for bi_temporal)")


@router.get("/status")
def gee_status():
    return {**gee_fetch.status(), "max_side_km": gee_fetch.MAX_SIDE_KM}


@router.post("/fetch", status_code=201)
def gee_fetch_upload(request: FetchRequest):
    try:
        return gee_fetch.fetch(request.mode, request.bbox, request.date_ranges)
    except gee_fetch.FetchError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
