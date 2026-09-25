import pytest

from agent.params import validate_params

SCHEMA = {
    "classes": {"type": "enum_list", "choices": ["water", "built_up"], "min_items": 1,
                "default": ["water", "built_up"]},
    "method": {"type": "enum", "choices": ["otsu", "fixed"], "default": "otsu"},
    "threshold": {"type": "float", "min": -30, "max": 0, "default": -18.0},
    "tiles": {"type": "int", "min": 1, "max": 8, "default": 1},
    "question": {"type": "str", "max_length": 10},
    "overlay": {"type": "bool", "default": True},
}


def test_defaults_fill_missing():
    clean, errors = validate_params(SCHEMA, {})
    assert errors == []
    assert clean == {"classes": ["water", "built_up"], "method": "otsu", "threshold": -18.0,
                     "tiles": 1, "overlay": True}


def test_valid_values_pass_and_lists_dedupe():
    clean, errors = validate_params(SCHEMA, {"classes": ["water", "water"], "method": "fixed",
                                             "threshold": -20, "tiles": 4, "question": "hi",
                                             "overlay": False})
    assert errors == []
    assert clean["classes"] == ["water"] and clean["threshold"] == -20 and clean["question"] == "hi"


def test_unknown_param_rejected():
    _, errors = validate_params(SCHEMA, {"model_path": "C:/evil.pt"})
    assert len(errors) == 1 and "'model_path' is not an allowed parameter" in errors[0]


@pytest.mark.parametrize("params, fragment", [
    ({"classes": ["water", "clouds"]}, "not in"),
    ({"classes": "water"}, "list of strings"),
    ({"classes": []}, "at least 1"),
    ({"method": "magic"}, "must be one of"),
    ({"threshold": 5}, "between"),
    ({"threshold": "low"}, "must be a float"),
    ({"tiles": 2.5}, "must be an int"),
    ({"tiles": True}, "must be an int"),
    ({"question": "x" * 11}, "longer than 10"),
    ({"question": 3}, "must be a string"),
    ({"overlay": "yes"}, "true or false"),
])
def test_bad_values_rejected(params, fragment):
    clean, errors = validate_params(SCHEMA, params)
    assert len(errors) == 1 and fragment in errors[0]
    assert list(params)[0] not in clean


def test_required_param():
    _, errors = validate_params({"q": {"type": "str", "required": True}}, {})
    assert errors == ["'q' is required"]


def test_empty_schema_rejects_everything():
    _, errors = validate_params({}, {"x": 1})
    assert "allowed: none" in errors[0]


def test_bad_schema_type_is_a_programming_error():
    with pytest.raises(ValueError):
        validate_params({"x": {"type": "blob"}}, {"x": 1})
