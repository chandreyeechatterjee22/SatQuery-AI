import settings
from ingest import store


def test_upload_dir_default_is_repo_data(monkeypatch):
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    assert settings.upload_dir() == settings.REPO_ROOT / "data" / "uploads"


def test_upload_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    assert settings.upload_dir() == tmp_path


def test_max_upload_default_and_env(monkeypatch):
    monkeypatch.delenv("MAX_UPLOAD_MB", raising=False)
    assert settings.max_upload_bytes() == 500 * 1024 * 1024
    monkeypatch.setenv("MAX_UPLOAD_MB", "2")
    assert settings.max_upload_bytes() == 2 * 1024 * 1024
    monkeypatch.setenv("MAX_UPLOAD_MB", "lots")
    assert settings.max_upload_bytes() == 500 * 1024 * 1024


def test_upload_id_format():
    uid = store.new_upload_id()
    assert store.is_valid_upload_id(uid)
    assert not store.is_valid_upload_id("../x")
    assert not store.is_valid_upload_id(uid.upper())
    assert not store.is_valid_upload_id(None)


def test_stored_name_ignores_user_path():
    assert store.stored_name(1, "../../a/B.TIF") == "file_1.tif"
    assert store.stored_name(2, "photo.jpeg") == "file_2.jpeg"


def test_commit_and_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    uid = store.new_upload_id()
    (store.staging_dir(uid) / "file_1.tif").write_bytes(b"x")

    folder = store.commit(uid, {"upload_id": uid, "mode": "single"})

    assert folder == tmp_path / uid
    assert store.load_manifest(uid) == {"upload_id": uid, "mode": "single"}
    assert store.upload_path(uid) == folder
    assert not (tmp_path / ".staging" / uid).exists()


def test_discard_removes_staging(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    uid = store.new_upload_id()
    (store.staging_dir(uid) / "f").write_bytes(b"x")
    store.discard(uid)
    assert not (tmp_path / ".staging" / uid).exists()
    assert store.load_manifest(uid) is None
