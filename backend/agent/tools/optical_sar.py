"""Water and built-up mapping from an optical + SAR pair, with per-modality evidence.

Confidence is the modality agreement (pixels both flag / pixels either flags),
averaged over the requested classes. It is a consensus measure, not a
calibrated probability, and is None when only one modality could be used.
"""
from agent import tasks
from agent.registry import Tool, ToolResult
from agent.tools.clip_common import preview_evidence
from agent.tools.question_classes import classes_in
from local_analysis import optical_sar
from local_analysis.optical_sar import CLASS_LABELS, CLASSES, DEFAULTS
from local_analysis.overlays import render_overlay

COLOURS = {
    "water": {"both": "#1f6feb", "optical_only": "#79c0ff", "sar_only": "#a371f7"},
    "built_up": {"both": "#d73a49", "optical_only": "#f9a36b", "sar_only": "#e3b341"},
}
ALPHA = {"both": 210, "optical_only": 160, "sar_only": 160}


class OpticalSarTool(Tool):
    name = "optical_sar_mapper"
    version = "1.0.0"
    task = tasks.WATER_BUILTUP
    description = ("Map water (low SAR backscatter + optical water index) and built-up "
                   "(high SAR backscatter + optical built-up index) from an optical + SAR pair.")
    params = {
        "classes": {"type": "enum_list", "choices": list(CLASSES), "min_items": 1, "default": list(CLASSES)},
        "sar_water_db": {"type": "float", "min": -35, "max": -5, "default": DEFAULTS["sar_water_db"]},
        "sar_builtup_db": {"type": "float", "min": -15, "max": 10, "default": DEFAULTS["sar_builtup_db"]},
        "optical_water_threshold": {"type": "float", "min": -1, "max": 1,
                                    "default": DEFAULTS["optical_water_threshold"]},
        "optical_builtup_threshold": {"type": "float", "min": -1, "max": 1,
                                      "default": DEFAULTS["optical_builtup_threshold"]},
        "ndvi_max_builtup": {"type": "float", "min": -1, "max": 1, "default": DEFAULTS["ndvi_max_builtup"]},
        "fusion": {"type": "enum", "choices": ["and", "or"], "default": DEFAULTS["fusion"]},
        "max_size": {"type": "int", "min": 128, "max": 2048, "default": DEFAULTS["max_size"]},
    }

    def extract_params(self, question, ctx):
        return {"classes": classes_in(question, list(CLASSES))}

    def check_params(self, params):
        if params["sar_builtup_db"] <= params["sar_water_db"]:
            return ["'sar_builtup_db' must be higher than 'sar_water_db'"]
        return []

    def inputs(self, ctx):
        roles = {1: "optical", 2: "sar"}
        return [{"slot": f["slot"], "filename": f["filename"], "kind": f["kind"], "role": roles[f["slot"]]}
                for f in ctx.files]

    def run(self, ctx, params, query_id):
        classes = params["classes"]
        result = optical_sar.map_water_builtup(
            ctx.path(1), ctx.file(1)["bands"], ctx.path(2), ctx.file(2)["bands"],
            params={k: v for k, v in params.items() if k != "classes"}, classes=classes)

        evidence = [preview_evidence(ctx, 1), preview_evidence(ctx, 2)]
        out_dir = ctx.query_dir(query_id)
        for cls in classes:
            evidence.append(self._overlay(ctx, query_id, out_dir, cls, result))

        agreements = [result["stats"][c]["agreement"] for c in classes
                      if result["stats"][c]["agreement"] is not None]
        confidence = sum(agreements) / len(agreements) if agreements else None
        return ToolResult(
            answer=answer_text(result, classes),
            confidence=confidence,
            evidence_images=evidence,
            data={"classes": result["stats"], "valid_pixels": result["valid_pixels"],
                  "valid_area_km2": result["valid_area_km2"], "methods": result["methods"],
                  "warnings": result["warnings"], "confidence_basis": "modality_agreement"},
            trace={"methods": result["methods"], "grid": list(result["grid"].shape),
                   "warnings": len(result["warnings"])},
        )

    def _overlay(self, ctx, query_id, out_dir, cls, result):
        m = result["masks"][cls]
        colours = COLOURS[cls]
        if m["optical"] is not None and m["sar"] is not None:
            parts = {"both": m["optical"] & m["sar"], "optical_only": m["optical"] & ~m["sar"],
                     "sar_only": m["sar"] & ~m["optical"]}
        elif m["final"] is not None:
            parts = {"optical_only" if m["optical"] is not None else "sar_only": m["final"]}
        else:
            parts = {}
        name = f"{cls}_overlay.png"
        render_overlay([(mask, colours[k], ALPHA[k]) for k, mask in parts.items() if mask is not None],
                       result["grid"].shape, out_dir / name)
        legend_labels = {"both": "optical + SAR agree", "optical_only": "optical only",
                         "sar_only": "SAR only"}
        return {"id": f"{cls}_overlay", "kind": "overlay", "class": cls, "base": "preview_1",
                "label": f"{CLASS_LABELS[cls]} mask", "url": ctx.evidence_url(query_id, name),
                "legend": [{"label": legend_labels[k], "color": colours[k]} for k in parts]}


def answer_text(result, classes):
    """Build the answer only from the computed stats."""
    methods = result["methods"]
    area = result["valid_area_km2"]
    scope = (f"the {area:g} km² both images cover" if area is not None
             else f"the {result['valid_pixels']} pixels both images cover")
    fusion = "both modalities must agree" if methods["fusion"] == "and" else "either modality is enough"
    lines = []
    for cls in classes:
        s = result["stats"][cls]
        label = CLASS_LABELS[cls]
        if s["percent"] is None:
            lines.append(f"{label}: not computed (neither modality has the needed bands).")
            continue
        head = f"{label}: {s['percent']:.2f}% of {scope}"
        if s["area_km2"] is not None:
            head += f" ({s['area_km2']:g} km²)"
        opt_method = methods["optical_water" if cls == "water" else "optical_built_up"]
        sar_rule = (f"{methods['sar_band']} < {methods['thresholds']['sar_water_db']:g} dB" if cls == "water"
                    else f"{methods['sar_band']} > {methods['thresholds']['sar_builtup_db']:g} dB")
        if s["both_percent"] is not None:
            detail = (f"Optical ({opt_method}) flagged {s['optical_percent']:.2f}%, SAR ({sar_rule}) "
                      f"flagged {s['sar_percent']:.2f}%; they agree on {s['both_percent']:.2f}% "
                      f"(optical only {s['optical_only_percent']:.2f}%, SAR only "
                      f"{s['sar_only_percent']:.2f}%, agreement {s['agreement']:.0%}).")
        elif s["optical_percent"] is not None:
            detail = f"Detected by optical only ({opt_method}); SAR could not be used."
        else:
            detail = f"Detected by SAR only ({sar_rule}); optical bands were missing."
        lines.append(f"{head}. {detail}")
    lines.append(f"Final masks: {fusion}.")
    return "\n".join(lines)
