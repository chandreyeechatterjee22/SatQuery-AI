"""Agent controller: classify -> check mode -> select tool -> validate params -> run.

Every step is recorded in the trace as structured facts (what was decided,
how long it took, whether it succeeded). No chain-of-thought is produced.
"""
import json
import time
import uuid

from agent import tasks
from agent.context import UploadContext
from agent.params import validate_params
from agent.registry import NOT_AVAILABLE, OK, default_registry

REJECTED = "REJECTED"
ERROR = "ERROR"

EXAMPLES = {
    "single": ["Describe this image", "How many bands does this image have?",
               "Are there any water bodies?"],
    "optical_sar": ["Where is the water?", "How much of the area is built-up?",
                    "What is the resolution of each image?"],
    "bi_temporal": ["What changed?",
                    "Has built-up area increased, decreased or remained unchanged?",
                    "What are the acquisition dates?"],
}

_NEEDS = {
    tasks.CHANGE: "a bi_temporal upload (two images from different dates)",
    tasks.WATER_BUILTUP: "an optical_sar upload",
    tasks.CAPTION: "a single-image upload",
    tasks.VQA: "a single-image upload",
}

_registry = None


def get_registry():
    global _registry
    if _registry is None:
        _registry = default_registry()
    return _registry


def run_query(upload_id, question, params=None, registry=None):
    """Answer ``question`` about an upload. Returns None if the upload does not exist."""
    ctx = UploadContext.load(upload_id)
    if ctx is None:
        return None
    return _Run(ctx, question.strip(), params or {}, registry or get_registry()).execute()


class _Run:
    def __init__(self, ctx, question, params_override, registry):
        self.ctx, self.question = ctx, question
        self.params_override, self.registry = params_override, registry
        self.query_id = uuid.uuid4().hex
        self.steps = []
        self.task = self.rerouted_from = self.tool = None
        self.params, self.inputs = {}, []
        self.task_confidence = None
        self.started = time.perf_counter()

    def execute(self):
        # 1. Classify the question.
        t = time.perf_counter()
        cls = tasks.classify(self.question)
        self.task_confidence = cls["confidence"]
        self._step("classify_task", "ok" if cls["task"] != tasks.UNKNOWN else "failed", t,
                   {k: cls[k] for k in ("task", "method", "matched", "confidence", "also_matched")})
        if cls["task"] == tasks.UNKNOWN:
            return self._finish(REJECTED, "I could not tell what kind of question this is. "
                                f"For a {self.ctx.mode} upload, try: " + "; ".join(
                                    f'"{q}"' for q in EXAMPLES[self.ctx.mode]) + ".")

        # 2. Check the task fits the upload mode (reroute if another task can answer).
        t = time.perf_counter()
        self.task, self.rerouted_from = tasks.route(cls["task"], self.ctx.mode)
        detail = {"mode": self.ctx.mode, "classified_task": cls["task"], "task": self.task,
                  "rerouted_from": self.rerouted_from}
        if self.task is None:
            self._step("check_mode", "failed", t, detail)
            self.task = cls["task"]
            return self._finish(REJECTED, f"This question needs {_NEEDS[cls['task']]}, but this "
                                f"upload is '{self.ctx.mode}'. You can ask: " + "; ".join(
                                    f'"{q}"' for q in EXAMPLES[self.ctx.mode]) + ".")
        self._step("check_mode", "ok", t, detail)

        # 3. Pick the tool registered for the task.
        t = time.perf_counter()
        self.tool = self.registry.for_task(self.task)
        if self.tool is None:
            self._step("select_tool", "failed", t, {"task": self.task})
            return self._finish(ERROR, f"No tool is registered for task '{self.task}'.")
        self.inputs = self.tool.inputs(self.ctx)
        self._step("select_tool", "ok", t, {"tool": self.tool.name, "version": self.tool.version})

        # 4. Validate params against the tool's allow-list.
        t = time.perf_counter()
        proposed = {**self.tool.extract_params(self.question, self.ctx), **self.params_override}
        clean, errors = validate_params(self.tool.params, proposed)
        if errors:
            self._step("validate_params", "failed", t, {"proposed": proposed, "errors": errors})
            return self._finish(REJECTED, "Invalid parameters: " + "; ".join(errors) + ".")
        self.params = clean
        self._step("validate_params", "ok", t, {"params": clean})

        # 5. Run the tool (or report that its model is not available).
        t = time.perf_counter()
        available, reason = self.tool.availability()
        if not available:
            self._step("run_tool", "not_available", t, {"reason": reason})
            return self._finish(NOT_AVAILABLE, f"Not available: {reason}")
        try:
            result = self.tool.run(self.ctx, clean, self.query_id)
        except Exception as exc:  # report, never crash the request
            self._step("run_tool", "failed", t, {"error": f"{type(exc).__name__}: {exc}"})
            return self._finish(ERROR, f"The {self.tool.name} tool failed: {exc}")
        self._step("run_tool", "ok", t, {"evidence_images": len(result.evidence_images)})
        confidence = round(result.confidence * self.task_confidence, 2)
        return self._finish(OK, result.answer, confidence, result.evidence_images, result.data,
                            tool_confidence=result.confidence)

    def _step(self, name, status, started, detail):
        self.steps.append({"step": name, "status": status,
                           "duration_ms": _ms(time.perf_counter() - started), "detail": detail})

    def _finish(self, status, answer, confidence=None, evidence=None, details=None,
                tool_confidence=None):
        response = {
            "query_id": self.query_id,
            "upload_id": self.ctx.upload_id,
            "question": self.question,
            "status": status,
            "answer": answer,
            "confidence": confidence,
            "evidence_images": evidence or [],
            "details": details or {},
            "trace": {
                "task": self.task,
                "rerouted_from": self.rerouted_from,
                "tool": self.tool.name if self.tool else None,
                "tool_version": self.tool.version if self.tool else None,
                "params": self.params,
                "inputs": self.inputs,
                "duration_ms": _ms(time.perf_counter() - self.started),
                "status": status,
                "confidence": {"task": self.task_confidence, "tool": tool_confidence,
                               "combined": confidence},
                "steps": self.steps,
            },
        }
        out = self.ctx.query_dir(self.query_id) / "result.json"
        out.write_text(json.dumps(response, indent=2), encoding="utf-8")
        return response


def _ms(seconds):
    return round(seconds * 1000, 2)
