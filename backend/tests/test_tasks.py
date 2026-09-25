import pytest

from agent.tasks import (CAPTION, CHANGE, METADATA, UNKNOWN, VQA, WATER_BUILTUP, classify, route,
                         tasks_for_mode)


@pytest.mark.parametrize("question, task", [
    ("What changed between the two dates?", CHANGE),
    ("Has built-up area increased, decreased or remained unchanged?", CHANGE),
    ("Compare vegetation before and after", CHANGE),
    ("How many bands does this image have?", METADATA),
    ("What is the spatial resolution?", METADATA),
    ("Which CRS / EPSG is it in?", METADATA),
    ("Where is the water?", WATER_BUILTUP),
    ("Show flooded areas", WATER_BUILTUP),
    ("Map the built-up area", WATER_BUILTUP),
    ("How much of the scene is urban?", WATER_BUILTUP),
    ("Describe this image", CAPTION),
    ("Give me a caption", CAPTION),
    ("What does this image show?", CAPTION),
    ("Are there any airports?", VQA),
    ("Is there a road crossing the field?", VQA),
])
def test_rule_classification(question, task):
    res = classify(question)
    assert res["task"] == task
    assert res["method"] == "rules"
    assert res["matched"]


def test_single_rule_hit_is_high_confidence():
    res = classify("Describe the scene")
    assert res["confidence"] == 0.95 and res["also_matched"] == []


def test_conflicting_rules_lower_confidence_and_are_recorded():
    res = classify("Has the water area changed?")
    assert res["task"] == CHANGE
    assert res["also_matched"] == [WATER_BUILTUP]
    assert res["confidence"] == 0.8


def test_generic_question_is_vqa_with_lower_confidence():
    res = classify("Are there any airports?")
    assert res["task"] == VQA and res["confidence"] == 0.6


@pytest.mark.parametrize("question, task", [
    ("chnages in urbn area", CHANGE),      # "chnages" ~ changes wins on priority
    ("descirbe", CAPTION),
    ("resoluton please", METADATA),
    ("watr bodys", WATER_BUILTUP),
])
def test_fuzzy_fallback_handles_typos(question, task):
    res = classify(question)
    assert res["task"] == task
    assert res["method"] == "fuzzy_keywords"
    assert res["confidence"] == 0.6
    assert any("~" in m for m in res["matched"])


@pytest.mark.parametrize("question", ["", "   ", "hello there", "xyzzy plugh"])
def test_unknown(question):
    res = classify(question)
    assert res["task"] == UNKNOWN and res["confidence"] == 0.0 and res["method"] == "none"


def test_result_has_no_free_text_reasoning():
    res = classify("What changed?")
    assert set(res) == {"task", "method", "matched", "confidence", "also_matched"}


@pytest.mark.parametrize("task, mode, expected", [
    (METADATA, "single", (METADATA, None)),
    (METADATA, "bi_temporal", (METADATA, None)),
    (CAPTION, "single", (CAPTION, None)),
    (CAPTION, "optical_sar", (None, None)),
    (VQA, "bi_temporal", (None, None)),
    (WATER_BUILTUP, "optical_sar", (WATER_BUILTUP, None)),
    (WATER_BUILTUP, "single", (VQA, WATER_BUILTUP)),
    (WATER_BUILTUP, "bi_temporal", (CHANGE, WATER_BUILTUP)),
    (CHANGE, "bi_temporal", (CHANGE, None)),
    (CHANGE, "single", (None, None)),
    (CHANGE, "optical_sar", (None, None)),
    (UNKNOWN, "single", (None, None)),
])
def test_route(task, mode, expected):
    assert route(task, mode) == expected


def test_tasks_for_mode():
    assert tasks_for_mode("single") == [METADATA, CAPTION, VQA]
    assert tasks_for_mode("optical_sar") == [METADATA, WATER_BUILTUP]
    assert tasks_for_mode("bi_temporal") == [METADATA, CHANGE]
