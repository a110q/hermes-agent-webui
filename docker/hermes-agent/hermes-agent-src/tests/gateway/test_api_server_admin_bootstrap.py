from gateway.platforms.api_server_admin_bootstrap import materialize_default_profile_if_present
from gateway.platforms.api_server_admin_profiles import AdminProfilesStore
from hermes_cli.config import load_config, load_env


def test_materialize_default_profile_into_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = AdminProfilesStore(tmp_path / "admin_profiles.json")
    created = store.create_profile(
        name="OpenAI Prod",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-live",
        model_name="gpt-4.1",
    )
    store.set_default_profile(created["id"])

    result = materialize_default_profile_if_present(tmp_path)
    config = load_config()
    env_vars = load_env()

    assert result["applied"] is True
    assert result["profile_id"] == created["id"]
    assert config["model"]["base_url"] == "https://api.openai.com/v1"
    assert env_vars["OPENAI_API_KEY"] == "sk-live"


def test_materialize_uses_last_known_good_when_default_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = AdminProfilesStore(tmp_path / "admin_profiles.json")
    created = store.create_profile(
        name="Fallback",
        provider_type="openai-compatible",
        base_url="https://proxy.example/v1",
        api_key="sk-fallback",
        model_name="gpt-4o-mini",
    )
    document = store.read_document()
    document["default_profile_id"] = "missing-profile"
    document["last_known_good_profile_id"] = created["id"]
    store._write_document(document)

    result = materialize_default_profile_if_present(tmp_path)

    assert result["applied"] is True
    assert result["profile_id"] == created["id"]


def test_materialize_noops_when_profile_library_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    result = materialize_default_profile_if_present(tmp_path)
    assert result == {"applied": False, "reason": "profile_library_missing"}
