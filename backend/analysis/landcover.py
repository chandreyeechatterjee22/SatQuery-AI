import ee

def analyze_landcover(aoi):
    """
    Uses ESA WorldCover (10m) to estimate land-cover composition within the AOI.
    Classes:
    10: Trees
    20: Shrubland
    30: Grassland
    40: Cropland
    50: Built-up
    60: Bare / sparse vegetation
    70: Snow and ice
    80: Permanent water bodies
    90: Herbaceous wetland
    95: Mangroves
    100: Moss and lichen
    """
    try:
        # Get the latest ESA WorldCover map (2021)
        worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()
        
        # Calculate pixel counts for each class within the AOI
        pixel_area = ee.Image.pixelArea()
        class_areas = worldcover.multiply(0).add(worldcover).eq([10, 20, 30, 40, 50, 60, 80]).multiply(pixel_area)
        class_areas = class_areas.rename(['Trees', 'Shrubland', 'Grassland', 'Cropland', 'Built-up', 'Bare', 'Water'])
        
        stats = class_areas.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=aoi,
            scale=10,
            maxPixels=1e9
        ).getInfo()
        
        # Calculate total area
        total_area = sum(stats.values()) if stats else 0
        
        if total_area == 0:
             return {"warning": False, "composition": {}, "message": "Could not calculate land cover area."}
        
        composition = {k: round((v / total_area) * 100, 2) for k, v in stats.items()}
        
        built_up_pct = composition.get('Built-up', 0)
        
        warning = built_up_pct > 50
        message = ""
        if warning:
             message = "Warning: The selected Area of Interest is predominantly built-up. Agricultural/vegetation analysis may not be highly relevant."
             
        return {
            "warning": warning,
            "message": message,
            "composition": composition
        }
    except Exception as e:
        print(f"Error in landcover analysis: {e}")
        return {"warning": False, "composition": {}, "message": "Failed to analyze land cover."}
