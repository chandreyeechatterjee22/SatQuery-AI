"""Task classification: regex rules first, then a fuzzy keyword fallback for typos.

Returns a structured result only (task, method, matched terms, confidence),
never free-text reasoning.
"""
import difflib
import re

METADATA = "metadata"
CAPTION = "caption"
VQA = "vqa"
WATER_BUILTUP = "water_builtup"
CHANGE = "change"
UNKNOWN = "unknown"

TASKS = (METADATA, CAPTION, VQA, WATER_BUILTUP, CHANGE)

# Which upload modes each task can run on.
TASK_MODES = {
    METADATA: {"single", "optical_sar", "bi_temporal"},
    CAPTION: {"single"},
    VQA: {"single"},
    WATER_BUILTUP: {"optical_sar"},
    CHANGE: {"bi_temporal"},
}

# When a task does not fit the mode but another task can answer the same
# question on that upload, reroute instead of rejecting.
REROUTES = {
    (WATER_BUILTUP, "single"): VQA,          # "Is there water?" on one image -> VQA
    (WATER_BUILTUP, "bi_temporal"): CHANGE,  # per-date land cover covers water/built-up
}

# Ordered by priority: the first task whose rules match wins.
_RULES = [
    (CHANGE, [
        r"\bchang\w*", r"\b(increas|decreas)\w*", r"\b(grew|grow\w*|shr[iau]nk\w*|expan\w*)",
        r"\b(loss|lost|gain\w*)\b", r"\b(before|after)\b", r"\bcompar\w*", r"\bdifferen\w*",
        r"\bunchanged\b", r"\bremain\w* (the )?same\b", r"\bbetween (the )?(two )?(dates|images)\b",
    ]),
    (METADATA, [
        r"\bhow many bands\b", r"\bband count\b", r"\bnumber of bands\b", r"\bwhich bands\b",
        r"\bcrs\b", r"\bprojection\b", r"\bepsg\b", r"\bcoordinate (reference )?system\b",
        r"\bresolution\b", r"\bpixel size\b", r"\bgsd\b", r"\bdimensions?\b",
        r"\b(extent|bounds|bounding box|footprint)\b", r"\bdata ?type\b", r"\bdtype\b",
        r"\bmetadata\b", r"\bacquisition date\b", r"\bwhich (sensor|satellite)\b",
    ]),
    (WATER_BUILTUP, [
        r"\bwater\w*", r"\bflood\w*", r"\b(river|lake|reservoir|pond|tank)s?\b", r"\binundat\w*",
        r"\bbuilt[- ]?up\b", r"\burban\w*", r"\bbuildings?\b", r"\bsettlements?\b",
        r"\bimpervious\b", r"\bconcrete\b", r"\bcity\b",
    ]),
    (CAPTION, [
        r"\bdescri(be|ption)\b", r"\bcaption\w*", r"\bsummar(y|i[sz]e)\b", r"\boverview\b",
        r"\bwhat (is|does) (this|the) (image|scene|picture) (show|contain)\w*",
        r"\bwhat('s| is) in (this|the) (image|scene|picture)\b",
    ]),
    (VQA, [
        r"^(is|are|does|do|can|how|what|which|where|why|who|when)\b", r"\?\s*$",
    ]),
]
_COMPILED = [(task, [re.compile(p, re.IGNORECASE) for p in patterns]) for task, patterns in _RULES]

# Fallback vocabulary: single words that point at a task, matched with typo tolerance.
_VOCAB = {
    CHANGE: ["change", "changed", "changes", "increase", "decrease", "compare", "difference",
             "growth", "expansion", "unchanged"],
    METADATA: ["bands", "projection", "resolution", "metadata", "crs", "epsg", "dimensions",
               "extent"],
    WATER_BUILTUP: ["water", "flood", "flooded", "river", "lake", "reservoir", "urban",
                    "buildings", "settlement", "builtup"],
    CAPTION: ["describe", "description", "caption", "summary", "summarize", "overview"],
}
_WORD_TO_TASK = {w: t for t, words in _VOCAB.items() for w in words}
_FUZZY_CUTOFF = 0.8

RULE_CONFIDENCE = 0.95
RULE_CONFLICT_CONFIDENCE = 0.8
GENERIC_QUESTION_CONFIDENCE = 0.6
FUZZY_CONFIDENCE = 0.6


def classify(question):
    """Return {"task", "method", "matched", "confidence", "also_matched"}."""
    text = (question or "").strip()
    hits = []
    for task, patterns in _COMPILED:
        matched = [m.group(0) for p in patterns if (m := p.search(text))]
        if matched:
            hits.append((task, matched))

    if hits:
        task, matched = hits[0]
        others = [t for t, _ in hits[1:] if t != VQA]
        if task == VQA:
            confidence = GENERIC_QUESTION_CONFIDENCE
        else:
            confidence = RULE_CONFLICT_CONFIDENCE if others else RULE_CONFIDENCE
        return _result(task, "rules", matched, confidence, others)

    fuzzy = _fuzzy(text)
    if fuzzy:
        task, matched = fuzzy
        return _result(task, "fuzzy_keywords", matched, FUZZY_CONFIDENCE)
    return _result(UNKNOWN, "none", [], 0.0)


def route(task, mode):
    """Map (task, mode) to the task that will actually run, or None if it cannot.

    Returns (task_to_run, rerouted_from or None).
    """
    if task in TASK_MODES and mode in TASK_MODES[task]:
        return task, None
    target = REROUTES.get((task, mode))
    if target:
        return target, task
    return None, None


def tasks_for_mode(mode):
    return [t for t in TASKS if mode in TASK_MODES[t]]


def _fuzzy(text):
    votes = {}
    for word in re.findall(r"[a-z]+", text.lower().replace("-", "")):
        if len(word) < 4:
            continue
        close = difflib.get_close_matches(word, _WORD_TO_TASK, n=1, cutoff=_FUZZY_CUTOFF)
        if close:
            votes.setdefault(_WORD_TO_TASK[close[0]], []).append(f"{word}~{close[0]}")
    if not votes:
        return None
    priority = [t for t, _ in _RULES]
    task = min(votes, key=lambda t: (-len(votes[t]), priority.index(t)))
    return task, votes[task]


def _result(task, method, matched, confidence, also_matched=None):
    return {"task": task, "method": method, "matched": matched,
            "confidence": confidence, "also_matched": also_matched or []}
