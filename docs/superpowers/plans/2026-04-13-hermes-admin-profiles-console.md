# Hermes Admin Profiles Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a protected Hermes admin console with multi-profile upstream configuration, default-profile startup materialization, immediate profile activation, Open WebUI repair, and verified rollback-safe apply flows.

**Architecture:** Extend the existing single-profile admin skeleton into three focused layers: a profile-library store, a runtime/apply layer, and an embedded admin UI served by the API server. Keep Hermes runtime config in `config.yaml` and `.env`, keep profile-library state in `admin_profiles.json`, and keep Open WebUI permanently pointed at Hermes rather than any external provider URL.

**Tech Stack:** Python 3.12, `aiohttp`, `sqlite3`, existing Hermes config helpers, Docker Engine Unix socket API, embedded HTML/CSS/JS, `pytest`, `pytest-asyncio`.

---

## Working Context

- Workspace root: `/Users/awk/lqf/hermes-agent`
- Hermes source tree: `/Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src`
- Python commands below assume:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src
source venv/bin/activate
```

## File Map

- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_profiles.py`
  - Own `admin_profiles.json` CRUD, default/active metadata, profile masking, and profile lookup.

- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_bootstrap.py`
  - Own startup-time materialization of the default or last-known-good profile into runtime config.

- Create: `docker/hermes-agent/hermes-agent-src/tools/admin_profiles_bootstrap.py`
  - Thin executable shim that calls the bootstrap helper from the container entrypoint.

- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_ui.py`
  - Own the embedded HTML shell and client-side JS for profile CRUD, default selection, activate, rollback, and status polling.

- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
  - Keep runtime-file writes, backups, restore, Open WebUI sync, status persistence, and add profile-to-runtime materialization helpers.

- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
  - Replace the single-profile admin flow with profile-library-backed endpoints and shared apply orchestration.

- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py`
  - Wire new `/api/admin/profiles*` routes and keep the HTML root mounted.

- Modify: `docker/hermes-agent/hermes-agent-src/docker/entrypoint.sh`
  - Materialize the default profile before launching Hermes.

- Modify: `docker-compose.yml`
  - Ensure `hermes-agent` mounts `/var/run/docker.sock` so apply flows can restart sibling containers.

- Modify: `README.md`
  - Document the admin console, default profile behavior, and Open WebUI repair behavior.

- Create: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_profiles.py`
  - Cover profile-library CRUD and metadata transitions.

- Create: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_bootstrap.py`
  - Cover startup materialization and last-known-good fallback.

- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`
  - Cover profile routes, UI shell assertions, activate/default flows, and rollback behavior.

- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py`
  - Extend storage tests for profile materialization and Open WebUI sync invariants.

- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_docker.py`
  - Keep Docker restart helper tests aligned with the final route orchestration.

## Scope Note

This plan stays as one implementation plan because the new profile library, startup bootstrap, runtime apply, and admin UI all ship one operator-facing feature. The work is phased so each task produces a working slice without requiring the full feature set to be complete first.

### Task 1: Add profile-library storage and metadata management

**Files:**
- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_profiles.py`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_profiles.py`

- [ ] **Step 1: Write the failing profile-library tests**

```python
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
```

- [ ] **Step 2: Run the profile-library tests to verify they fail**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin_profiles.py -q
```

Expected: `ModuleNotFoundError` for `gateway.platforms.api_server_admin_profiles`.

- [ ] **Step 3: Implement the minimal profile-library module**

```python
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import atomic_json_write


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


class AdminProfilesStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read_document(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "version": 1,
                "default_profile_id": None,
                "active_profile_id": None,
                "last_known_good_profile_id": None,
                "profiles": [],
            }
        import json
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write_document(self, document: dict[str, Any]) -> None:
        atomic_json_write(self.path, document)

    def list_profiles(self) -> list[dict[str, Any]]:
        document = self.read_document()
        listed: list[dict[str, Any]] = []
        for profile in document["profiles"]:
            item = dict(profile)
            item["api_key_masked"] = _mask_secret(str(profile.get("api_key", "")))
            item.pop("api_key", None)
            listed.append(item)
        return listed

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        document = self.read_document()
        for profile in document["profiles"]:
            if profile["id"] == profile_id:
                return dict(profile)
        raise KeyError(profile_id)

    def create_profile(self, *, name: str, provider_type: str, base_url: str, api_key: str, model_name: str) -> dict[str, Any]:
        document = self.read_document()
        created = {
            "id": f"prof_{secrets.token_hex(6)}",
            "name": name,
            "provider_type": provider_type,
            "base_url": base_url,
            "api_key": api_key,
            "model_name": model_name,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "last_test_result": None,
        }
        document["profiles"].append(created)
        self._write_document(document)
        listed = dict(created)
        listed["api_key_masked"] = _mask_secret(api_key)
        listed.pop("api_key")
        return listed

    def update_profile(self, profile_id: str, **changes: Any) -> dict[str, Any]:
        document = self.read_document()
        for profile in document["profiles"]:
            if profile["id"] == profile_id:
                for key in ("name", "provider_type", "base_url", "api_key", "model_name", "last_test_result"):
                    if key in changes and changes[key] is not None:
                        profile[key] = changes[key]
                profile["updated_at"] = _utc_now()
                self._write_document(document)
                updated = dict(profile)
                updated["api_key_masked"] = _mask_secret(str(profile.get("api_key", "")))
                updated.pop("api_key", None)
                return updated
        raise KeyError(profile_id)

    def delete_profile(self, profile_id: str) -> None:
        document = self.read_document()
        document["profiles"] = [p for p in document["profiles"] if p["id"] != profile_id]
        for key in ("default_profile_id", "active_profile_id", "last_known_good_profile_id"):
            if document.get(key) == profile_id:
                document[key] = None
        self._write_document(document)

    def set_default_profile(self, profile_id: str) -> None:
        document = self.read_document()
        document["default_profile_id"] = profile_id
        self._write_document(document)

    def set_active_profile(self, profile_id: str | None) -> None:
        document = self.read_document()
        document["active_profile_id"] = profile_id
        self._write_document(document)

    def mark_last_known_good(self, profile_id: str | None) -> None:
        document = self.read_document()
        document["last_known_good_profile_id"] = profile_id
        self._write_document(document)
```

- [ ] **Step 4: Re-run the profile-library tests and get them green**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin_profiles.py -q
```

Expected: all tests in `test_api_server_admin_profiles.py` pass.

- [ ] **Step 5: Commit the profile-library slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git add gateway/platforms/api_server_admin_profiles.py tests/gateway/test_api_server_admin_profiles.py && git commit -m "feat: add hermes admin profile library"; fi
```

### Task 2: Materialize the default profile at startup

**Files:**
- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_bootstrap.py`
- Create: `docker/hermes-agent/hermes-agent-src/tools/admin_profiles_bootstrap.py`
- Modify: `docker/hermes-agent/hermes-agent-src/docker/entrypoint.sh`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_bootstrap.py`

- [ ] **Step 1: Write the failing startup-materialization tests**

```python
from gateway.platforms.api_server_admin_bootstrap import materialize_default_profile_if_present
from gateway.platforms.api_server_admin_profiles import AdminProfilesStore
from hermes_cli.config import load_config, load_env


def test_materialize_default_profile_into_runtime(tmp_path):
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


def test_materialize_uses_last_known_good_when_default_missing(tmp_path):
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


def test_materialize_noops_when_profile_library_missing(tmp_path):
    result = materialize_default_profile_if_present(tmp_path)
    assert result == {"applied": False, "reason": "profile_library_missing"}
```

- [ ] **Step 2: Run the startup-materialization tests to verify they fail**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin_bootstrap.py -q
```

Expected: `ModuleNotFoundError` for `gateway.platforms.api_server_admin_bootstrap`.

- [ ] **Step 3: Implement default-profile bootstrap and the entrypoint shim**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway.platforms.api_server_admin_profiles import AdminProfilesStore
from gateway.platforms.api_server_admin_storage import HermesAdminStorage


def materialize_default_profile_if_present(hermes_home: str | Path) -> dict[str, Any]:
    hermes_home = Path(hermes_home)
    profiles_path = hermes_home / "admin_profiles.json"
    if not profiles_path.exists():
        return {"applied": False, "reason": "profile_library_missing"}

    store = AdminProfilesStore(profiles_path)
    storage = HermesAdminStorage(hermes_home=hermes_home)
    document = store.read_document()
    selected_id = document.get("default_profile_id") or document.get("last_known_good_profile_id")
    if not selected_id:
        return {"applied": False, "reason": "no_default_profile"}

    try:
        profile = store.get_profile(selected_id)
    except KeyError:
        fallback_id = document.get("last_known_good_profile_id")
        if not fallback_id or fallback_id == selected_id:
            return {"applied": False, "reason": "selected_profile_missing"}
        profile = store.get_profile(fallback_id)
        selected_id = fallback_id

    storage.apply_profile_record(profile)
    store.set_active_profile(selected_id)
    return {"applied": True, "profile_id": selected_id}
```

Add the thin script:

```python
from pathlib import Path
import os

from gateway.platforms.api_server_admin_bootstrap import materialize_default_profile_if_present


if __name__ == "__main__":
    hermes_home = Path(os.getenv("HERMES_HOME", "/opt/data"))
    materialize_default_profile_if_present(hermes_home)
```

Add the storage helper used by bootstrap:

```python
class HermesAdminStorage:
    ...
    def apply_profile_record(self, profile: dict[str, Any]) -> dict[str, str]:
        provider_type = str(profile.get("provider_type") or "openai-compatible").strip().lower()
        provider = "openai" if provider_type in ("openai", "openai-compatible", "custom") else provider_type
        return self.apply_provider_settings(
            provider=provider,
            api_key=str(profile.get("api_key", "")),
            base_url=str(profile.get("base_url", "")),
            model_name=str(profile.get("model_name", "")),
        )
```

Patch `docker/entrypoint.sh` before `exec hermes "$@"`:

```bash
python3 "$INSTALL_DIR/tools/admin_profiles_bootstrap.py" || true
```

- [ ] **Step 4: Re-run the bootstrap tests and get them green**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin_bootstrap.py -q
```

Expected: all tests in `test_api_server_admin_bootstrap.py` pass.

- [ ] **Step 5: Commit the bootstrap slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git add gateway/platforms/api_server_admin_bootstrap.py gateway/platforms/api_server_admin_storage.py tools/admin_profiles_bootstrap.py docker/entrypoint.sh tests/gateway/test_api_server_admin_bootstrap.py && git commit -m "feat: materialize default admin profile on startup"; fi
```

### Task 3: Add profile-backed admin API routes and activation flow

**Files:**
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py`

- [ ] **Step 1: Write failing tests for profile CRUD, default, and activation**

```python
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
    monkeypatch.setattr(adapter._admin_service, "probe_provider", AsyncMock(return_value={"ok": True, "status": 200, "model_ids": ["gpt-4.1"], "model_name": "gpt-4.1"}))
    monkeypatch.setattr(adapter._admin_service.storage, "sync_open_webui_config", lambda **kwargs: {"rewritten": True})
    restart_calls = []
    monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post(f"/api/admin/profiles/{profile['id']}/activate")
        payload = await response.json()

    assert response.status == 202
    assert payload["active_profile_id"] == profile["id"]
    assert restart_calls == ["hermes-agent", "open-webui"]
```

- [ ] **Step 2: Run the profile-route tests to verify they fail**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin.py -q
```

Expected: 404 route failures or missing `profiles` attribute on the admin service.

- [ ] **Step 3: Implement profile-backed routes and shared activation logic**

```python
from gateway.platforms.api_server_admin_profiles import AdminProfilesStore


class APIServerAdminService:
    def __init__(self, adapter):
        self.adapter = adapter
        self.storage = HermesAdminStorage()
        self.runtime = DockerComposeRuntime()
        self.sessions = AdminSessionStore()
        self.profiles = AdminProfilesStore(self.storage.hermes_home / "admin_profiles.json")

    async def handle_list_profiles(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        document = self.profiles.read_document()
        return web.json_response(
            {
                "profiles": self.profiles.list_profiles(),
                "default_profile_id": document.get("default_profile_id"),
                "active_profile_id": document.get("active_profile_id"),
                "last_known_good_profile_id": document.get("last_known_good_profile_id"),
            }
        )

    async def handle_create_profile(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        payload = await request.json()
        created = self.profiles.create_profile(
            name=str(payload["name"]),
            provider_type=str(payload.get("provider_type", "openai-compatible")),
            base_url=str(payload["base_url"]),
            api_key=str(payload["api_key"]),
            model_name=str(payload["model_name"]),
        )
        return web.json_response(created, status=201)

    async def handle_update_profile(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        profile_id = request.match_info["profile_id"]
        payload = await request.json()
        updated = self.profiles.update_profile(profile_id, **payload)
        return web.json_response(updated)

    async def handle_delete_profile(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        self.profiles.delete_profile(request.match_info["profile_id"])
        return web.json_response({"ok": True})

    async def handle_test_profile(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        profile = self.profiles.get_profile(request.match_info["profile_id"])
        result = await self.probe_provider(
            api_key=str(profile.get("api_key", "")),
            base_url=str(profile.get("base_url", "")),
            model_name=str(profile.get("model_name", "")),
        )
        self.profiles.update_profile(profile["id"], last_test_result=result)
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def handle_set_default_profile(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        profile_id = request.match_info["profile_id"]
        self.profiles.set_default_profile(profile_id)
        document = self.profiles.read_document()
        return web.json_response({"default_profile_id": document["default_profile_id"]})

    async def handle_activate_profile(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        profile = self.profiles.get_profile(request.match_info["profile_id"])
        return await self._activate_profile(profile)

    async def _activate_profile(self, profile: dict[str, Any]) -> web.Response:
        probe = await self.probe_provider(
            api_key=str(profile.get("api_key", "")),
            base_url=str(profile.get("base_url", "")),
            model_name=str(profile.get("model_name", "")),
        )
        if not probe.get("ok"):
            return web.json_response({"ok": False, "phase": "probe_failed", "probe": probe}, status=400)
        self.storage.backup_current_state()
        self.storage.apply_profile_record(profile)
        self.storage.status_store.write({"phase": "restarting_hermes", "profile_id": profile["id"]})
        self.runtime.restart_service("hermes-agent")
        self.storage.sync_open_webui_config(db_path=self._open_webui_db_path(), api_key=self.adapter._api_key)
        self.storage.status_store.write({"phase": "restarting_open_webui", "profile_id": profile["id"]})
        self.runtime.restart_service("open-webui")
        self.profiles.set_active_profile(profile["id"])
        self.profiles.mark_last_known_good(profile["id"])
        self.storage.status_store.write({"phase": "pending_verification", "profile_id": profile["id"]})
        return web.json_response({"ok": True, "phase": "pending_verification", "active_profile_id": profile["id"]}, status=202)
```

Wire the routes in `api_server.py`:

```python
app.router.add_get("/api/admin/profiles", self._admin_service.handle_list_profiles)
app.router.add_post("/api/admin/profiles", self._admin_service.handle_create_profile)
app.router.add_patch("/api/admin/profiles/{profile_id}", self._admin_service.handle_update_profile)
app.router.add_delete("/api/admin/profiles/{profile_id}", self._admin_service.handle_delete_profile)
app.router.add_post("/api/admin/profiles/{profile_id}/test", self._admin_service.handle_test_profile)
app.router.add_post("/api/admin/profiles/{profile_id}/default", self._admin_service.handle_set_default_profile)
app.router.add_post("/api/admin/profiles/{profile_id}/activate", self._admin_service.handle_activate_profile)
```

- [ ] **Step 4: Re-run the profile-route tests and get them green**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin.py tests/gateway/test_api_server_admin_storage.py -q
```

Expected: profile CRUD/default/activate tests pass.

- [ ] **Step 5: Commit the API slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git add gateway/platforms/api_server.py gateway/platforms/api_server_admin.py gateway/platforms/api_server_admin_storage.py tests/gateway/test_api_server_admin.py tests/gateway/test_api_server_admin_storage.py && git commit -m "feat: add profile-backed hermes admin API"; fi
```

### Task 4: Build the embedded multi-profile admin UI

**Files:**
- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_ui.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`

- [ ] **Step 1: Write the failing UI-shell assertions**

```python
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
    assert "Set as Default" in body
    assert "Apply Now" in body
    assert "Rollback Previous Runtime" in body
```

- [ ] **Step 2: Run the UI-shell tests and verify they fail**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin.py::test_root_contains_profiles_console_shell -q
```

Expected: HTML assertion failure because the root shell still contains only the basic auth form.

- [ ] **Step 3: Implement the embedded HTML/CSS/JS shell**

```python
from __future__ import annotations


def render_admin_shell() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Hermes Config Console</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #f5f7fb; color: #111827; }
    .layout { display: grid; grid-template-columns: 320px 1fr; min-height: 100vh; }
    aside, main { padding: 24px; }
    .card { background: #fff; border-radius: 16px; padding: 16px; box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08); }
    .stack { display: grid; gap: 12px; }
    input, select, button, textarea { font: inherit; }
  </style>
</head>
<body>
  <div id=\"locked-view\" class=\"card\">
    <h1>Hermes Config Console</h1>
    <label>Current HERMES_API_KEY <input id=\"unlock-key\" type=\"password\"></label>
    <button id=\"unlock-button\">Enter Console</button>
  </div>
  <div id=\"app\" class=\"layout\" hidden>
    <aside>
      <div class=\"card stack\">
        <div id=\"profiles-list\"></div>
        <button id=\"new-profile\">New Profile</button>
      </div>
    </aside>
    <main class=\"stack\">
      <section class=\"card\" id=\"status-panel\"></section>
      <section class=\"card\">
        <form id=\"profile-form\" class=\"stack\">
          <input name=\"name\" placeholder=\"Profile Name\">
          <select name=\"provider_type\"><option value=\"openai-compatible\">OpenAI-compatible</option></select>
          <input name=\"base_url\" placeholder=\"Base URL\">
          <input name=\"api_key\" type=\"password\" placeholder=\"API Key\">
          <input name=\"model_name\" placeholder=\"Model Name\">
          <div class=\"stack\">
            <button type=\"button\" id=\"test-connection\">Test Connection</button>
            <button type=\"button\" id=\"save-profile\">Save</button>
            <button type=\"button\" id=\"set-default\">Set as Default</button>
            <button type=\"button\" id=\"apply-profile\">Apply Now</button>
            <button type=\"button\" id=\"rollback-runtime\">Rollback Previous Runtime</button>
          </div>
        </form>
      </section>
      <section class=\"card\" id=\"operation-log\"></section>
    </main>
  </div>
  <script>
    async function api(path, options = {}) {
      const response = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...options });
      if (response.status === 204) return null;
      return { status: response.status, data: await response.json() };
    }
    async function loadProfiles() { return api('/api/admin/profiles'); }
    async function loadStatus() { return api('/api/admin/status'); }
    async function testSelectedProfile(profileId) { return api(`/api/admin/profiles/${profileId}/test`, { method: 'POST' }); }
    async function setDefaultProfile(profileId) { return api(`/api/admin/profiles/${profileId}/default`, { method: 'POST' }); }
    async function activateProfile(profileId) { return api(`/api/admin/profiles/${profileId}/activate`, { method: 'POST' }); }
    async function rollbackRuntime() { return api('/api/admin/restore', { method: 'POST' }); }
  </script>
</body>
</html>"""
```

Then use it in `api_server_admin.py`:

```python
from gateway.platforms.api_server_admin_ui import render_admin_shell


async def handle_root(self, request: web.Request) -> web.Response:
    return web.Response(text=render_admin_shell(), content_type="text/html")
```

- [ ] **Step 4: Re-run the UI-shell tests and get them green**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin.py -q
```

Expected: root-shell assertions pass with the profile console HTML in place.

- [ ] **Step 5: Commit the UI slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git add gateway/platforms/api_server_admin.py gateway/platforms/api_server_admin_ui.py tests/gateway/test_api_server_admin.py && git commit -m "feat: add multi-profile admin console UI"; fi
```

### Task 5: Finish rollback-safe activation, deployment wiring, and docs

**Files:**
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`

- [ ] **Step 1: Write the failing rollback and deployment-surface tests**

```python
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
    monkeypatch.setattr(adapter._admin_service, "probe_provider", AsyncMock(return_value={"ok": True, "status": 200, "model_ids": ["gpt-4.1"], "model_name": "gpt-4.1"}))
    monkeypatch.setattr(adapter._admin_service.storage, "sync_open_webui_config", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sync failed")))
    restore_calls = []
    monkeypatch.setattr(adapter._admin_service.storage, "restore_last_backup", lambda: restore_calls.append("restore"))
    restart_calls = []
    monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
    app = adapter._build_test_app()

    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post(f"/api/admin/profiles/{profile['id']}/activate")
        payload = await response.json()

    assert response.status == 500
    assert payload["phase"] == "failed"
    assert restore_calls == ["restore"]
    assert restart_calls[-2:] == ["hermes-agent", "open-webui"]


def test_compose_mounts_docker_socket():
    compose_text = Path("/Users/awk/lqf/hermes-agent/docker-compose.yml").read_text(encoding="utf-8")
    assert "/var/run/docker.sock:/var/run/docker.sock" in compose_text
```

- [ ] **Step 2: Run the rollback/deployment tests and verify they fail**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_admin.py tests/gateway/test_api_server_admin_storage.py -q
```

Expected: activate-flow rollback assertion failures or missing rollback status behavior.

- [ ] **Step 3: Implement rollback-safe activation and document the deployment behavior**

```python
class APIServerAdminService:
    ...
    async def _activate_profile(self, profile: dict[str, Any]) -> web.Response:
        probe = await self.probe_provider(
            api_key=str(profile.get("api_key", "")),
            base_url=str(profile.get("base_url", "")),
            model_name=str(profile.get("model_name", "")),
        )
        if not probe.get("ok"):
            return web.json_response({"ok": False, "phase": "probe_failed", "probe": probe}, status=400)

        self.storage.backup_current_state()
        try:
            self.storage.status_store.write({"phase": "writing_runtime_config", "profile_id": profile["id"]})
            self.storage.apply_profile_record(profile)
            self.storage.status_store.write({"phase": "restarting_hermes", "profile_id": profile["id"]})
            self.runtime.restart_service("hermes-agent")
            self.storage.status_store.write({"phase": "verifying_hermes", "profile_id": profile["id"]})
            verified = await self._verify_after_restart({"phase": "pending_verification", "profile_id": profile["id"]})
            if verified.get("phase") != "ready":
                raise RuntimeError("hermes verification failed")
            self.storage.status_store.write({"phase": "syncing_open_webui", "profile_id": profile["id"]})
            self.storage.sync_open_webui_config(db_path=self._open_webui_db_path(), api_key=self.adapter._api_key)
            self.storage.status_store.write({"phase": "restarting_open_webui", "profile_id": profile["id"]})
            self.runtime.restart_service("open-webui")
            self.profiles.set_active_profile(profile["id"])
            self.profiles.mark_last_known_good(profile["id"])
            self.storage.status_store.write({"phase": "ready", "profile_id": profile["id"]})
            return web.json_response({"ok": True, "phase": "ready", "active_profile_id": profile["id"]}, status=202)
        except Exception as exc:
            self.storage.restore_last_backup()
            self.runtime.restart_service("hermes-agent")
            self.runtime.restart_service("open-webui")
            self.storage.status_store.write({"phase": "rollback_complete", "profile_id": profile.get("id"), "error": str(exc)})
            return web.json_response({"ok": False, "phase": "failed", "error": str(exc)}, status=500)
```

Update `docker-compose.yml`:

```yaml
services:
  hermes-agent:
    volumes:
      - ${HERMES_DATA_ROOT:-./data}/hermes:/opt/data
      - /var/run/docker.sock:/var/run/docker.sock
```

Update `README.md` with the operator-facing behavior:

```md
## 配置控制台

- 控制台入口：`http://localhost:18642/`
- 登录口令：`.env` 里的 `HERMES_API_KEY`
- 支持多套上游配置档案、默认档案、当前生效档案
- `Apply Now` 会更新 Hermes 运行配置、修复 Open WebUI 连接、重启服务并做健康检查
- Open WebUI 始终连接 `http://hermes-agent:8642/v1`，不会直接连接外部 OpenAI URL
```

- [ ] **Step 4: Run the full admin test suite and then a local stack verification**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server.py tests/gateway/test_api_server_admin.py tests/gateway/test_api_server_admin_storage.py tests/gateway/test_api_server_admin_docker.py tests/gateway/test_api_server_admin_profiles.py tests/gateway/test_api_server_admin_bootstrap.py -q
```

Expected: all targeted admin and API-server tests pass.

Then run the deployment verification:

```bash
cd /Users/awk/lqf/hermes-agent && docker compose up -d --build && curl -sS http://localhost:18642/ | head -20 && export $(grep '^HERMES_API_KEY=' .env | xargs) && curl -sS -H "Authorization: Bearer $HERMES_API_KEY" http://localhost:18642/v1/models && sqlite3 data/open-webui/webui.db "select json_extract(data,'$.openai.api_base_urls[0]') from config limit 1;"
```

Expected:

- root HTML contains `Hermes Config Console`
- `/v1/models` returns at least one model object
- Open WebUI DB points at `http://hermes-agent:8642/v1`

- [ ] **Step 5: Commit the final deployment slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent && if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git add docker-compose.yml README.md docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_profiles.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_bootstrap.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_ui.py docker/hermes-agent/hermes-agent-src/tools/admin_profiles_bootstrap.py docker/hermes-agent/hermes-agent-src/docker/entrypoint.sh docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_docker.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_profiles.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_bootstrap.py && git commit -m "feat: add hermes multi-profile admin console"; fi
```

## Self-Review

### Spec coverage

- local protected admin console: Tasks 3 and 4
- multiple profiles and metadata: Task 1
- default profile used at startup: Task 2
- active profile immediate apply: Task 3
- Open WebUI fixed to Hermes: Tasks 3 and 5
- automatic restart and health verification: Tasks 3 and 5
- rollback and last-known-good behavior: Task 5
- docs and deployment socket mount: Task 5

### Placeholder scan

- No `TODO`, `TBD`, or “handle later” placeholders remain.
- Every task names exact files, test commands, and concrete code seams.
- Every task includes a red-green verification loop.

### Type consistency

- `AdminProfilesStore` owns the profile library only.
- `HermesAdminStorage` owns runtime files, backups, status, and WebUI sync.
- `materialize_default_profile_if_present()` is the only startup bootstrap entry.
- `APIServerAdminService` remains the route/orchestration layer.
- `render_admin_shell()` is the only embedded UI entry point.

Plan complete and saved to `docs/superpowers/plans/2026-04-13-hermes-admin-profiles-console.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
