import ee
from datetime import datetime, timezone
from gee_service import get_map_tile_url, get_thumb_url

def analyze_vegetation(s2_image, aoi):
    """
    Calculates NDVI using Sentinel-2 B8 (NIR) and B4 (Red).
    NDVI = (NIR - Red) / (NIR + Red)
    """
    ndvi = s2_image.normalizedDifference(['B8', 'B4']).rename('NDVI')

    # Vegetation threshold: NDVI > 0.2 typically indicates vegetation
    veg_mask = ndvi.gt(0.2).rename('NDVI')

    # Calculate vegetated area: mask * pixel area
    pixel_area = ee.Image.pixelArea()
    veg_area_img = veg_mask.multiply(pixel_area)  # band name: 'NDVI'

    veg_stats = veg_area_img.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=10,
        maxPixels=1e9
    ).getInfo()

    total_area_stats = pixel_area.rename('area').reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=10,
        maxPixels=1e9
    ).getInfo()

    ndvi_stats = ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.minMax(),
            sharedInputs=True
        ),
        geometry=aoi,
        scale=10,
        maxPixels=1e9
    ).getInfo()

    # Band name inherited from ndvi rename = 'NDVI'
    veg_area_sqm = veg_stats.get('NDVI') or 0
    total_area_sqm = total_area_stats.get('area') or 1

    veg_area_ha = veg_area_sqm / 10000
    total_area_ha = total_area_sqm / 10000
    pct_coverage = (veg_area_sqm / total_area_sqm) * 100

    # Choose unit: ha for farm-sized, km² for large AOI
    if total_area_ha > 10000:
        area_display = round(veg_area_sqm / 1e6, 2)
        area_unit = "km²"
        total_display = round(total_area_sqm / 1e6, 2)
    else:
        area_display = round(veg_area_ha, 2)
        area_unit = "ha"
        total_display = round(total_area_ha, 2)

    vis_params = {
        'min': 0.0,
        'max': 0.8,
        'palette': ['#FFFFFF', '#CE7E45', '#DF923D', '#F1B555', '#FCD163',
                    '#99B718', '#74A901', '#66A000', '#529400', '#3E8601',
                    '#207401', '#056201', '#004C00', '#023B01', '#012E01',
                    '#011D01', '#011301']
    }

    # Show full NDVI layer (positive values only) clipped to AOI
    ndvi_clipped = ndvi.clip(aoi).updateMask(ndvi.gt(0))
    tile_url = get_map_tile_url(ndvi_clipped, vis_params)
    thumb_url = get_thumb_url(ndvi_clipped, vis_params, aoi)

    return {
        "stats": {
            "area": area_display,
            "area_unit": area_unit,
            "total_aoi": total_display,
            "percentage_coverage": round(pct_coverage, 2),
            "mean_ndvi": round(ndvi_stats.get('NDVI_mean') or 0, 3),
            "max_ndvi": round(ndvi_stats.get('NDVI_max') or 0, 3),
            "min_ndvi": round(ndvi_stats.get('NDVI_min') or 0, 3),
        },
        "tile_url": tile_url,
        "thumb_url": thumb_url
    }
