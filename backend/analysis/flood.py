import ee
from gee_service import get_map_tile_url, get_thumb_url

def analyze_flood(s2_col, current_image, aoi):
    """
    Temporal flood detection proxy using Sentinel-2 NDWI.

    Method:
    - Current water: NDWI > 0 on the recent composite image.
    - Historical baseline: NDWI > 0 on the full 12-month collection median.
    - ESA WorldCover permanent water (Class 80) is added to the baseline.
    - Potential Flooded Areas = Current Water AND NOT Historical Baseline Water.

    This approach reduces false positives from permanent water bodies.
    IMPORTANT: This result is labelled "Potential Flooded Areas".
    It is a spectral water proxy, NOT confirmed flood mapping.
    Official flood confirmation requires dedicated SAR data and validation.
    """
    # Current water mask from recent composite
    current_ndwi = current_image.normalizedDifference(['B3', 'B8']).rename('NDWI')
    current_water = current_ndwi.gt(0)

    # Historical baseline: median of the full 12-month collection
    # This is broader than the recent 3-month composite, so it will include
    # seasonal water that shouldn't be flagged as flood
    baseline_image = s2_col.median()
    baseline_ndwi = baseline_image.normalizedDifference(['B3', 'B8'])
    baseline_water = baseline_ndwi.gt(0)

    # ESA WorldCover permanent water bodies (Class 80)
    worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
    permanent_water = worldcover.eq(80)

    # Combined historical water reference
    historical_water = baseline_water.Or(permanent_water)

    # Potential flood = currently wet AND not historically wet
    potential_flood = current_water.And(historical_water.Not()).rename('flood')

    # Calculate areas
    pixel_area = ee.Image.pixelArea()

    flood_area_sqm = potential_flood.multiply(pixel_area).rename('flood').reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=10,
        maxPixels=1e9
    ).getInfo().get('flood') or 0

    total_area_sqm = pixel_area.rename('area').reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=10,
        maxPixels=1e9
    ).getInfo().get('area') or 1

    flood_area_ha = flood_area_sqm / 10000
    total_area_ha = total_area_sqm / 10000
    pct_coverage = (flood_area_sqm / total_area_sqm) * 100

    # Choose unit
    if total_area_ha > 10000:
        area_display = round(flood_area_sqm / 1e6, 2)
        area_unit = "km²"
        total_display = round(total_area_sqm / 1e6, 2)
    else:
        area_display = round(flood_area_ha, 2)
        area_unit = "ha"
        total_display = round(total_area_ha, 2)

    vis_params = {
        'min': 0,
        'max': 1,
        'palette': ['FF4500']  # Red-orange for potential flood
    }

    flood_layer = potential_flood.updateMask(potential_flood).clip(aoi)
    tile_url = get_map_tile_url(flood_layer, vis_params)
    thumb_url = get_thumb_url(flood_layer, vis_params, aoi)

    return {
        "stats": {
            "area": area_display,
            "area_unit": area_unit,
            "total_aoi": total_display,
            "percentage_coverage": round(pct_coverage, 2),
        },
        "tile_url": tile_url,
        "thumb_url": thumb_url,
        "method_note": (
            "Potential Flooded Areas detected using Sentinel-2 NDWI temporal comparison "
            "(recent composite vs 12-month baseline + ESA WorldCover permanent water). "
            "This is a spectral estimate only — NOT confirmed flood mapping."
        )
    }
