"""On-disk storage for uploads: <UPLOAD_DIR>/<upload_id>/{file_1.tif, file_2.tif, manifest.json}.

Files are written to a staging folder first and only moved into place once
validation passes, so rejected uploads never leave anything behind.
"""
import json
import re
import shutil
import uuid
from pathlib import Path

import settings

MANIFEST = "manifest.json"
_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_upload_id():
    return uuid.uuid4().hex


def is_valid_upload_id(upload_id):
    return bool(_ID_RE.match(upload_id or ""))


def staging_dir(upload_id):
    path = settings.upload_dir() / ".staging" / upload_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def stored_name(slot, original_filename):
    """Server-side name for a file; the user's filename is never used as a path."""
    return f"file_{slot}{Path(original_filename or '').suffix.lower()}"


def commit(upload_id, manifest):
    """Write the manifest and move the staged upload into place. Returns its folder."""
    staged = staging_dir(upload_id)
    (staged / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    final = settings.upload_dir() / upload_id
    shutil.move(str(staged), str(final))
    return final


def discard(upload_id):
    shutil.rmtree(settings.upload_dir() / ".staging" / upload_id, ignore_errors=True)


def upload_path(upload_id):
    """Folder of an accepted upload, or None if the id is malformed or unknown."""
    if not is_valid_upload_id(upload_id):
        return None
    path = settings.upload_dir() / upload_id
    return path if (path / MANIFEST).is_file() else None


def load_manifest(upload_id):
    path = upload_path(upload_id)
    if path is None:
        return None
    return json.loads((path / MANIFEST).read_text(encoding="utf-8"))
