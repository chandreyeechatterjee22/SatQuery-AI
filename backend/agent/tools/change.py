"""Bi-temporal land-cover change tool: per-class area deltas with answer text built from them.

Confidence is threshold robustness: the share of 27 threshold perturbations
(±0.05 on each index threshold) that reach the same increased / decreased /
unchanged conclusion for the classes asked about. It is not a probability.
"""
import numpy as np

from agent import tasks
from agent.registry import Tool, ToolNotAvailable, ToolResult
from agent.tools.clip_common import preview_evidence
from agent.tools.question_classes import classes_in
from local_analysis import landcover_change as lc
from local_analysis.landcover_change import CLASS_CODES, CLASS_LABELS, CLASSES, DEFAULTS
from local_analysis.overlays import render_overlay
from models import landcover_patch as lp

COLOURS = {"water": "#1f6feb", "built_up": "#d73a49", "vegetation": "#2da44e", "other": "#bf8700"}
MAP_ALPHA = 170
VERB = {lc.INCREASED: "increased", lc.DECREASED: "decreased", lc.UNCHANGED: "remained essentially unchanged"}
# Built-up direction comes from the fine-tuned land-cover model's scene-level P(urban) when available
# (pixel rules confuse dry bare fields with built-up). A change below this is "unchanged".
URBAN_UNCHANGED_TOLERANCE = 0.05
DISAGREEMENT_PENALTY = 0.5  # confidence multiplier when model and pixel rules disagree


class ChangeTool(Tool):
    name = "landcover_change"
    version = "1.0.0"
    task = tasks.CHANGE
    description = ("Classify land cover (water / built-up / vegetation / other) on both dates "
                   "from spectral indices and report per-class area change.")
    params = {
        "classes": {"type": "enum_list", "choices": list(CLASSES), "min_items": 1, "default": list(CLASSES)},
        "water_threshold": {"type": "float", "min": -1, "max": 1, "default": DEFAULTS["water_threshold"]},
        "vegetation_ndvi": {"type": "float", "min": -1, "max": 1, "default": DEFAULTS["vegetation_ndvi"]},
        "builtup_threshold": {"type": "float", "min": -1, "max": 1, "default": DEFAULTS["builtup_threshold"]},
        "ndvi_max_builtup": {"type": "float", "min": -1, "max": 1, "default": DEFAULTS["ndvi_max_builtup"]},
        "unchanged_tolerance_pp": {"type": "float", "min": 0, "max": 20,
                                   "default": DEFAULTS["unchanged_tolerance_pp"]},
        "max_size": {"type": "int", "min": 128, "max": 2048, "default": DEFAULTS["max_size"]},
        "urban_unchanged_tolerance": {"type": "float", "min": 0, "max": 0.5, "default": URBAN_UNCHANGED_TOLERANCE},
    }

    def extract_params(self, question, ctx):
        return {"classes": classes_in(question, list(CLASSES))}

    def inputs(self, ctx):
        before, after = _ordered(ctx)
        return [{"slot": f["slot"], "filename": f["filename"], "kind": f["kind"], "date": f.get("date"),
                 "role": role} for role, f in (("before", before), ("after", after))]

    def run(self, ctx, params, query_id):
        before, after = _ordered(ctx)
        try:
            result = lc.analyse_change(
                {"path": ctx.path(before["slot"]), "bands": before["bands"], "date": before.get("date")},
                {"path": ctx.path(after["slot"]), "bands": after["bands"], "date": after.get("date")},
                params={k: v for k, v in params.items() if k not in ("classes", "urban_unchanged_tolerance")})
        except lc.MissingBands as exc:
            raise ToolNotAvailable(f"Land-cover change needs multispectral images: {exc}") from exc

        focus = params["classes"]
        out_dir = ctx.query_dir(query_id)
        evidence = [preview_evidence(ctx, 1), preview_evidence(ctx, 2)]
        for role, f in (("before", before), ("after", after)):
            evidence.append(self._map(ctx, query_id, out_dir, role, f, result))

        per_class = {c: lc.class_confidence(result, c) for c in CLASSES}
        confidence = float(np.mean([per_class[c] for c in focus]))
        details = {
            "classes": result["classes"], "focus": focus, "transitions": result["transitions"][:6],
            "changed_percent": result["changed_percent"], "dates": result["dates"],
            "valid_pixels": result["valid_pixels"], "valid_area_km2": result["valid_area_km2"],
            "methods": result["methods"], "robustness": result["robustness"],
            "season": result["season"], "confidence_per_class": per_class,
            "warnings": result["warnings"], "confidence_basis": "threshold_robustness x season_consistency",
        }
        if len(focus) == 1:
            details["short_answer"] = result["classes"][focus[0]]["direction"]
        answer = answer_text(result, focus)
        model_trace = None
        if "built_up" in focus:
            md = model_direction(ctx, before, after, params["urban_unchanged_tolerance"])
            model_trace = md["trace"]
            if md["direction"]:
                rules = result["classes"]["built_up"]
                agree = md["direction"] == rules["direction"]
                details["built_up_direction"] = {"source": "landcover_model", "model": md["trace"],
                                                 "rules_direction": rules["direction"], "agree": agree}
                if focus == ["built_up"]:
                    details["short_answer"] = md["direction"]
                lead = model_line(md, result["dates"])
                if agree:
                    lead += " The pixel rules agree."
                else:
                    lead += (f" Disagreement: the pixel rules say built-up {VERB[rules['direction']]} "
                             f"({rules['delta_pp']:+.2f} percentage points, area table below); confidence lowered.")
                    confidence *= DISAGREEMENT_PENALTY
                answer = f"{lead}\n{answer}"
        return ToolResult(
            answer=answer,
            confidence=confidence,
            evidence_images=evidence,
            data=details,
            trace={"methods": {k: result["methods"][k] for k in ("water_index", "built_up_index")},
                   "grid": list(result["grid"].shape), "order": [before["slot"], after["slot"]],
                   "warnings": len(result["warnings"]),
                   **({"landcover_model": model_trace} if model_trace else {})},
        )

    def _map(self, ctx, query_id, out_dir, role, f, result):
        classes_map = result["maps"][role]
        name = f"landcover_{role}.png"
        render_overlay([(classes_map == CLASS_CODES[c], COLOURS[c], MAP_ALPHA) for c in CLASSES],
                       result["grid"].shape, out_dir / name)
        return {"id": f"landcover_{role}", "kind": "overlay", "base": f"preview_{f['slot']}",
                "label": f"Land cover {role} ({f.get('date')})", "url": ctx.evidence_url(query_id, name),
                "legend": [{"label": CLASS_LABELS[c], "color": COLOURS[c]} for c in CLASSES]}


def model_direction(ctx, before, after, tolerance):
    """Built-up direction from the scene-level P(urban) delta, or direction=None with the reason."""
    ok, reason = lp.availability()
    if not ok:
        return {"direction": None, "trace": {"used": False, "reason": reason}}
    try:
        model = lp.get_model()
        scores = {}
        for role, f in (("before", before), ("after", after)):
            image, info = lp.prepare_input(ctx.path(f["slot"]), f["metadata"], f["bands"])
            score, n = model.scene_score(image)
            scores[role] = {"p_urban": round(score, 4), "windows": n, "in_distribution": info["in_distribution"],
                            "source_resolution_m": info["source_resolution_m"]}
    except lp.MissingBands as exc:
        return {"direction": None, "trace": {"used": False, "reason": str(exc)}}
    delta = round(scores["after"]["p_urban"] - scores["before"]["p_urban"], 4)
    return {"direction": lc.direction(delta, tolerance), "delta": delta, "tolerance": tolerance, "scores": scores,
            "trace": {"used": True, **model.trace_info, "p_urban": scores, "delta": delta, "tolerance": tolerance}}


def model_line(md, dates):
    t = md["trace"]
    b, a = md["scores"]["before"]["p_urban"], md["scores"]["after"]["p_urban"]
    line = (f"Built-up {VERB[md['direction']]} according to the land-cover model ({t['model']} {t['version']}, "
            f"bands {'/'.join(t['bands'])}): scene P(urban) {b:.2f} on {dates['before']} -> {a:.2f} on "
            f"{dates['after']} ({md['delta']:+.2f}; unchanged within ±{md['tolerance']:g}).")
    if not all(s["in_distribution"] for s in md["scores"].values()):
        line += " Input is not Sentinel-2-like reflectance, so the model is out of its training distribution."
    return line


def _ordered(ctx):
    """(before, after) file entries by date; upload order when dates are missing."""
    files = sorted(ctx.files, key=lambda f: (f.get("date") or "", f["slot"]))
    return files[0], files[1]


def _class_line(label, s, dates, tolerance):
    verb = VERB[s["direction"]]
    line = (f"{label} {verb}: {s['before_percent']:.2f}% on {dates['before']} -> "
            f"{s['after_percent']:.2f}% on {dates['after']} ({s['delta_pp']:+.2f} percentage points")
    if s["delta_km2"] is not None:
        line += f", {s['before_km2']:g} -> {s['after_km2']:g} km², {s['delta_km2']:+g} km²"
    if s["relative_change_percent"] is not None and s["direction"] != lc.UNCHANGED:
        line += f", {s['relative_change_percent']:+.1f}% relative"
    line += ")"
    if s["direction"] == lc.UNCHANGED:
        line += f"; the change is within the ±{tolerance:g} pp tolerance"
    return line + "."


def answer_text(result, focus):
    """Answer built only from the computed (rounded) numbers."""
    dates, tol = result["dates"], result["methods"]["unchanged_tolerance_pp"]
    stats = result["classes"]
    lines = []
    if len(focus) < len(CLASSES):
        for c in focus:
            lines.append(_class_line(CLASS_LABELS[c], stats[c], dates, tol))
    else:
        lines.append(f"Between {dates['before']} and {dates['after']}, {result['changed_percent']:.2f}% "
                     "of the compared area changed land-cover class.")
        for c in sorted(CLASSES, key=lambda c: -abs(stats[c]["delta_pp"])):
            lines.append(_class_line(CLASS_LABELS[c], stats[c], dates, tol))
        top = [t for t in result["transitions"][:3]]
        if top:
            lines.append("Largest transitions: " + "; ".join(
                f"{CLASS_LABELS[t['from']]} -> {CLASS_LABELS[t['to']]} {t['percent']:.2f}%" for t in top) + ".")
    for w in result["warnings"]:
        lines.append(f"Note: {w}")
    return "\n".join(lines)
