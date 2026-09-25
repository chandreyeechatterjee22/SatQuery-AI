"""HTTP routes for the agent: POST /api/query, tool list, previews and evidence files."""
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent.context import UploadContext
from agent.controller import get_registry, run_query
from ingest import store

router = APIRouter(prefix="/api", tags=["agent"])

_EVIDENCE_NAME = re.compile(r"^[a-z0-9_]+\.(png|json)$")


class QueryRequest(BaseModel):
    upload_id: str
    question: str = Field(..., min_length=1, max_length=1000)
    params: Optional[Dict[str, Any]] = None


@router.post("/query")
def query(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="Question is empty.")
    result = run_query(request.upload_id, request.question, request.params)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Upload '{request.upload_id}' not found.")
    return result


@router.get("/tools")
def list_tools():
    return {"tools": [tool.describe() for tool in get_registry().all()]}


@router.get("/uploads/{upload_id}/preview/{slot}")
def preview(upload_id: str, slot: int):
    ctx = UploadContext.load(upload_id)
    if ctx is None or slot not in {f["slot"] for f in ctx.files}:
        raise HTTPException(status_code=404, detail="Preview not found.")
    return FileResponse(ctx.preview_path(slot), media_type="image/png")


@router.get("/uploads/{upload_id}/queries/{query_id}/{name}")
def evidence(upload_id: str, query_id: str, name: str):
    folder = store.upload_path(upload_id)
    if folder is None or not store.is_valid_upload_id(query_id) or not _EVIDENCE_NAME.match(name):
        raise HTTPException(status_code=404, detail="File not found.")
    path = folder / "queries" / query_id / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path, media_type="image/png" if name.endswith(".png") else "application/json")
