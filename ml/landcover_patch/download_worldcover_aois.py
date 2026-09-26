"""Download the Bengaluru evaluation areas via Earth Engine: Sentinel-2 composites + ESA WorldCover 2021.

Usage (PowerShell, from the repo root; needs Earth Engine auth, see README):
    .\\.venv\\Scripts\\python.exe ml\\landcover_patch\\download_worldcover_aois.py

Writes data/worldcover_eval/{aoi}_s2_2021.tif (B2,B3,B4,B8,B11,B12, Jan-Mar median),
{aoi}_wc.tif, and sarjapur_s2_{2019,2025}.tif for the season case. ~20 MB total.
"""
import sys
import urllib.request

import common  # noqa: F401  (backend imports)

OUT = common.REPO_ROOT / "data" / "worldcover_eval"
AOIS = {  # lon/lat boxes, ~4.3 x 3.3 km each
    "sarjapur": [77.700, 12.880, 77.740, 12.910],
    "yelahanka": [77.570, 13.080, 77.610, 13.110],
    "bellandur": [77.640, 12.915, 77.680, 12.945],
    "hoskote": [77.770, 13.050, 77.810, 13.080],
}
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
CRS = "EPSG:32643"


def s2_composite(ee, aoi, year):
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi)
           .filterDate(f"{year}-01-01", f"{year}-03-31").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 10)))
    return col.median().select(S2_BANDS).toUint16()


def save(img, aoi, path):
    url = img.getDownloadURL({"region": aoi, "scale": 10, "crs": CRS, "format": "GEO_TIFF"})
    urllib.request.urlretrieve(url, path)
    print("saved", path.name)


def main():
    import ee

    from gee_service import get_gee_project_id

    ee.Initialize(project=get_gee_project_id())
    OUT.mkdir(parents=True, exist_ok=True)
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().toUint8()
    for name, box in AOIS.items():
        aoi = ee.Geometry.Rectangle(box)
        save(s2_composite(ee, aoi, 2021), aoi, OUT / f"{name}_s2_2021.tif")
        save(wc, aoi, OUT / f"{name}_wc.tif")
    aoi = ee.Geometry.Rectangle(AOIS["sarjapur"])
    for year in (2019, 2025):
        save(s2_composite(ee, aoi, year), aoi, OUT / f"sarjapur_s2_{year}.tif")


if __name__ == "__main__":
    sys.exit(main())
