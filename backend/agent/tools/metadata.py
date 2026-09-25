"""Answer questions about the uploaded files themselves (bands, CRS, resolution, ...).

Everything is read from the stored rasterio metadata, so confidence is 1.0;
band roles that were only inferred are flagged in the answer.
"""
import re

from agent import tasks
from agent.registry import Tool, ToolResult

FIELDS = ["bands", "dtype", "crs", "resolution", "size", "bounds", "date", "sensor"]

_FIELD_PATTERNS = {
    "bands": r"\bbands?\b",
    "dtype": r"\b(data ?type|dtype|bit depth|bits?)\b",
    "crs": r"\b(crs|projection|epsg|coordinate)",
    "resolution": r"\b(resolution|pixel size|gsd)\b",
    "size": r"\b(dimensions?|size|width|height|how many pixels)\b",
    "bounds": r"\b(extent|bounds|bounding box|footprint|where)\b",
    "date": r"\b(date|when)\b",
    "sensor": r"\b(sensor|satellite)\b",
}

_SENSOR_LABELS = {
    "sentinel2": "Sentinel-2", "cartosat2s": "Cartosat-2S MX", "bgrn": "4-band blue/green/red/NIR",
    "rgb": "RGB", "sar": "SAR", "described": "from band descriptions", "unknown": "unknown",
}


class MetadataTool(Tool):
    name = "image_metadata"
    version = "1.0.0"
    task = tasks.METADATA
    description = "Report band layout, data type, CRS, resolution, size, extent and dates."
    params = {"fields": {"type": "enum_list", "choices": FIELDS, "min_items": 1,
                         "default": FIELDS}}

    def extract_params(self, question, ctx):
        asked = [f for f, p in _FIELD_PATTERNS.items() if re.search(p, question, re.IGNORECASE)]
        return {"fields": asked or FIELDS}

    def run(self, ctx, params, query_id):
        fields = params["fields"]
        lines = [f"File {f['slot']} ({f['filename']}): " + "; ".join(_describe(f, fields))
                 for f in ctx.files]
        evidence = [{"id": f"preview_{f['slot']}", "kind": "preview",
                     "label": f"File {f['slot']} preview ({f['filename']})",
                     "url": _ensure_preview(ctx, f["slot"])} for f in ctx.files]
        pair = ctx.manifest.get("pair")
        if pair and "bounds" in fields and pair.get("overlap_fraction") is not None:
            lines.append(f"The two files overlap by {pair['overlap_fraction']:.0%} "
                         "of the smaller image.")
        return ToolResult(answer="\n".join(lines), confidence=1.0, evidence_images=evidence,
                          data={"fields": fields})


def _ensure_preview(ctx, slot):
    ctx.preview_path(slot)
    return ctx.preview_url(slot)


def _describe(f, fields):
    meta, bands = f["metadata"], f["bands"]
    parts = []
    for field in fields:
        if field == "bands":
            roles = ", ".join(f"{role}=band {i}" for role, i in bands["roles"].items()) or "no roles"
            inferred = "" if bands["source"] in ("descriptions", "sensor_hint") else " (inferred from band count)"
            parts.append(f"{meta['band_count']} band(s), {roles}{inferred}")
        elif field == "dtype":
            parts.append("data type " + "/".join(sorted(set(meta["dtypes"]))))
        elif field == "crs":
            parts.append(f"CRS {meta['crs']}" if meta["crs"] else "no CRS")
        elif field == "resolution":
            r = meta["resolution"]
            parts.append(f"resolution {r['x']:g} x {r['y']:g} {r['units']}")
        elif field == "size":
            parts.append(f"{meta['width']} x {meta['height']} pixels")
        elif field == "bounds":
            b = meta["bounds"]
            parts.append(f"bounds [{b['left']:g}, {b['bottom']:g}, {b['right']:g}, {b['top']:g}]")
        elif field == "date":
            parts.append(f"date {f['date']}" if f.get("date") else "no date given")
        elif field == "sensor":
            parts.append(f"{f['kind']} image, sensor profile "
                         f"{_SENSOR_LABELS.get(bands['sensor'], bands['sensor'])}")
    return parts
