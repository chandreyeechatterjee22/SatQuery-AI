import pytest

from agent import tasks
from agent.context import UploadContext
from agent.params import validate_params
from agent.registry import PlaceholderTool, Registry, Tool, default_registry
from agent.tools.metadata import FIELDS, MetadataTool
from agent.tools.change import ChangeTool
from agent.tools.question_classes import classes_in


def test_default_registry_covers_every_task():
    reg = default_registry()
    assert {t.task for t in reg.all()} == set(tasks.TASKS)
    for tool in reg.all():
        assert tool.name and tool.version
        # Every tool's default params must pass its own allow-list.
        _, errors = validate_params({k: v for k, v in tool.params.items() if not v.get("required")}, {})
        assert errors == []


def test_availability_without_model_weights():
    # Tests run without weights (see conftest): CLIP tools are unavailable, numpy tools are not.
    available = {t.task: t.availability()[0] for t in default_registry().all()}
    assert available == {tasks.METADATA: True, tasks.CAPTION: False, tasks.VQA: False,
                         tasks.WATER_BUILTUP: True, tasks.CHANGE: True}


def test_registry_rejects_duplicate_task():
    class A(Tool):
        task = "x"
    with pytest.raises(ValueError, match="already has tool"):
        Registry([A(), A()])


def test_placeholder_reports_reason():
    class Later(PlaceholderTool):
        unavailable_reason = "Coming later."
    ok, reason = Later().availability()
    assert ok is False and reason == "Coming later."
    with pytest.raises(RuntimeError):
        Later().run(None, {}, "q")


@pytest.mark.parametrize("question, allowed, expected", [
    ("Where is the water?", ["water", "built_up"], ["water"]),
    ("Show urban areas", ["water", "built_up"], ["built_up"]),
    ("Water and buildings please", ["water", "built_up"], ["water", "built_up"]),
    ("Map it", ["water", "built_up"], ["water", "built_up"]),
    ("Has forest cover changed?", ["water", "built_up", "vegetation", "other"], ["vegetation"]),
    ("Did vegetation change?", ["water", "built_up"], ["water", "built_up"]),
])
def test_classes_in(question, allowed, expected):
    assert classes_in(question, allowed) == expected


def test_change_tool_extracts_classes():
    assert ChangeTool().extract_params("Has built-up increased?", None) == {"classes": ["built_up"]}


# --- metadata tool --------------------------------------------------------

@pytest.mark.parametrize("question, fields", [
    ("How many bands does it have?", ["bands"]),
    ("What is the CRS and resolution?", ["crs", "resolution"]),
    ("When were these taken?", ["date"]),
    ("Show me the metadata", FIELDS),
])
def test_metadata_param_extraction(question, fields):
    assert MetadataTool().extract_params(question, None) == {"fields": fields}


def test_metadata_tool_answers_from_manifest(make_upload):
    uid = make_upload("single", [{"count": 4}], sensors=["cartosat2s"])
    ctx = UploadContext.load(uid)
    res = MetadataTool().run(ctx, {"fields": ["bands", "crs", "resolution", "sensor"]}, "q1")

    assert res.confidence == 1.0
    assert "File 1 (input_1.tif): 4 band(s), blue=band 1, green=band 2, red=band 3, nir=band 4" in res.answer
    assert "(inferred" not in res.answer
    assert "CRS EPSG:32643" in res.answer
    assert "resolution 10 x 10 metres" in res.answer
    assert "Cartosat-2S MX" in res.answer
    assert res.evidence_images == [{"id": "preview_1", "kind": "preview",
                                    "label": "File 1 preview (input_1.tif)",
                                    "url": f"/api/uploads/{uid}/preview/1"}]
    assert (ctx.folder / "previews" / "file_1.png").is_file()


def test_metadata_tool_flags_inferred_bands_and_pair_overlap(make_upload):
    uid = make_upload("optical_sar", [{"count": 4},
                                      {"count": 2, "dtype": "float32", "origin": (780040.0, 1440000.0)}])
    res = MetadataTool().run(UploadContext.load(uid), {"fields": ["bands", "bounds"]}, "q1")
    assert "(inferred from band count)" in res.answer
    assert "vv=band 1, vh=band 2" in res.answer
    assert "overlap by 50%" in res.answer
    assert len(res.evidence_images) == 2


def test_metadata_tool_dates(make_upload):
    uid = make_upload("bi_temporal", [{}, {}], dates=["2023-01-01", "2025-06-30"])
    res = MetadataTool().run(UploadContext.load(uid), {"fields": ["date"]}, "q1")
    assert "date 2023-01-01" in res.answer and "date 2025-06-30" in res.answer
