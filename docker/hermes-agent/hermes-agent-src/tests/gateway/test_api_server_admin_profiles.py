from gateway.platforms.api_server_admin_profiles import AdminProfilesStore


def test_create_profile_persists_and_masks_secret(tmp_path):
    store = AdminProfilesStore(tmp_path / "admin_profiles.json")

    created = store.create_profile(
        name="OpenAI Prod",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-live-secret",
        model_name="gpt-4.1",
    )
    listed = store.list_profiles()
    raw = store.read_document()

    assert created["name"] == "OpenAI Prod"
    assert listed[0]["api_key_masked"] == "••••cret"
    assert raw["profiles"][0]["api_key"] == "sk-live-secret"
    assert raw["default_profile_id"] is None
    assert raw["active_profile_id"] is None


def test_set_default_active_and_last_known_good(tmp_path):
    store = AdminProfilesStore(tmp_path / "admin_profiles.json")
    first = store.create_profile(
        name="Primary",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-primary",
        model_name="gpt-4.1",
    )
    second = store.create_profile(
        name="Backup",
        provider_type="openai-compatible",
        base_url="https://proxy.example/v1",
        api_key="sk-backup",
        model_name="gpt-4o-mini",
    )

    store.set_default_profile(second["id"])
    store.set_active_profile(first["id"])
    store.mark_last_known_good(first["id"])
    document = store.read_document()

    assert document["default_profile_id"] == second["id"]
    assert document["active_profile_id"] == first["id"]
    assert document["last_known_good_profile_id"] == first["id"]


def test_delete_profile_clears_metadata_links(tmp_path):
    store = AdminProfilesStore(tmp_path / "admin_profiles.json")
    profile = store.create_profile(
        name="Delete Me",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-delete",
        model_name="gpt-4.1",
    )
    store.set_default_profile(profile["id"])
    store.set_active_profile(profile["id"])
    store.mark_last_known_good(profile["id"])

    store.delete_profile(profile["id"])
    document = store.read_document()

    assert document["profiles"] == []
    assert document["default_profile_id"] is None
    assert document["active_profile_id"] is None
    assert document["last_known_good_profile_id"] is None
