import ee
import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_GEE_PROJECT_ID = 'satquery-ai-508105'

def get_gee_project_id():
    """GEE project id from env GEE_PROJECT_ID, falling back to the original default."""
    return os.getenv("GEE_PROJECT_ID") or DEFAULT_GEE_PROJECT_ID

def initialize_gee():
    """Initializes Google Earth Engine."""
    try:
        # If using a service account (recommended for production backend)
        service_account = os.getenv("GEE_SERVICE_ACCOUNT")
        private_key = os.getenv("GEE_PRIVATE_KEY")
        project_id = get_gee_project_id()

        if service_account and private_key:
            credentials = ee.ServiceAccountCredentials(service_account, private_key)
            ee.Initialize(credentials, project=project_id)
        else:
            # Fallback to local authentication for development
            ee.Initialize(project=project_id)
        print("Earth Engine initialized successfully.")
    except Exception as e:
        print(f"Failed to initialize Earth Engine: {e}")
        raise

def get_s2_sr_cld_col(aoi, start_date, end_date):
    """
    Fetches Sentinel-2 SR Harmonized collection with Cloud Score+ masking.
    Returns the median composite or a filtered image collection.
    """
    # Cloud Score+ Image Collection
    csPlus = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED')
    
    # Sentinel-2 SR Harmonized Image Collection
    s2Sr = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')

    # Filter collections by time and AOI
    s2_filtered = s2Sr.filterBounds(aoi).filterDate(start_date, end_date)
    cs_filtered = csPlus.filterBounds(aoi).filterDate(start_date, end_date)
    # Keep only scenes that already have a Cloud Score+ image (it lags new scenes by days).
    s2_filtered = s2_filtered.filter(ee.Filter.inList('system:index', cs_filtered.aggregate_array('system:index')))

    # Link collections
    def link_cs(img):
        # We find the corresponding CS+ image based on system:index
        cs_img = cs_filtered.filter(ee.Filter.eq('system:index', img.get('system:index'))).first()
        return img.addBands(cs_img.select('cs_cdf'))

    s2_with_cs = s2_filtered.map(link_cs)

    # Apply Cloud Score+ Masking (Threshold > 0.6 means high confidence of clear pixels)
    def apply_cs_mask(img):
        mask = img.select('cs_cdf').gte(0.6)
        return img.updateMask(mask)

    s2_masked = s2_with_cs.map(apply_cs_mask)
    
    return s2_masked

def get_map_tile_url(ee_object, vis_params):
    """Generates a tile URL for a given Earth Engine object."""
    try:
        map_id_dict = ee.Image(ee_object).getMapId(vis_params)
        return map_id_dict['tile_fetcher'].url_format
    except Exception as e:
        print(f"Error generating map tile URL: {e}")
        return None

def get_thumb_url(ee_object, vis_params, aoi, dimensions=400):
    """Generates a static preview PNG (cropped to the AOI) for a given Earth Engine object."""
    try:
        image = ee.Image(ee_object).visualize(**vis_params)
        return image.getThumbURL({'region': aoi, 'dimensions': dimensions, 'format': 'png'})
    except Exception as e:
        print(f"Error generating thumbnail URL: {e}")
        return None
