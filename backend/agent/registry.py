"""Tool interface and registry. One tool per task; tools declare a param allow-list."""
from dataclasses import dataclass, field

OK = "OK"
NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass
class ToolResult:
    answer: str
    confidence: float
    evidence_images: list = field(default_factory=list)
    data: dict = field(default_factory=dict)


class Tool:
    """Base class. Subclasses set name/version/task/params and implement run()."""
    name = "tool"
    version = "0.0.0"
    task = None
    description = ""
    params = {}  # allow-list schema, see agent.params

    def availability(self):
        """Return (available, reason_if_not)."""
        return True, None

    def extract_params(self, question, ctx):
        """Derive params from the question. The controller validates them afterwards."""
        return {}

    def inputs(self, ctx):
        """Which uploaded files this tool reads (for the trace)."""
        return [{"slot": f["slot"], "filename": f["filename"], "kind": f["kind"],
                 "date": f.get("date")} for f in ctx.files]

    def run(self, ctx, params, query_id):
        raise NotImplementedError

    def describe(self):
        return {"name": self.name, "version": self.version, "task": self.task,
                "description": self.description, "params": self.params,
                "available": self.availability()[0]}


class PlaceholderTool(Tool):
    """Registered so routing works end to end; reports NOT_AVAILABLE until implemented."""
    version = "0.0.0"
    unavailable_reason = "This tool is not implemented yet."

    def availability(self):
        return False, self.unavailable_reason

    def run(self, ctx, params, query_id):
        raise RuntimeError(self.unavailable_reason)


class Registry:
    def __init__(self, tools=()):
        self._by_task = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool):
        if tool.task in self._by_task:
            raise ValueError(f"task {tool.task!r} already has tool {self._by_task[tool.task].name!r}")
        self._by_task[tool.task] = tool

    def for_task(self, task):
        return self._by_task.get(task)

    def all(self):
        return list(self._by_task.values())


def default_registry():
    from agent.tools.metadata import MetadataTool
    from agent.tools.placeholders import (CaptionPlaceholder, ChangePlaceholder, VqaPlaceholder,
                                          WaterBuiltupPlaceholder)
    return Registry([MetadataTool(), CaptionPlaceholder(), VqaPlaceholder(),
                     WaterBuiltupPlaceholder(), ChangePlaceholder()])
