"""Indian states / union territories and their districts, from data/india_locations.json.

The file is generated once by scripts/build_india_locations.py (geoBoundaries, see its "source"
block) and read from disk; no Earth Engine or internet access is needed at runtime.
"""
import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "india_locations.json"


@lru_cache(maxsize=1)
def _data():
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    states = {}
    for s in data["states"]:
        districts = {d["name"]: d for d in s["districts"]}
        states[s["name"]] = {**s, "districts": districts}
    return {"source": data["source"], "states": states}


def state_names():
    """All states and UTs, alphabetical."""
    return list(_data()["states"])


def get_state(name):
    return _data()["states"].get(name)


def district_names(state):
    """Districts of ``state``, alphabetical, or None if the state is unknown."""
    s = get_state(state)
    return None if s is None else list(s["districts"])


def major_cities(state):
    s = get_state(state)
    return None if s is None else s["major_cities"]


def resolve(state, area):
    """District record for ``area`` (current name or an alias such as "Bangalore"), or None."""
    s = get_state(state)
    if s is None:
        return None
    name = area if area in s["districts"] else s["aliases"].get(area)
    return None if name is None else {"name": name, **s["districts"][name]}
