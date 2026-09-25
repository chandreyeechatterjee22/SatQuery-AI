"""What a tool sees of an upload: its manifest, file paths and output folders."""
from dataclasses import dataclass
from pathlib import Path

from ingest import store
from raster.preview import render_preview


@dataclass
class UploadContext:
    upload_id: str
    folder: Path
    manifest: dict

    @classmethod
    def load(cls, upload_id):
        folder = store.upload_path(upload_id)
        if folder is None:
            return None
        return cls(upload_id, folder, store.load_manifest(upload_id))

    @property
    def mode(self):
        return self.manifest["mode"]

    @property
    def files(self):
        return self.manifest["files"]

    def file(self, slot):
        return next(f for f in self.files if f["slot"] == slot)

    def path(self, slot):
        return self.folder / self.file(slot)["stored_as"]

    def preview_path(self, slot):
        """Quicklook PNG for a file, rendered on first use and cached."""
        out = self.folder / "previews" / f"file_{slot}.png"
        if not out.exists():
            out.parent.mkdir(exist_ok=True)
            render_preview(self.path(slot), self.file(slot)["bands"], out)
        return out

    def preview_url(self, slot):
        return f"/api/uploads/{self.upload_id}/preview/{slot}"

    def query_dir(self, query_id):
        path = self.folder / "queries" / query_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def evidence_url(self, query_id, name):
        return f"/api/uploads/{self.upload_id}/queries/{query_id}/{name}"
