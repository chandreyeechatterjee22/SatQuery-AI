"""Validate tool parameters against the tool's allow-list.

A schema maps each allowed parameter name to a spec:
    {"type": "enum", "choices": [...], "default": ...}
    {"type": "enum_list", "choices": [...], "min_items": 1, "default": [...]}
    {"type": "str", "max_length": 500, "default": ...}
    {"type": "int" | "float", "min": ..., "max": ..., "default": ...}
    {"type": "bool", "default": ...}
Unknown names, wrong types and out-of-range values are all rejected.
"""


def validate_params(schema, params):
    """Return (clean_params, errors). Defaults fill in parameters not given."""
    params = dict(params or {})
    errors = [f"'{name}' is not an allowed parameter for this tool "
              f"(allowed: {', '.join(sorted(schema)) or 'none'})"
              for name in sorted(set(params) - set(schema))]
    clean = {}
    for name, spec in schema.items():
        if name not in params:
            if "default" in spec:
                clean[name] = spec["default"]
            elif spec.get("required"):
                errors.append(f"'{name}' is required")
            continue
        value, error = _check(name, spec, params[name])
        if error:
            errors.append(error)
        else:
            clean[name] = value
    return clean, errors


def _check(name, spec, value):
    kind = spec["type"]
    if kind == "enum":
        if value not in spec["choices"]:
            return None, f"'{name}' must be one of {spec['choices']}, got {value!r}"
        return value, None
    if kind == "enum_list":
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            return None, f"'{name}' must be a list of strings"
        bad = [v for v in value if v not in spec["choices"]]
        if bad:
            return None, f"'{name}' has values not in {spec['choices']}: {bad}"
        deduped = list(dict.fromkeys(value))
        if len(deduped) < spec.get("min_items", 0):
            return None, f"'{name}' needs at least {spec['min_items']} item(s)"
        return deduped, None
    if kind == "str":
        if not isinstance(value, str):
            return None, f"'{name}' must be a string"
        if len(value) > spec.get("max_length", 1000):
            return None, f"'{name}' is longer than {spec.get('max_length', 1000)} characters"
        return value, None
    if kind in ("int", "float"):
        ok_types = (int,) if kind == "int" else (int, float)
        if isinstance(value, bool) or not isinstance(value, ok_types):
            return None, f"'{name}' must be a{'n' if kind == 'int' else ''} {kind}"
        if "min" in spec and value < spec["min"] or "max" in spec and value > spec["max"]:
            return None, f"'{name}' must be between {spec.get('min')} and {spec.get('max')}"
        return value, None
    if kind == "bool":
        if not isinstance(value, bool):
            return None, f"'{name}' must be true or false"
        return value, None
    raise ValueError(f"unknown param type {kind!r} in schema for {name!r}")
