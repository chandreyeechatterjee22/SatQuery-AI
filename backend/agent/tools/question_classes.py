"""Which land-cover classes a question mentions (used to fill tool params)."""
import re

_CLASS_PATTERNS = {
    "water": r"\b(water\w*|flood\w*|rivers?|lakes?|reservoirs?|ponds?|inundat\w*)",
    "built_up": r"\b(built[- ]?up|urban\w*|buildings?|settlements?|impervious|concrete|city)\b",
    "vegetation": r"\b(vegetat\w*|green\w*|forests?|trees?|crops?|farm\w*|agricultur\w*)",
}


def classes_in(question, allowed):
    found = [c for c, p in _CLASS_PATTERNS.items()
             if c in allowed and re.search(p, question, re.IGNORECASE)]
    return found or list(allowed)
