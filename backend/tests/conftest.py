import pytest

from ingest import store
from ingest.validation import validate_upload
from tests.synthetic import make_geotiff


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    target = tmp_path / "uploads"
    monkeypatch.setenv("UPLOAD_DIR", str(target))
    return target


@pytest.fixture
def make_upload(upload_dir, tmp_path):
    """Create an accepted upload on disk and return its id.

    ``specs`` is a list of make_geotiff kwargs, one per file.
    """
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)

    def _make(mode, specs, dates=None, sensors=None):
        upload_id = store.new_upload_id()
        staged = store.staging_dir(upload_id)
        files = []
        for slot, spec in enumerate(specs, start=1):
            path = make_geotiff(staged / f"file_{slot}.tif", **spec)
            files.append((f"input_{slot}.tif", path))
        result = validate_upload(mode, files, dates=dates, sensors=sensors)
        assert result["ok"], result["reasons"]
        for info, (_, path) in zip(result["files"], files):
            info["stored_as"] = path.name
        store.commit(upload_id, {"upload_id": upload_id, "status": "accepted", "mode": mode,
                                 "benchmark_mode": False, "files": result["files"],
                                 "pair": result["pair"], "warnings": result["warnings"]})
        return upload_id

    return _make
