"""Config-only tests for gee_service: ee.Initialize is stubbed, no network calls."""
import gee_service


def test_project_id_defaults_to_original(monkeypatch):
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)
    assert gee_service.get_gee_project_id() == "satquery-ai-508105"


def test_project_id_from_env(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "my-other-project")
    assert gee_service.get_gee_project_id() == "my-other-project"


def test_empty_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GEE_PROJECT_ID", "")
    assert gee_service.get_gee_project_id() == "satquery-ai-508105"


def test_initialize_uses_env_project(monkeypatch):
    calls = []
    monkeypatch.setattr(gee_service.ee, "Initialize", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT", raising=False)
    monkeypatch.delenv("GEE_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("GEE_PROJECT_ID", "env-project")

    gee_service.initialize_gee()

    assert calls == [((), {"project": "env-project"})]


def test_initialize_with_service_account(monkeypatch):
    calls = []
    monkeypatch.setattr(gee_service.ee, "ServiceAccountCredentials", lambda sa, key: ("creds", sa, key))
    monkeypatch.setattr(gee_service.ee, "Initialize", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setenv("GEE_SERVICE_ACCOUNT", "svc@example.iam.gserviceaccount.com")
    monkeypatch.setenv("GEE_PRIVATE_KEY", "key.json")
    monkeypatch.delenv("GEE_PROJECT_ID", raising=False)

    gee_service.initialize_gee()

    assert calls == [((("creds", "svc@example.iam.gserviceaccount.com", "key.json"),), {"project": "satquery-ai-508105"})]
