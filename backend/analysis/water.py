import ee
from gee_service import get_map_tile_url, get_thumb_url

def analyze_water(s2_image, aoi):
    """
    Calculates NDWI using Sentinel-2 B3 (Green) and B8 (NIR).
    NDWI = (Green - NIR) / (Green + NIR)
    """
    ndwi = s2_image.normalizedDifference(['B3', 'B8']).rename('NDWI')

    # Water threshold: NDWI > 0 typically indicates water bodies
    water_mask = ndwi.gt(0).rename('NDWI')

    # Calculate water area: mask * pixel area
    pixel_area = ee.Image.pixelArea()
    water_area_img = water_mask.multiply(pixel_area)  # band name: 'NDWI'

    water_stats = water_area_img.reduceRegion(
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

    ndwi_stats = ndwi.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.minMax(),
            sharedInputs=True
        ),
        geometry=aoi,
        scale=10,
        maxPixels=1e9
    ).getInfo()

    # Band name inherited from ndwi rename = 'NDWI'
    water_area_sqm = water_stats.get('NDWI') or 0
    total_area_sqm = total_area_stats.get('area') or 1

    water_area_ha = water_area_sqm / 10000
    total_area_ha = total_area_sqm / 10000
    pct_coverage = (water_area_sqm / total_area_sqm) * 100

    # Choose unit: ha for farm-sized, km² for large AOI
    if total_area_ha > 10000:
        area_display = round(water_area_sqm / 1e6, 2)
        area_unit = "km²"
        total_display = round(total_area_sqm / 1e6, 2)
    else:
        area_display = round(water_area_ha, 2)
        area_unit = "ha"
        total_display = round(total_area_ha, 2)

    vis_params = {
        'min': 0.0,
        'max': 1.0,
        'palette': ['00FFFF', '0000FF']  # Cyan to Blue
    }

    # Show masked water layer clipped to AOI
    water_layer = ndwi.updateMask(water_mask).clip(aoi)
    tile_url = get_map_tile_url(water_layer, vis_params)
    thumb_url = get_thumb_url(water_layer, vis_params, aoi)

    return {
        "stats": {
            "area": area_display,
            "area_unit": area_unit,
            "total_aoi": total_display,
            "percentage_coverage": round(pct_coverage, 2),
            "mean_ndwi": round(ndwi_stats.get('NDWI_mean') or 0, 3),
            "max_ndwi": round(ndwi_stats.get('NDWI_max') or 0, 3),
            "min_ndwi": round(ndwi_stats.get('NDWI_min') or 0, 3),
        },
        "tile_url": tile_url,
        "thumb_url": thumb_url
    }
