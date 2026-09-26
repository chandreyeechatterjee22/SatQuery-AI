"""HTTP routes for uploads: POST /api/uploads and GET /api/uploads/{upload_id}."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

import settings
from ingest import store
from ingest.validation import reason, validate_upload

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

_CHUNK = 1024 * 1024


@router.post("", status_code=201)
async def create_upload(
    mode: str = Form(..., description="single | optical_sar | bi_temporal"),
    file_1: Optional[UploadFile] = File(None, description="single image, optical image, or date-1 image"),
    file_2: Optional[UploadFile] = File(None, description="SAR image or date-2 image"),
    date_1: Optional[str] = Form(None, description="YYYY-MM-DD (required for bi_temporal)"),
    date_2: Optional[str] = Form(None, description="YYYY-MM-DD (required for bi_temporal)"),
    sensor_1: Optional[str] = Form(None, description="auto | sentinel2 | cartosat2s | bgrn | rgb | sar"),
    sensor_2: Optional[str] = Form(None, description="auto | sentinel2 | cartosat2s | bgrn | rgb | sar"),
    band_roles_1: Optional[str] = Form(None, description="comma list per band, e.g. blue,green,red,nir,swir1 ('-' = ignore)"),
    band_roles_2: Optional[str] = Form(None, description="comma list per band, e.g. vv,vh"),
    benchmark_mode: bool = Form(False, description="also accept PNG/JPEG"),
):
    uploads = [u for u in (file_1, file_2) if u is not None and u.filename]
    upload_id = store.new_upload_id()
    staged = store.staging_dir(upload_id)
    try:
        saved, too_big = [], []
        limit = settings.max_upload_bytes()
        for slot, upload in enumerate(uploads, start=1):
            target = staged / store.stored_name(slot, upload.filename)
            if not await _save_limited(upload, target, limit):
                too_big.append(reason("file_too_large",
                                      f"File {slot} ({upload.filename}) exceeds the "
                                      f"{limit // (1024 * 1024)} MB limit.", slot))
            saved.append((upload.filename, target))
        if too_big:
            return _rejected(too_big, [])

        result = validate_upload(mode, saved, dates=[date_1, date_2],
                                 sensors=[sensor_1, sensor_2], benchmark_mode=benchmark_mode,
                                 band_roles=[band_roles_1, band_roles_2])
        if not result["ok"]:
            return _rejected(result["reasons"], result["warnings"])

        for info, (_, target) in zip(result["files"], saved):
            info["stored_as"] = target.name
        manifest = {
            "upload_id": upload_id,
            "status": "accepted",
            "mode": mode,
            "benchmark_mode": benchmark_mode,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": result["files"],
            "pair": result["pair"],
            "warnings": result["warnings"],
        }
        store.commit(upload_id, manifest)
        return manifest
    finally:
        store.discard(upload_id)


@router.get("/{upload_id}")
def get_upload(upload_id: str):
    manifest = store.load_manifest(upload_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Upload '{upload_id}' not found.")
    return manifest


async def _save_limited(upload, target, limit):
    """Stream an upload to disk; return False (and stop) once it exceeds ``limit`` bytes."""
    written = 0
    with open(target, "wb") as out:
        while chunk := await upload.read(_CHUNK):
            written += len(chunk)
            if written > limit:
                return False
            out.write(chunk)
    return True


def _rejected(reasons, warnings):
    status = 413 if any(r["code"] == "file_too_large" for r in reasons) else 422
    return JSONResponse(status_code=status,
                        content={"status": "rejected", "reasons": reasons, "warnings": warnings})
