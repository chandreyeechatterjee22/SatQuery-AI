"""RSVQA question types and answer helpers, shared by the runtime and ml/vqa_head.

Types follow RSVQA-LR: presence, comp (comparison), count, rural_urban.
"""
import re

PRESENCE, COMP, COUNT, RURAL_URBAN, OTHER = "presence", "comp", "count", "rural_urban", "other"
TYPES = (PRESENCE, COMP, COUNT, RURAL_URBAN)

_RURAL_URBAN = re.compile(r"\brural\b.*\burban\b|\burban\b.*\brural\b", re.I)
_COMP = re.compile(r"\b(more|less|fewer|greater|smaller|larger)\b.*\bthan\b|\bequal to\b"
                   r"|\bas many\b|\bsame (number|amount)\b", re.I)
_COUNT = re.compile(r"\b(how many|number of|amount of|count)\b", re.I)
_PRESENCE = re.compile(r"^\s*(is|are) there\b|\b(is|are)\b.+\bpresent\b|^\s*(does|do) .+\b(contain|have)\b",
                       re.I)

# Object extraction for presence questions, e.g. "Is there a small water area?"
_PRESENCE_OBJECT = [
    re.compile(r"^\s*(?:is|are) there\s+(?:(?:a|an|any|some)\s+)?(?P<obj>.+?)\s*(?:in the image)?\s*\??\s*$",
               re.I),
    re.compile(r"^\s*(?:is|are)\s+(?:(?:a|an|any|some|the)\s+)?(?P<obj>.+?)\s+present\b.*$", re.I),
    re.compile(r"^\s*(?:does|do) (?:the|this) (?:image|area|scene) (?:contain|have)\s+"
               r"(?:(?:a|an|any|some)\s+)?(?P<obj>.+?)\s*\??\s*$", re.I),
]


def question_type(question):
    """Detect the RSVQA question type from wording (comparison beats count)."""
    q = question or ""
    if _RURAL_URBAN.search(q):
        return RURAL_URBAN
    if _COMP.search(q):
        return COMP
    if _COUNT.search(q):
        return COUNT
    if _PRESENCE.search(q):
        return PRESENCE
    return OTHER


def presence_object(question):
    """The thing asked about in a presence question, or None."""
    for pattern in _PRESENCE_OBJECT:
        m = pattern.match(question or "")
        if m:
            obj = re.sub(r"\s+", " ", m.group("obj")).strip(" ?.")
            return obj or None
    return None


def count_bin(answer):
    """RSVQA paper convention for LR counts: 0, 1-10, 11-100, 101-1000, >1000."""
    try:
        n = int(answer)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return "0"
    if n <= 10:
        return "1-10"
    if n <= 100:
        return "11-100"
    if n <= 1000:
        return "101-1000"
    return ">1000"
