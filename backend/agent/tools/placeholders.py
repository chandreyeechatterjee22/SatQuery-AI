"""Placeholder tools for tasks whose models are not built yet.

They extract and validate params like the real tools will, so routing and
the trace work end to end, but they always report NOT_AVAILABLE.
"""
import re

from agent import tasks
from agent.registry import PlaceholderTool

WATER_BUILTUP_CLASSES = ["water", "built_up"]
LANDCOVER_CLASSES = ["water", "built_up", "vegetation", "other"]

_CLASS_PATTERNS = {
    "water": r"\b(water\w*|flood\w*|rivers?|lakes?|reservoirs?|ponds?|inundat\w*)",
    "built_up": r"\b(built[- ]?up|urban\w*|buildings?|settlements?|impervious|concrete|city)\b",
    "vegetation": r"\b(vegetat\w*|green\w*|forests?|trees?|crops?|farm\w*|agricultur\w*)",
}


def classes_in(question, allowed):
    found = [c for c, p in _CLASS_PATTERNS.items()
             if c in allowed and re.search(p, question, re.IGNORECASE)]
    return found or list(allowed)


class VqaPlaceholder(PlaceholderTool):
    name = "rs_vqa"
    task = tasks.VQA
    description = "Answer free-form questions about a single image with a remote-sensing VLM."
    params = {"question": {"type": "str", "max_length": 500, "required": True}}
    unavailable_reason = "No visual question-answering model is loaded."

    def extract_params(self, question, ctx):
        return {"question": question}


class CaptionPlaceholder(PlaceholderTool):
    name = "rs_caption"
    task = tasks.CAPTION
    description = "Describe a single image with a remote-sensing captioning model."
    params = {}
    unavailable_reason = "No image-captioning model is loaded."


class WaterBuiltupPlaceholder(PlaceholderTool):
    name = "optical_sar_mapper"
    task = tasks.WATER_BUILTUP
    description = "Map water and built-up area from an optical + SAR pair."
    params = {"classes": {"type": "enum_list", "choices": WATER_BUILTUP_CLASSES,
                          "min_items": 1, "default": WATER_BUILTUP_CLASSES}}
    unavailable_reason = "Optical + SAR water/built-up mapping is not available yet."

    def extract_params(self, question, ctx):
        return {"classes": classes_in(question, WATER_BUILTUP_CLASSES)}


class ChangePlaceholder(PlaceholderTool):
    name = "landcover_change"
    task = tasks.CHANGE
    description = "Classify land cover on both dates and report per-class area change."
    params = {"classes": {"type": "enum_list", "choices": LANDCOVER_CLASSES,
                          "min_items": 1, "default": LANDCOVER_CLASSES}}
    unavailable_reason = "Land-cover change analysis is not available yet."

    def extract_params(self, question, ctx):
        return {"classes": classes_in(question, LANDCOVER_CLASSES)}
