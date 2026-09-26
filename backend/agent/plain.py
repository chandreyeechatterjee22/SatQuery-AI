"""Plain-language answers: templates filled only from the controller's response.

``explain(response, ctx)`` returns the ``plain`` block shown first in the UI:

    headline          one short sentence that answers the question
    what_it_means     2-4 everyday sentences
    key_numbers       2-4 bullets in friendly units (km² only when the images have map location)
    how_we_know       1-2 sentences on the method, without jargon
    confidence        {"level": High/Medium/Low/Not rated, "reason", "text"}
    caveats           plain warnings, only when they apply
    next_step         one suggested follow-up question (or None)

No language model is involved and nothing is added that the tool did not compute:
every number is the tool's own number (percentages at the tool's precision, km² rounded
to 0.01), and every direction word is the tool's direction. The technical ``answer`` is
left untouched for the technical details and for the batch CLI.
"""
import re
from datetime import date

import settings
from local_analysis.landcover_change import direction as lc_direction
from models import rsvqa
from raster.band_adapter import PHOTO_DRIVERS

HIGH, MEDIUM, LOW, NOT_RATED = "High", "Medium", "Low", "Not rated"

# Words that must never appear in plain fields (checked by the tests).
BANNED_TERMS = [
    "dB", "P(urban)", "pp", "percentage point", "VV", "VH", "HH", "HV", "NDWI", "MNDWI", "NDBI", "NDVI",
    "SWIR", "SWIR1", "SWIR2", "NIR", "sigma0", "backscatter", "softmax", "EPSG", "CRS", "p90", "dtype",
    "rs_vqa", "rs_caption", "optical_sar_mapper", "landcover_change", "image_metadata", "trained_head",
    "zero_shot", "RemoteCLIP", "resnet18", "BigEarthNet", "RSVQA", "threshold", "modality", "modalities",
]

CLASS_WORDS = {
    "water": "water",
    "built_up": "built-up area (buildings and roads)",
    "vegetation": "vegetation (plants, trees and crops)",
    "other": "other land (anything that is not water, plants or buildings)",
}
CLASS_SHORT = {"water": "Water", "built_up": "Built-up", "vegetation": "Vegetation", "other": "Other land"}
CHANGE_VERB = {"increased": "has increased", "decreased": "has decreased", "unchanged": "has stayed about the same"}
BECAME = {  # "more of this area became ..." phrasing for increases / decreases
    "water": ("more of this area was covered by water", "less of this area was covered by water"),
    "built_up": ("more of this area became buildings and roads", "less of this area looked like buildings and roads"),
    "vegetation": ("more of this area was covered by plants", "less of this area was covered by plants"),
    "other": ("more of this area was other land", "less of this area was other land"),
}

EXAMPLE_NEXT = {
    "single": "Describe this image",
    "optical_sar": "Map water and built-up areas",
    "bi_temporal": "What changed?",
}


# ----------------------------------------------------------------------------- entry point

def explain(response, ctx):
    """Plain block for a controller response. Never raises: falls back to a minimal block."""
    try:
        return _explain(response, ctx)
    except Exception:  # a template problem must never break the answer itself
        return _block(
            headline="We have an answer, but could not write a simple summary for it.",
            what_it_means="Open 'Technical details' below to see the full answer.",
            how_we_know="The technical details show exactly what was computed.",
            confidence=_confidence(response.get("confidence"), "see the technical details for how it was measured."),
        )


def _explain(response, ctx):
    status = response["status"]
    if status == "NOT_AVAILABLE":
        return _not_available(response, ctx)
    if status == "REJECTED":
        return _rejected(response, ctx)
    if status != "OK":
        return _block(
            headline="Something went wrong while answering.",
            what_it_means="The analysis stopped with an error before it could finish. Nothing was measured.",
            how_we_know="The error is recorded in 'Technical details'.",
            confidence=_not_rated("no answer was produced."),
            next_step=EXAMPLE_NEXT.get(ctx.mode),
        )
    tool = response["trace"]["tool"]
    builder = {"rs_vqa": _vqa, "rs_caption": _caption, "image_metadata": _metadata,
               "optical_sar_mapper": _optical_sar, "landcover_change": _change}.get(tool)
    if builder is None:
        raise ValueError(f"no plain template for {tool}")
    return builder(response, ctx)


# ----------------------------------------------------------------------------- helpers

def _block(headline, what_it_means, how_we_know, confidence, key_numbers=None, caveats=None, next_step=None):
    return {"headline": headline, "what_it_means": what_it_means, "key_numbers": key_numbers or [],
            "how_we_know": how_we_know, "confidence": confidence, "caveats": caveats or [],
            "next_step": next_step}


def level_for(value):
    """High / Medium / Low from a 0..1 confidence, using the configured cut-offs."""
    if value is None:
        return NOT_RATED
    high, medium = settings.plain_confidence_thresholds()
    if value >= high:
        return HIGH
    return MEDIUM if value >= medium else LOW


def _confidence(value, reason):
    level = level_for(value)
    return {"level": level, "reason": reason, "text": f"{level} — {reason}"}


def _not_rated(reason):
    return {"level": NOT_RATED, "reason": reason, "text": f"{NOT_RATED} — {reason}"}


def pct(value):
    """A percentage exactly as the tool reported it (2 decimals)."""
    return f"{value:.2f}%"


def about_pct(value):
    """A percentage in running text: 1 decimal."""
    return f"about {value:.1f}%"


def km2(value):
    """An area in friendly units: km² with 2 decimals, or m² for areas under 0.1 km²."""
    if value is None:
        return None
    if abs(value) < 0.1:
        return f"{value * 1e6:,.0f} m²"
    return f"{value:.2f} km²"


def chance(p):
    return f"{round(p * 100):d}%"


def nice_date(iso):
    try:
        return date.fromisoformat(str(iso)).strftime("%d %b %Y").lstrip("0")
    except (TypeError, ValueError):
        return str(iso)


def _is_photo(f):
    return f["metadata"].get("driver") in PHOTO_DRIVERS or not f["metadata"].get("georeferenced", True)


def _photo_caveat(ctx, has_area=True):
    if any(_is_photo(f) for f in ctx.files):
        return "These are photos (or images without map location), so we can't measure real areas — sizes are given in pixels instead."
    if not has_area:
        return "The images have no usable ground scale, so we can't measure real areas — sizes are given in pixels instead."
    return None


def _join(parts):
    return " ".join(p for p in parts if p)


# ----------------------------------------------------------------------------- single image: VQA

def _vqa(response, ctx):
    d = response["details"]
    answer = str(response["answer"])
    p = response["confidence"]
    qtype = d.get("question_type")
    question = response["question"]
    top = d.get("top_answers") or []
    answered_by = d.get("answered_by")

    if qtype == rsvqa.RURAL_URBAN:
        headline = f"This looks like {'a rural area (countryside)' if answer == 'rural' else 'an urban area (a town or city)'}."
        meaning = [f"Our AI model looked at the whole image and decided whether it shows countryside or a town or city. "
                   f"It chose \"{answer}\"."]
    elif qtype == rsvqa.PRESENCE and answer in ("yes", "no"):
        obj = rsvqa.presence_object(question)
        if obj:
            headline = (f"Yes — the model found {obj} in this image." if answer == "yes"
                        else f"No — the model did not find {obj} in this image.")
        else:
            headline = f"{answer.capitalize()} — that is the model's answer to your question."
        meaning = ["Our AI model checked the image for what you asked about and answered "
                   f"\"{answer}\"."]
    elif qtype == rsvqa.COUNT:
        headline = f"The model estimates a count of about {answer}."
        meaning = [f"Our AI model estimated the number you asked about as {answer}. "
                   "It gives a rough count for the whole image, not an exact tally of each object."]
    elif answer in ("yes", "no"):
        headline = f"{answer.capitalize()} — that is the model's answer to your question."
        meaning = [f"Our AI model compared what you asked about in the image and answered \"{answer}\"."]
    else:
        headline = f"The model's answer is \"{answer}\"."
        meaning = [f"Our AI model looked at the image and your question and answered \"{answer}\"."]

    if len(top) > 1:
        others = ", ".join(f"\"{t['answer']}\" {chance(t['probability'])}" for t in top[1:3])
        meaning.append(f"It gave this answer a {chance(p)} chance; other answers it considered: {others}.")
    else:
        meaning.append(f"It gave this answer a {chance(p)} chance.")

    key_numbers = [f"Answer: {answer}", f"Model's certainty: {chance(p)}"]
    key_numbers += [f"Next most likely: \"{t['answer']}\" ({chance(t['probability'])})" for t in top[1:2]]

    how = ("An AI model trained on thousands of satellite images with questions and answers looked at this image "
           "together with your question and picked the most likely answer." if answered_by == "trained_head" else
           "An AI model that matches pictures with short descriptions compared this image with descriptions of "
           "each possible answer and picked the closest one.")
    reason = (f"the model gave this answer a {chance(p)} chance." if level_for(p) != LOW
              else f"the model was unsure; it gave this answer only a {chance(p)} chance.")
    caveats = []
    if any("no map scale" in w for w in d.get("warnings", [])):
        caveats.append("This image has no map scale, and the model learned to count on images of a fixed size, "
                       "so treat the number as a rough guess.")
    next_step = "Describe this image" if qtype == rsvqa.RURAL_URBAN else "Is it a rural or an urban area?"
    return _block(headline, " ".join(meaning), how, _confidence(p, reason), key_numbers, caveats, next_step)


# ----------------------------------------------------------------------------- single image: caption

def _caption(response, ctx):
    scores = response["details"].get("scene_scores") or []
    p = response["confidence"]
    best = scores[0] if scores else {"label": str(response["answer"]), "probability": p or 0}
    headline = f"This looks like {best['label']}."
    meaning = [f"Our AI model compared the image with a list of common kinds of places seen from space. "
               f"The best match was {best['label']} ({chance(best['probability'])} match)."]
    if len(scores) > 1:
        meaning.append("Other possible matches: " + ", ".join(
            f"{s['label']} ({chance(s['probability'])})" for s in scores[1:]) + ".")
    key_numbers = [f"{s['label'][0].upper() + s['label'][1:]}: {chance(s['probability'])} match" for s in scores[:4]]
    how = ("We compared the picture with short descriptions of common scenes (such as farmland, airports or rivers) "
           "and ranked how well each one fits.")
    if level_for(p) == HIGH:
        reason = f"the best match is clear ({chance(p)})."
    else:
        reason = f"the best match got only {chance(p)}, so other kinds of place are also possible."
    return _block(headline, " ".join(meaning), how, _confidence(p, reason), key_numbers, [],
                  "Is it a rural or an urban area?")


# ----------------------------------------------------------------------------- metadata

_LAYER_WORDS = {"blue": "blue", "green": "green", "red": "red", "nir": "near-infrared",
                "rededge1": "red-edge", "rededge2": "red-edge", "rededge3": "red-edge", "nir2": "near-infrared",
                "swir1": "short-wave infrared", "swir2": "short-wave infrared", "vv": "radar", "vh": "radar",
                "hh": "radar", "hv": "radar"}
_DTYPE_WORDS = {"uint8": "8-bit whole numbers", "uint16": "16-bit whole numbers", "int16": "16-bit whole numbers",
                "uint32": "32-bit whole numbers", "int32": "32-bit whole numbers",
                "float32": "decimal numbers", "float64": "decimal numbers"}


def _layers(f):
    kinds = []
    for role in f["bands"].get("roles", {}):
        word = _LAYER_WORDS.get(role, "other")
        if word not in kinds:
            kinds.append(word)
    return kinds


def _metadata(response, ctx):
    fields = response["details"].get("fields") or []
    many = len(ctx.files) > 1
    key_numbers, meaning, caveats = [], [], []
    for f in ctx.files:
        facts = _file_facts(f, fields)
        if f["bands"].get("source") not in ("descriptions", "sensor_hint", "user_roles") and "bands" in fields:
            caveats.append("We guessed which layer is which colour from the number of layers. "
                           "If that is wrong, set them under 'Advanced' when uploading.")
        if len(facts) < 2 and not many:
            facts.append(("Placed on a map", "yes" if f["metadata"].get("georeferenced") else "no"))
        prefix = f"Image {f['slot']} " if many else ""
        key_numbers += [f"{prefix}{label.lower() if prefix else label}: {value}" for label, value in facts]
        meaning.append(f"{'Image ' + str(f['slot']) if many else 'Your image'}: "
                       + "; ".join(_phrase(label, value) for label, value in facts) + ".")
    pair = ctx.manifest.get("pair") or {}
    if many and pair.get("overlap_fraction") is not None and ("bounds" in fields or "crs" in fields):
        key_numbers.append(f"The two images overlap by {pair['overlap_fraction']:.0%}")
    headline = "Here are the basic facts about your images." if many else "Here are the basic facts about your image."
    return _block(headline, " ".join(meaning[:4]),
                  "We read these facts directly from the information stored inside the file.",
                  _confidence(response["confidence"], "these facts are read straight from the file."),
                  key_numbers[:4], list(dict.fromkeys(caveats)), EXAMPLE_NEXT.get(ctx.mode))


def _phrase(label, value):
    if label == "Layers":
        count, _, rest = value.partition(" ")
        return f"{count} layer{'' if count == '1' else 's'}{' ' + rest if rest else ''}"
    return f"{label.lower()} {value}"


def _file_facts(f, fields):
    """(label, value) pairs in everyday words for the metadata fields asked about."""
    meta, r = f["metadata"], f["metadata"]["resolution"]
    metres = r.get("units") == "metres"
    facts = []
    if "bands" in fields:
        kinds = _layers(f)
        what = (" (radar)" if kinds == ["radar"] else f" ({', '.join(kinds)} light)" if kinds else "")
        facts.append(("Layers", f"{meta['band_count']}{what}"))
    if "resolution" in fields:
        facts.append(("Each pixel covers", f"{r['x']:g} × {r['y']:g} m on the ground" if metres
                      else "no ground scale (the pixel size is not in metres)"))
    if "size" in fields:
        size = f"{meta['width']} × {meta['height']} pixels"
        if metres:
            size += f" (about {meta['width'] * r['x'] / 1000:.1f} × {meta['height'] * r['y'] / 1000:.1f} km)"
        facts.append(("Image size", size))
    if "crs" in fields or "bounds" in fields:
        facts.append(("Placed on a map", "yes" if meta.get("georeferenced") else "no"))
    if "date" in fields:
        facts.append(("Date", nice_date(f["date"]) if f.get("date") else "not given"))
    if "dtype" in fields:
        facts.append(("Stored as", " and ".join(sorted({_DTYPE_WORDS.get(t, t) for t in meta["dtypes"]}))))
    if "sensor" in fields:
        facts.append(("Kind of image", "radar" if f["kind"] == "sar" else "optical (camera-like)"))
    return facts


# ----------------------------------------------------------------------------- optical + SAR

_OPTSAR_CAVEATS = [
    ("do not look like calibrated", "The radar image may not be properly calibrated, so its results may be off."),
    ("low-NDVI proxy", "The normal image is missing one infrared layer, so bare soil may be counted as buildings. "
                       "The radar image matters more here."),
    ("water is detected by SAR only", "The normal image lacks the colours needed for water, so only the radar image was used for water."),
    ("built-up is detected by SAR only", "The normal image lacks the colours needed for buildings, so only the radar image was used for buildings."),
    ("SAR is not used", "The radar image has no usable radar layer, so only the normal image was used."),
]


def _translate(warnings, table):
    out = []
    for w in warnings:
        for needle, text in table:
            if needle in w:
                out.append(text)
                break
        else:
            out.append("There is an extra technical note about this result; see 'Technical details'.")
    return list(dict.fromkeys(out))


def _optical_sar(response, ctx):
    d = response["details"]
    stats = d["classes"]
    area = d.get("valid_area_km2")
    fusion_and = d["methods"].get("fusion") == "and"
    classes = [c for c in ("water", "built_up") if c in stats]
    measured = [c for c in classes if stats[c]["percent"] is not None]

    def size(c):
        s = stats[c]
        return km2(s["area_km2"]) if area is not None and s["area_km2"] is not None else f"{s['pixels']:,} pixels"

    words = {"water": "water", "built_up": "built-up (buildings and roads)"}
    if measured:
        headline = "About " + " and ".join(f"{stats[c]['percent']:.1f}% of the area is {words[c]}" for c in measured) + "."
    else:
        headline = "We couldn't measure water or buildings with these two images."

    scope = f"the {km2(area)} both images cover" if area is not None else f"the {d['valid_pixels']:,} pixels both images cover"
    meaning = [f"We looked for {' and '.join(words[c] for c in classes)} in {scope}."]
    for c in measured:
        meaning.append(f"{CLASS_SHORT[c]} covers {size(c)} ({about_pct(stats[c]['percent'])}).")
    meaning.append("A spot only counts when both the normal image and the radar image agree." if fusion_and
                   else "A spot counts when either the normal image or the radar image detects it.")

    key_numbers = [f"{CLASS_SHORT[c]}: {pct(stats[c]['percent'])} of the area ({size(c)})" for c in measured]
    both = [c for c in measured if stats[c]["both_percent"] is not None]
    for c in both[:2]:
        s = stats[c]
        key_numbers.append(f"{CLASS_SHORT[c]} found by the normal image {pct(s['optical_percent'])}, by radar "
                           f"{pct(s['sar_percent'])}, by both {pct(s['both_percent'])}")
    key_numbers = key_numbers[:4]

    how = []
    how.append("We used two kinds of satellite image: a normal (optical) image that records sunlight reflected "
               "from the ground, and a radar (SAR) image that records how the surface bounces back radar signals.")
    tips = []
    if "water" in classes:
        tips.append("calm water looks dark to radar")
    if "built_up" in classes:
        tips.append("buildings reflect radar strongly")
    if tips:
        how.append(f"{'; '.join(tips).capitalize()}, and the normal image adds colour clues.")

    agreements = [(c, stats[c]["agreement"]) for c in measured if stats[c]["agreement"] is not None]
    p = response["confidence"]
    if not agreements:
        confidence = _not_rated("only one of the two images could be used, so there is nothing to cross-check.")
    else:
        worst_c, worst = min(agreements, key=lambda t: t[1])
        if level_for(p) == HIGH:
            reason = "the radar and the normal image mostly agree on what they found."
        else:
            reason = (f"the radar and the normal image agree on only {chance(worst)} of the "
                      f"{'water' if worst_c == 'water' else 'built-up'} spots they found.")
        confidence = _confidence(p, reason)

    caveats = _translate(d.get("warnings", []), _OPTSAR_CAVEATS)
    photo = _photo_caveat(ctx, area is not None)
    if photo:
        caveats.insert(0, photo)
    only_one = [c for c in measured if stats[c]["both_percent"] is None]
    for c in only_one:
        by = "normal image" if stats[c]["optical_percent"] is not None else "radar image"
        caveats.append(f"{CLASS_SHORT[c]} was found by the {by} only, so it could not be cross-checked.")
    next_step = ("How much of the area is built-up?" if classes == ["water"] else
                 "Where is the water?" if classes == ["built_up"] else "What is the resolution of each image?")
    return _block(headline, _join(meaning[:4]), _join(how), confidence, key_numbers,
                  list(dict.fromkeys(caveats)), next_step)


# ----------------------------------------------------------------------------- change

_CHANGE_CAVEATS = [
    ("differ in overall greenness",
     "The two images differ in how green the land is (for example a dry year versus a wet year). Dry bare fields can "
     "look like buildings, so some of this change may be season or rainfall rather than real change. "
     "Images from the same season give a fairer comparison."),
    ("No SWIR band", "One infrared layer is missing on at least one date, so bare soil may be counted as buildings."),
    ("only present on one date", "Some image layers exist on only one of the dates and were not used."),
]


def _direction(d, c):
    """(final direction, rules direction, model info or None) for class c."""
    rules = d["classes"][c]["direction"]
    bd = d.get("built_up_direction")
    if c == "built_up" and bd:
        md = bd["model"]
        before, after = md["p_urban"]["before"]["p_urban"], md["p_urban"]["after"]["p_urban"]
        final = lc_direction(md["delta"], md["tolerance"])  # the model's direction, as the tool reports it
        return final, rules, {"before": before, "after": after, "agree": bd["agree"], "md": md}
    return rules, rules, None


def _change(response, ctx):
    d = response["details"]
    focus = d["focus"]
    dates = d["dates"]
    b, a = nice_date(dates["before"]), nice_date(dates["after"])
    has_km2 = d.get("valid_area_km2") is not None
    stats = d["classes"]

    def amount(s, when):
        return km2(s[f"{when}_km2"]) if has_km2 else f"{s[f'{when}_pixels']:,} pixels"

    key_numbers, meaning = [], []
    model_info = None
    if len(focus) == 1:
        c = focus[0]
        s = stats[c]
        final, rules, model_info = _direction(d, c)
        if model_info and not model_info["agree"]:
            headline = f"The {CLASS_WORDS[c].split(' (')[0]} probably {final}, but our two methods disagree."
        elif final == "unchanged":
            headline = f"No — the {CLASS_WORDS[c].split(' (')[0]} has stayed about the same."
        else:
            headline = f"Yes — the {CLASS_WORDS[c].split(' (')[0]} {CHANGE_VERB[final]}."
        if model_info and not model_info["agree"]:
            meaning.append(_model_story(model_info, b, a))
            meaning.append(f"But a simple count of building-like spots went the other way: about "
                           f"{s['before_percent']:.1f}% of the area on {b} and about {s['after_percent']:.1f}% on {a}.")
            meaning.append("Because the two methods disagree, treat this answer as uncertain.")
        else:
            meaning.append(_class_story(c, s, rules, b, a))
            if model_info:
                meaning.append(_model_story(model_info, b, a))
        key_numbers.append(f"{CLASS_SHORT[c]}: {pct(s['before_percent'])} → {pct(s['after_percent'])} of the area"
                           + (f" ({amount(s, 'before')} → {amount(s, 'after')})" if has_km2 else ""))
        if model_info:
            key_numbers.append(f"How city-like the scene looks to our AI model: {round(model_info['before'] * 100)} → "
                               f"{round(model_info['after'] * 100)} out of 100")
        key_numbers.append(f"Area compared: {km2(d['valid_area_km2'])}" if has_km2
                           else f"Area compared: {d['valid_pixels']:,} pixels")
    else:
        headline = f"About {d['changed_percent']:.1f}% of the area changed between {b} and {a}."
        ranked = sorted(focus, key=lambda c: -abs(stats[c]["delta_pp"]))
        for c in ranked[:2]:
            final, rules, info = _direction(d, c)
            model_info = model_info or info
            meaning.append(_class_story(c, stats[c], rules, b, a))
        for c in ranked[:3]:
            s = stats[c]
            key_numbers.append(f"{CLASS_SHORT[c]}: {pct(s['before_percent'])} → {pct(s['after_percent'])} of the area"
                               + (f" ({amount(s, 'before')} → {amount(s, 'after')})" if has_km2 else ""))
        key_numbers.append(f"Share of the area that changed: {pct(d['changed_percent'])}")
        top = (d.get("transitions") or [None])[0]
        if top:
            meaning.append(f"The biggest shift was {CLASS_SHORT[top['from']].lower()} turning into "
                           f"{CLASS_SHORT[top['to']].lower()} ({about_pct(top['percent'])} of the area).")

    how = ["We compared the satellite images from both dates and sorted every spot into water, plants, "
           "buildings and roads, or other land, based on how each surface reflects different colours of light."]
    if model_info:
        how.append("For buildings we also asked an AI model, trained on thousands of labelled satellite images, "
                   "how city-like each image looks.")

    p = response["confidence"]
    season_gap = any("differ in overall greenness" in w for w in d.get("warnings", []))
    if model_info and not model_info["agree"]:
        reason = "the two methods we used don't agree."
    elif season_gap:
        reason = "the images differ in how green the land is, which can affect the result."
    elif level_for(p) == HIGH:
        reason = ("the result stays the same when we adjust our detection settings"
                  + (", and both methods agree." if model_info else "."))
    else:
        reason = "the result changes when we adjust our detection settings slightly."
    caveats = _translate(d.get("warnings", []), _CHANGE_CAVEATS)
    if model_info and not all(v["in_distribution"] for v in model_info["md"]["p_urban"].values()):
        caveats.append("These images don't look like the satellite images our AI model learned from, "
                       "so its opinion is less reliable.")
    photo = _photo_caveat(ctx, has_km2)
    if photo:
        caveats.insert(0, photo)
    next_step = "What changed?" if len(focus) == 1 else "Has built-up area increased, decreased or remained unchanged?"
    return _block(headline, _join(meaning[:4]), _join(how), _confidence(p, reason), key_numbers[:4],
                  caveats, next_step)


def _class_story(c, s, direction, b, a):
    before, after = about_pct(s["before_percent"]), about_pct(s["after_percent"])
    name = CLASS_SHORT[c].lower()
    if direction == "unchanged":
        return (f"Between {b} and {a}, the {name} share stayed about the same: {before} of the area before "
                f"and {after} after.")
    more, less = BECAME[c]
    return (f"Between {b} and {a}, {more if direction == 'increased' else less}. "
            f"About {s['before_percent']:.1f}% of the area was {name} before; now it's about {s['after_percent']:.1f}%.")


def _model_story(info, b, a):
    before, after = round(info["before"] * 100), round(info["after"] * 100)
    trend = "more" if after > before else "less" if after < before else "equally"
    if trend == "equally":
        return f"Our AI model sees the scene as equally city-like on both dates ({before} out of 100)."
    return f"Our AI model sees the scene as {trend} city-like on {a} than on {b} ({before} → {after} out of 100)."


# ----------------------------------------------------------------------------- not available / rejected

_NA_CASES = [
    (("SAR image is a photo", "does not contain calibrated backscatter"),
     "The radar image is an ordinary picture, not real radar measurements, so we can't measure water or buildings from it.",
     "Upload a real Sentinel-1 radar file (GeoTIFF), or use 'Fetch from Earth Engine' to get one automatically."),
    (("optical image is a photo",),
     "The normal image is a plain photo with only red, green and blue. Finding water and buildings also needs "
     "infrared light, which ordinary photos don't record.",
     "Upload a Sentinel-2 or Cartosat-2S image (GeoTIFF), or use 'Fetch from Earth Engine'."),
    (("needs multispectral images",),
     "Comparing land cover needs images with infrared light as well as colour, and these images don't have it.",
     "Upload two Sentinel-2 images (GeoTIFF) of the same place, or use 'Fetch from Earth Engine' with 'Two dates'."),
    (("cannot answer", "could not find what the presence question asks about"),
     "Our AI model can't answer this kind of question on this server yet.",
     "Try 'Describe this image' or 'Is it a rural or an urban area?'."),
    (("not installed", "No module named", "torch", "open_clip", "checkpoint", "weights", "failed to load", "not found"),
     "The AI model needed for this question isn't installed on this server.",
     "Ask whoever runs the server to run the model download script (see docs/DEMO.md). "
     "Meanwhile you can ask about the image's basic facts, such as its size or date."),
]


def _not_available(response, ctx):
    text = str(response["answer"])
    what, nxt = ("The tool needed for this question isn't available right now.",
                 "Try a different question, or check 'Technical details' for the reason.")
    for needles, w, n in _NA_CASES:
        if any(k.lower() in text.lower() for k in needles):
            what, nxt = w, n
            break
    return _block("We can't answer this question with these images or on this server.", what,
                  "Nothing was measured, so no numbers are shown. The exact reason is in 'Technical details'.",
                  _not_rated("no answer was produced."), next_step=nxt)


def _rejected(response, ctx):
    text = str(response["answer"])
    example = EXAMPLE_NEXT.get(ctx.mode)
    if text.startswith("I could not tell"):
        return _block("We couldn't tell what you're asking.",
                      "The question didn't match any kind of analysis we can run on this upload.",
                      "We match the words in your question against the kinds of questions each tool can answer.",
                      _not_rated("no answer was produced."), next_step=example)
    if text.startswith("This question needs"):
        needs = {"change": "two images of the same place from different dates",
                 "water_builtup": "a normal image plus a radar image of the same place",
                 "caption": "a single image", "vqa": "a single image"}.get(response["trace"].get("task"),
                                                                             "a different kind of upload")
        return _block("This question doesn't fit the images you uploaded.",
                      f"To answer it we need {needs}. You can upload those, or ask a question that fits this upload.",
                      "Each kind of question needs a matching set of images.",
                      _not_rated("no answer was produced."), next_step=example)
    return _block("We couldn't run this question with the settings given.",
                  "One of the settings for this analysis was not accepted. The exact problem is in 'Technical details'.",
                  "Every setting is checked against a list of allowed values before anything runs.",
                  _not_rated("no answer was produced."), next_step=example)


def contains_banned(text):
    """Banned jargon terms found in ``text`` (whole words, case-sensitive for short acronyms)."""
    found = []
    for term in BANNED_TERMS:
        flags = 0 if len(term) <= 4 or term.isupper() else re.IGNORECASE
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", text, flags):
            found.append(term)
    return found
