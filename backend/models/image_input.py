"""Turn an uploaded raster into the PIL RGB image the CLIP encoder sees.

Uses the same band-role selection and 2-98% stretch as the preview, so the
model sees what the user sees. The VQA head is trained through this exact
function too (ml/vqa_head), keeping train and serve inputs identical.
"""
from PIL import Image

from raster.preview import display_rgb

MODEL_INPUT_MAX_SIZE = 512  # CLIP resizes to 224 anyway; keep reads cheap


def load_model_image(path, bands):
    rgb, _, rendering, _ = display_rgb(path, bands, max_size=MODEL_INPUT_MAX_SIZE)
    return Image.fromarray(rgb.transpose(1, 2, 0), mode="RGB"), rendering
