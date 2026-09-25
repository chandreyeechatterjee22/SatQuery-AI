import json

import pytest

from agent import tasks
from agent.controller import run_query
from agent.registry import Registry, Tool, ToolResult, default_registry

TRACE_KEYS = {"task", "rerouted_from", "tool", "tool_version", "params", "inputs", "duration_ms",
              "status", "confidence", "steps"}


def step_names(res):
    return [(s["step"], s["status"]) for s in res["trace"]["steps"]]


def test_unknown_upload_returns_none(upload_dir):
    assert run_query("0" * 32, "What changed?") is None


def test_metadata_question_runs_end_to_end(make_upload, upload_dir):
    uid = make_upload("single", [{"count": 13}])
    res = run_query(uid, "  How many bands does this image have?  ")

    assert res["status"] == "OK"
    assert res["question"] == "How many bands does this image have?"
    assert "13 band(s)" in res["answer"]
    assert res["confidence"] == 0.95          # rule confidence 0.95 x tool confidence 1.0
    assert res["evidence_images"][0]["url"] == f"/api/uploads/{uid}/preview/1"

    trace = res["trace"]
    assert set(trace) == TRACE_KEYS
    assert trace["task"] == "metadata" and trace["status"] == "OK"
    assert trace["tool"] == "image_metadata" and trace["tool_version"] == "1.0.0"
    assert trace["params"] == {"fields": ["bands"]}
    assert trace["inputs"] == [{"slot": 1, "filename": "input_1.tif", "kind": "optical", "date": None}]
    assert trace["confidence"] == {"task": 0.95, "tool": 1.0, "combined": 0.95}
    assert trace["duration_ms"] >= 0
    assert step_names(res) == [("classify_task", "ok"), ("check_mode", "ok"), ("select_tool", "ok"),
                               ("validate_params", "ok"), ("run_tool", "ok")]
    assert all(s["duration_ms"] >= 0 for s in trace["steps"])

    saved = upload_dir / uid / "queries" / res["query_id"] / "result.json"
    assert json.loads(saved.read_text()) == res


def test_placeholder_tool_reports_not_available(make_upload):
    uid = make_upload("bi_temporal", [{}, {}], dates=["2023-01-01", "2025-01-01"])
    res = run_query(uid, "Has built-up area increased, decreased or remained unchanged?")

    assert res["status"] == "NOT_AVAILABLE"
    assert res["answer"].startswith("Not available:")
    assert res["confidence"] is None and res["evidence_images"] == []
    assert res["trace"]["tool"] == "landcover_change"
    assert res["trace"]["params"] == {"classes": ["built_up"]}
    assert step_names(res)[-1] == ("run_tool", "not_available")


def test_task_that_does_not_fit_mode_is_rejected(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "What changed between the two dates?")

    assert res["status"] == "REJECTED"
    assert "bi_temporal" in res["answer"] and "'single'" in res["answer"]
    assert res["trace"]["task"] == "change" and res["trace"]["tool"] is None
    assert step_names(res) == [("classify_task", "ok"), ("check_mode", "failed")]


def test_reroute_is_recorded(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "Where is the water?")
    assert res["trace"]["task"] == "vqa"
    assert res["trace"]["rerouted_from"] == "water_builtup"
    assert res["trace"]["steps"][1]["detail"]["rerouted_from"] == "water_builtup"
    assert res["status"] == "NOT_AVAILABLE"   # VQA model not loaded yet


def test_unknown_question_is_rejected_with_examples(make_upload):
    uid = make_upload("optical_sar", [{"count": 4}, {"count": 2, "dtype": "float32"}])
    res = run_query(uid, "hello there")
    assert res["status"] == "REJECTED"
    assert "Where is the water?" in res["answer"]
    assert step_names(res) == [("classify_task", "failed")]


def test_param_override_is_validated(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "What is the resolution?", params={"fields": ["crs"], "shell": "rm -rf"})
    assert res["status"] == "REJECTED"
    assert "'shell' is not an allowed parameter" in res["answer"]
    assert step_names(res)[-1] == ("validate_params", "failed")


def test_valid_param_override_wins(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "What is the resolution?", params={"fields": ["size"]})
    assert res["status"] == "OK" and res["trace"]["params"] == {"fields": ["size"]}
    assert "8 x 8 pixels" in res["answer"] and "resolution" not in res["answer"]


class _Boom(Tool):
    name, version, task = "boom", "9.9.9", tasks.METADATA

    def run(self, ctx, params, query_id):
        raise ValueError("disk on fire")


class _Fixed(Tool):
    name, version, task = "fixed", "1.2.3", tasks.METADATA

    def run(self, ctx, params, query_id):
        return ToolResult(answer="42", confidence=0.5, data={"x": 1})


def test_tool_exception_becomes_error_status(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "How many bands?", registry=Registry([_Boom()]))
    assert res["status"] == "ERROR"
    assert "disk on fire" in res["answer"]
    assert res["trace"]["steps"][-1]["detail"]["error"] == "ValueError: disk on fire"


def test_combined_confidence_and_details(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "How many bands?", registry=Registry([_Fixed()]))
    assert res["confidence"] == round(0.5 * 0.95, 2)
    assert res["details"] == {"x": 1}
    assert res["trace"]["tool_version"] == "1.2.3"


def test_missing_tool_is_error(make_upload):
    uid = make_upload("single", [{}])
    res = run_query(uid, "How many bands?", registry=Registry([]))
    assert res["status"] == "ERROR"
    assert step_names(res)[-1] == ("select_tool", "failed")


@pytest.mark.parametrize("question", ["What changed?", "How many bands?", "Describe it", "xyzzy"])
def test_trace_never_contains_free_text_reasoning(make_upload, question):
    uid = make_upload("single", [{}])
    res = run_query(uid, question, registry=default_registry())
    for step in res["trace"]["steps"]:
        assert set(step) == {"step", "status", "duration_ms", "detail"}
        for key in step["detail"]:
            assert key not in {"reasoning", "thoughts", "rationale", "chain_of_thought"}
