import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter
from hermes_cli.config import load_config, load_env, save_config, save_env_value


@pytest.mark.asyncio
async def test_root_returns_html_shell():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert response.content_type == "text/html"
    assert "Hermes 配置控制台" in body
    assert "当前 HERMES_API_KEY" in body
    assert "进入控制台" in body


@pytest.mark.asyncio
async def test_root_contains_profiles_console_shell():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
        body = await response.text()

    assert response.status == 200
    assert "profiles-list" in body
    assert "profile-form" in body
    assert "设为默认" in body
    assert "立即应用" in body
    assert "回滚上一版运行配置" in body


@pytest.mark.asyncio
async def test_auth_sets_cookie_and_config_masks_secret():
    save_config(
        {
            "model": {
                "provider": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "default": "openai/gpt-4.1-mini",
            }
        }
    )
    save_env_value("OPENROUTER_API_KEY", "real-secret")

    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        auth_response = await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        assert auth_response.status == 200
        assert "hermes_admin_session" in auth_response.cookies

        config_response = await client.get("/api/admin/config")
        payload = await config_response.json()

    assert payload["provider"] == "openrouter"
    assert payload["base_url"] == "https://openrouter.ai/api/v1"
    assert payload["model"] == "openai/gpt-4.1-mini"
    assert payload["api_key_masked"] == "••••cret"
    assert payload["has_api_key"] is True


@pytest.mark.asyncio
async def test_auth_allows_same_origin_browser_request():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/admin/auth",
            json={"api_key": "sk-admin"},
            headers={"Origin": str(client.make_url('/')).rstrip('/')},
        )
        payload = await response.json()

    assert response.status == 200
    assert payload["ok"] is True


@pytest.mark.asyncio
async def test_config_requires_admin_cookie():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/admin/config")
        payload = await response.json()

    assert response.status == 401
    assert payload["error"] == "admin_auth_required"


@pytest.mark.asyncio
async def test_profiles_list_and_create_flow():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        create_response = await client.post(
            "/api/admin/profiles",
            json={
                "name": "OpenAI Prod",
                "provider_type": "openai-compatible",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-live",
                "model_name": "gpt-4.1",
            },
        )
        list_response = await client.get("/api/admin/profiles")
        created = await create_response.json()
        listed = await list_response.json()

    assert create_response.status == 201
    assert created["api_key_masked"] == "••••live"
    assert listed["profiles"][0]["name"] == "OpenAI Prod"


@pytest.mark.asyncio
async def test_set_default_profile_updates_library():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    profile = adapter._admin_service.profiles.create_profile(
        name="Primary",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-primary",
        model_name="gpt-4.1",
    )
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post(f"/api/admin/profiles/{profile['id']}/default")
        payload = await response.json()

    assert response.status == 200
    assert payload["default_profile_id"] == profile["id"]


@pytest.mark.asyncio
async def test_activate_profile_uses_saved_profile(monkeypatch):
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    profile = adapter._admin_service.profiles.create_profile(
        name="Primary",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-primary",
        model_name="gpt-4.1",
    )
    monkeypatch.setattr(
        adapter._admin_service,
        "probe_provider",
        AsyncMock(return_value={"ok": True, "status": 200, "model_ids": ["gpt-4.1"], "model_name": "gpt-4.1"}),
    )
    monkeypatch.setattr(adapter._admin_service.storage, "sync_open_webui_config", lambda **kwargs: {"rewritten": True})
    restart_calls = []
    wait_calls = []
    monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
    monkeypatch.setattr(adapter._admin_service.runtime, "wait_for_service", lambda name, timeout_seconds=90, poll_interval=1.0: wait_calls.append(name))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post(f"/api/admin/profiles/{profile['id']}/activate")
        payload = await response.json()

    assert response.status == 202
    assert payload["phase"] == "ready"
    assert payload["active_profile_id"] == profile["id"]
    assert restart_calls == ["open-webui"]
    assert wait_calls == ["open-webui"]


@pytest.mark.asyncio
async def test_test_connection_uses_form_values(monkeypatch):
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})

        fake_probe = AsyncMock(
            return_value={"ok": True, "status": 200, "model_ids": ["gpt-4o-mini"], "model_name": "gpt-4o-mini"}
        )
        monkeypatch.setattr(adapter._admin_service, "probe_provider", fake_probe)

        response = await client.post(
            "/api/admin/test-connection",
            json={
                "provider": "openai",
                "api_key": "sk-live",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o-mini",
            },
        )
        payload = await response.json()

    assert response.status == 200
    assert payload["ok"] is True
    assert payload["model_ids"] == ["gpt-4o-mini"]
    fake_probe.assert_awaited_once_with(
        api_key="sk-live",
        base_url="https://api.openai.com/v1",
        model_name="gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_apply_writes_status_and_requests_restarts(monkeypatch):
    save_config(
        {
            "model": {
                "provider": "custom",
                "base_url": "https://old.example/v1",
                "default": "old-model",
            }
        }
    )
    save_env_value("OPENAI_API_KEY", "old-openai-key")

    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()

    restart_calls = []
    wait_calls = []
    monkeypatch.setattr(
        adapter._admin_service,
        "probe_provider",
        AsyncMock(return_value={"ok": True, "status": 200, "model_ids": ["gpt-4o-mini"], "model_name": "gpt-4o-mini"}),
    )
    monkeypatch.setattr(adapter._admin_service.storage, "sync_open_webui_config", lambda **kwargs: {"rewritten": True})
    monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
    monkeypatch.setattr(adapter._admin_service.runtime, "wait_for_service", lambda name, timeout_seconds=90, poll_interval=1.0: wait_calls.append(name))

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post(
            "/api/admin/apply",
            json={
                "provider": "openai",
                "api_key": "sk-new",
                "base_url": "https://api.openai.com/v1",
                "model_name": "gpt-4o-mini",
            },
        )
        payload = await response.json()

    status = adapter._admin_service.storage.status_store.read()
    config = load_config()
    env_vars = load_env()

    assert response.status == 202
    assert payload["ok"] is True
    assert payload["phase"] == "ready"
    assert restart_calls == ["open-webui"]
    assert wait_calls == ["open-webui"]
    assert status["phase"] == "ready"
    assert status["provider"] == "custom"
    assert config["model"]["provider"] == "custom"
    assert env_vars["OPENAI_API_KEY"] == "sk-new"


@pytest.mark.asyncio
async def test_activate_profile_rolls_back_when_webui_sync_fails(monkeypatch):
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    profile = adapter._admin_service.profiles.create_profile(
        name="Primary",
        provider_type="openai-compatible",
        base_url="https://api.openai.com/v1",
        api_key="sk-primary",
        model_name="gpt-4.1",
    )
    monkeypatch.setattr(
        adapter._admin_service,
        "probe_provider",
        AsyncMock(return_value={"ok": True, "status": 200, "model_ids": ["gpt-4.1"], "model_name": "gpt-4.1"}),
    )
    monkeypatch.setattr(
        adapter._admin_service.storage,
        "sync_open_webui_config",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sync failed")),
    )
    restore_calls = []
    monkeypatch.setattr(adapter._admin_service.storage, "restore_last_backup", lambda: restore_calls.append("restore"))
    restart_calls = []
    wait_calls = []
    monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
    monkeypatch.setattr(adapter._admin_service.runtime, "wait_for_service", lambda name, timeout_seconds=90, poll_interval=1.0: wait_calls.append(name))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post(f"/api/admin/profiles/{profile['id']}/activate")
        payload = await response.json()

    assert response.status == 500
    assert payload["phase"] == "failed"
    assert restore_calls == ["restore"]
    assert restart_calls == ["open-webui"]
    assert wait_calls == ["open-webui"]


def test_compose_mounts_required_admin_volumes():
    compose_text = Path('/Users/awk/lqf/hermes-agent/docker-compose.yml').read_text(encoding='utf-8')
    assert '/var/run/docker.sock:/var/run/docker.sock' in compose_text
    assert '${HERMES_DATA_ROOT:-./data}/open-webui:/opt/open-webui' in compose_text


@pytest.mark.asyncio
async def test_status_returns_persisted_state():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    adapter._admin_service.storage.status_store.write({"phase": "pending_verification", "provider": "custom"})
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.get("/api/admin/status")
        payload = await response.json()

    assert response.status == 200
    assert payload["phase"] in {"pending_verification", "ready"}


@pytest.mark.asyncio
async def test_restore_endpoint_restores_backup(monkeypatch):
    save_config({"model": {"provider": "custom", "base_url": "https://old.example/v1", "default": "old-model"}})
    save_env_value("OPENAI_API_KEY", "old-openai-key")

    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    adapter._admin_service.storage.backup_current_state()
    adapter._admin_service.storage.apply_provider_settings(
        provider="gemini",
        api_key="gemini-secret",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model_name="gemini-2.5-pro",
    )
    restart_calls = []
    wait_calls = []
    monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
    monkeypatch.setattr(adapter._admin_service.runtime, "wait_for_service", lambda name, timeout_seconds=90, poll_interval=1.0: wait_calls.append(name))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post("/api/admin/restore")
        payload = await response.json()

    config = load_config()
    env_vars = load_env()

    assert response.status == 200
    assert payload["ok"] is True
    assert payload["phase"] == "restored"
    assert restart_calls == ["open-webui"]
    assert wait_calls == ["open-webui"]
    assert config["model"]["provider"] == "custom"
    assert env_vars["OPENAI_API_KEY"] == "old-openai-key"
