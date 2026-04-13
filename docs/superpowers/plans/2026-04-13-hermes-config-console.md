# Hermes Config Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the API server root JSON overview with a protected local config console that updates Hermes provider settings, repairs Open WebUI’s upstream target, and makes the stack recover to a working model list without manual file or database edits.

**Architecture:** Add an embedded admin console layer to the API server using server-rendered HTML plus `/api/admin/*` JSON endpoints. Persist Hermes changes through existing `hermes_cli.config` helpers, rewrite the mounted `data/open-webui/webui.db` config JSON via `sqlite3`, and persist apply state to disk so the system can resume verification after a self-triggered container restart. Mount the Docker Engine socket into the Hermes container and call the Docker HTTP API over the Unix socket so the admin flow can restart `open-webui` and then `hermes-agent` from inside the standalone stack.

**Tech Stack:** Python 3.12, `aiohttp`, `sqlite3`, existing Hermes config helpers, Docker Engine Unix socket API, embedded HTML/CSS/JS, `pytest`, `aiohttp.test_utils`.

---

## Working Context

- Workspace root: `/Users/awk/lqf/hermes-agent`
- Hermes source tree: `docker/hermes-agent/hermes-agent-src`
- Python commands below assume:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src
source venv/bin/activate
```

## File Map

- Modify: `docker-compose.yml`
  - Mount `/var/run/docker.sock` into the `hermes-agent` service so the admin flow can restart sibling containers through the Docker API.

- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py`
  - Delegate `/` to the admin HTML shell.
  - Register `/api/admin/auth`, `/api/admin/config`, `/api/admin/test-connection`, `/api/admin/apply`, `/api/admin/status`, and `/api/admin/restore`.
  - Instantiate the admin service once per adapter and expose it to handlers.

- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
  - Own the HTML shell, auth-cookie validation, request parsing, masked config summaries, provider connection test logic, and orchestration for apply/restore/status endpoints.

- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
  - Own backup/restore, YAML mutation, `.env` mutation, persisted apply-status reads/writes, and Open WebUI SQLite rewrites.

- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_docker.py`
  - Own Docker Unix-socket requests, compose-project discovery from the current container, and `restart_service(service_name)` helpers.

- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server.py`
  - Update the root-route expectation from JSON to HTML.

- Create: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py`
  - Cover config/env persistence, backup/restore, status persistence, and Open WebUI config rewrites.

- Create: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`
  - Cover HTML shell, auth, masked config reads, connection testing, apply/restore/status flows, and restart orchestration stubs.

- Create: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_docker.py`
  - Cover Docker API discovery and restart behavior without touching the real daemon.

- Modify: `README.md`
  - Document the config console URL, authentication model, and Docker socket requirement in this standalone deployment.

### Task 1: Add admin storage primitives

**Files:**
- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from pathlib import Path

from gateway.platforms.api_server_admin_storage import (
    AdminApplyStatusStore,
    HermesAdminStorage,
)


def test_write_provider_config_updates_yaml_and_env(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    (hermes_home / "config.yaml").write_text(
        "model:\n  provider: custom\n  base_url: https://old.example/v1\n  default: old-model\n",
        encoding="utf-8",
    )
    (hermes_home / ".env").write_text(
        "OPENAI_API_KEY=old-key\nOPENROUTER_API_KEY=stale-openrouter\n",
        encoding="utf-8",
    )

    storage = HermesAdminStorage(hermes_home=hermes_home)
    summary = storage.apply_provider_settings(
        provider="openrouter",
        api_key="or-key",
        base_url="https://openrouter.ai/api/v1",
        model_name="openai/gpt-4.1-mini",
    )

    config_text = (hermes_home / "config.yaml").read_text(encoding="utf-8")
    env_text = (hermes_home / ".env").read_text(encoding="utf-8")
    assert "provider: openrouter" in config_text
    assert "base_url: https://openrouter.ai/api/v1" in config_text
    assert "default: openai/gpt-4.1-mini" in config_text
    assert "OPENROUTER_API_KEY=or-key" in env_text
    assert "OPENAI_API_KEY" not in env_text
    assert summary["provider"] == "openrouter"
    assert summary["api_key_masked"] == "••••key"


def test_backup_and_restore_round_trip(tmp_path, monkeypatch):
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    (hermes_home / "config.yaml").write_text("model:\n  default: before\n", encoding="utf-8")
    (hermes_home / ".env").write_text("OPENAI_API_KEY=before\n", encoding="utf-8")

    storage = HermesAdminStorage(hermes_home=hermes_home)
    backup = storage.backup_current_state()
    (hermes_home / "config.yaml").write_text("model:\n  default: after\n", encoding="utf-8")
    (hermes_home / ".env").write_text("OPENAI_API_KEY=after\n", encoding="utf-8")

    storage.restore_last_backup()

    assert "before" in (hermes_home / "config.yaml").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=before" in (hermes_home / ".env").read_text(encoding="utf-8")
    assert backup["config_backup_path"].endswith("config.yaml.bak")


def test_status_store_round_trip(tmp_path):
    store = AdminApplyStatusStore(tmp_path / "admin_apply_status.json")
    store.write({"phase": "pending_restart", "provider": "gemini"})
    assert store.read()["provider"] == "gemini"
```

- [ ] **Step 2: Run the storage tests to prove the gap**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server_admin_storage.py -q
```

Expected: `ModuleNotFoundError` or import failures for `gateway.platforms.api_server_admin_storage`.

- [ ] **Step 3: Implement the storage module minimally**

```python
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hermes_cli.config import (
    get_config_path,
    get_env_path,
    load_config,
    remove_env_value,
    save_config,
    save_env_value,
)


_PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "custom": "OPENAI_API_KEY",
}


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    return f"••••{value[-3:]}" if len(value) <= 6 else f"••••{value[-4:]}"


@dataclass
class AdminApplyStatusStore:
    path: Path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"phase": "idle"}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class HermesAdminStorage:
    def __init__(self, hermes_home: Path | None = None):
        self.hermes_home = Path(hermes_home) if hermes_home else get_config_path().parent
        self.status_store = AdminApplyStatusStore(self.hermes_home / "admin_apply_status.json")

    def backup_current_state(self) -> dict[str, str]:
        config_src = self.hermes_home / "config.yaml"
        env_src = self.hermes_home / ".env"
        config_backup = self.hermes_home / "config.yaml.bak"
        env_backup = self.hermes_home / ".env.bak"
        if config_src.exists():
            shutil.copy2(config_src, config_backup)
        if env_src.exists():
            shutil.copy2(env_src, env_backup)
        return {
            "config_backup_path": str(config_backup),
            "env_backup_path": str(env_backup),
        }

    def apply_provider_settings(self, *, provider: str, api_key: str, base_url: str, model_name: str) -> dict[str, Any]:
        config = load_config()
        model_cfg = dict(config.get("model", {}))
        model_cfg["provider"] = provider
        model_cfg["base_url"] = base_url
        model_cfg["default"] = model_name
        config["model"] = model_cfg
        save_config(config)

        selected_key = _PROVIDER_ENV_KEYS[provider]
        for key_name in sorted(set(_PROVIDER_ENV_KEYS.values())):
            if key_name == selected_key:
                save_env_value(key_name, api_key)
            else:
                remove_env_value(key_name)

        return {
            "provider": provider,
            "base_url": base_url,
            "model": model_name,
            "api_key_masked": _mask_secret(api_key),
        }

    def restore_last_backup(self) -> None:
        shutil.copy2(self.hermes_home / "config.yaml.bak", self.hermes_home / "config.yaml")
        shutil.copy2(self.hermes_home / ".env.bak", self.hermes_home / ".env")
```

- [ ] **Step 4: Re-run the storage tests and get them green**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server_admin_storage.py -q
```

Expected: all tests in `test_api_server_admin_storage.py` pass.

- [ ] **Step 5: Commit the storage slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent && test -d .git && git add docs/superpowers/plans/2026-04-13-hermes-config-console.md docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py && git commit -m "feat: add hermes admin storage primitives" || true
```

### Task 2: Add Open WebUI sync and Docker restart helpers

**Files:**
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_docker.py`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_docker.py`

- [ ] **Step 1: Write failing tests for SQLite sync and Docker discovery**

```python
import json
import sqlite3

from gateway.platforms.api_server_admin_docker import DockerComposeRuntime
from gateway.platforms.api_server_admin_storage import HermesAdminStorage


def test_sync_open_webui_config_rewrites_stale_target(tmp_path):
    db_path = tmp_path / "webui.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE config (id INTEGER PRIMARY KEY, data JSON NOT NULL, version INTEGER NOT NULL)")
    payload = {
        "version": 0,
        "openai": {
            "enable": True,
            "api_base_urls": ["http://openclaw-hermes-agent:8642/v1"],
            "api_keys": ["old-secret"],
            "api_configs": {"0": {"enable": True, "connection_type": "external", "auth_type": "bearer", "model_ids": [], "tags": [], "prefix_id": ""}},
        },
    }
    conn.execute("INSERT INTO config (id, data, version) VALUES (1, ?, 0)", (json.dumps(payload),))
    conn.commit()
    conn.close()

    storage = HermesAdminStorage(hermes_home=tmp_path)
    summary = storage.sync_open_webui_config(db_path=db_path, api_key="new-secret")

    updated = json.loads(sqlite3.connect(db_path).execute("SELECT data FROM config WHERE id = 1").fetchone()[0])
    assert updated["openai"]["api_base_urls"] == ["http://hermes-agent:8642/v1"]
    assert updated["openai"]["api_keys"] == ["new-secret"]
    assert summary["rewritten"] is True


def test_discover_services_uses_compose_labels(monkeypatch):
    runtime = DockerComposeRuntime(socket_path="/var/run/docker.sock")

    def fake_request(method, path):
        if path == "/containers/self-id/json":
            return {
                "Config": {},
                "Config.Labels": {},
                "Name": "/hermes_agent-hermes-agent-1",
                "Config": {"Labels": {"com.docker.compose.project": "hermes_agent"}},
            }
        if path.startswith("/containers/json"):
            return [
                {"Names": ["/hermes_agent-hermes-agent-1"], "Labels": {"com.docker.compose.service": "hermes-agent"}},
                {"Names": ["/hermes_agent-open-webui-1"], "Labels": {"com.docker.compose.service": "open-webui"}},
            ]
        raise AssertionError(path)

    monkeypatch.setattr(runtime, "_request_json", fake_request)
    monkeypatch.setenv("HOSTNAME", "self-id")
    services = runtime.discover_services()

    assert services["hermes-agent"] == "hermes_agent-hermes-agent-1"
    assert services["open-webui"] == "hermes_agent-open-webui-1"
```

- [ ] **Step 2: Run the new focused tests and confirm failure**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server_admin_storage.py tests/gateway/test_api_server_admin_docker.py -q
```

Expected: failures for missing `sync_open_webui_config`, missing Docker runtime, or wrong rewrite behavior.

- [ ] **Step 3: Implement SQLite sync and Docker Unix-socket helpers**

```python
import json
import os
import socket
import sqlite3
from pathlib import Path
from urllib.parse import quote


class HermesAdminStorage:
    def sync_open_webui_config(self, *, db_path: Path, api_key: str) -> dict[str, object]:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT id, data FROM config ORDER BY id LIMIT 1").fetchone()
            payload = json.loads(row[1]) if row else {"version": 0}
            openai_cfg = dict(payload.get("openai", {}))
            openai_cfg["enable"] = True
            openai_cfg["api_base_urls"] = ["http://hermes-agent:8642/v1"]
            openai_cfg["api_keys"] = [api_key]
            api_configs = dict(openai_cfg.get("api_configs", {}))
            api_configs["0"] = {
                "enable": True,
                "tags": [],
                "prefix_id": "",
                "model_ids": [],
                "connection_type": "external",
                "auth_type": "bearer",
            }
            openai_cfg["api_configs"] = api_configs
            payload["openai"] = openai_cfg
            backup_path = self.hermes_home / "open_webui_config.bak.json"
            backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            conn.execute("UPDATE config SET data = ? WHERE id = ?", (json.dumps(payload), row[0]))
            conn.commit()
            return {"rewritten": True, "db_path": str(db_path), "backup_path": str(backup_path)}
        finally:
            conn.close()


class DockerComposeRuntime:
    def __init__(self, socket_path: str = "/var/run/docker.sock"):
        self.socket_path = socket_path

    def _request_json(self, method: str, path: str):
        request = f"{method} {path} HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n".encode("utf-8")
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(self.socket_path)
        try:
            client.sendall(request)
            response = b""
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                response += chunk
        finally:
            client.close()
        body = response.split(b"\r\n\r\n", 1)[1]
        return json.loads(body.decode("utf-8")) if body else {}

    def discover_services(self) -> dict[str, str]:
        container_id = os.environ["HOSTNAME"]
        current = self._request_json("GET", f"/containers/{container_id}/json")
        project = current["Config"]["Labels"]["com.docker.compose.project"]
        filters = quote(json.dumps({"label": [f"com.docker.compose.project={project}"]}))
        containers = self._request_json("GET", f"/containers/json?all=1&filters={filters}")
        return {
            item["Labels"]["com.docker.compose.service"]: item["Names"][0].lstrip("/")
            for item in containers
        }

    def restart_service(self, service_name: str) -> None:
        services = self.discover_services()
        container_name = services[service_name]
        self._request_json("POST", f"/containers/{container_name}/restart?t=2")
```

- [ ] **Step 4: Re-run the sync/runtime tests and make them pass**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server_admin_storage.py tests/gateway/test_api_server_admin_docker.py -q
```

Expected: both files pass.

- [ ] **Step 5: Commit the sync/runtime slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent && test -d .git && git add docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_docker.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_storage.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin_docker.py && git commit -m "feat: add webui sync and docker restart helpers" || true
```

### Task 3: Add the protected admin console routes

**Files:**
- Create: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py`
- Modify: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server.py`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`

- [ ] **Step 1: Write failing tests for HTML shell, auth, and config summary**

```python
from aiohttp.test_utils import TestClient, TestServer

from gateway.platforms.api_server import APIServerAdapter
from gateway.config import PlatformConfig


async def test_root_returns_html_shell():
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/")
        body = await response.text()
        assert response.status == 200
        assert response.content_type == "text/html"
        assert "Hermes Config Console" in body
        assert "Enter Console" in body


async def test_auth_sets_cookie_and_config_masks_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("model:\n  provider: openrouter\n  base_url: https://openrouter.ai/api/v1\n  default: openai/gpt-4.1-mini\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=real-secret\n", encoding="utf-8")
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()
    async with TestClient(TestServer(app)) as client:
        auth = await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        assert auth.status == 200
        assert "hermes_admin_session" in auth.cookies
        config = await client.get("/api/admin/config")
        payload = await config.json()
        assert payload["provider"] == "openrouter"
        assert payload["api_key_masked"] == "••••cret"
```

- [ ] **Step 2: Run the admin-route tests and confirm red**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server.py tests/gateway/test_api_server_admin.py -q
```

Expected: failures because the root still returns JSON and the admin module/routes do not exist.

- [ ] **Step 3: Implement auth, HTML, and route wiring**

```python
from __future__ import annotations

import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from gateway.platforms.api_server_admin_storage import HermesAdminStorage


ADMIN_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Hermes Config Console</title></head>
<body>
  <main>
    <h1>Hermes Config Console</h1>
    <form id="auth-form"><label>Current HERMES_API_KEY<input type="password" name="api_key"></label><button type="submit">Enter Console</button></form>
    <section id="status"></section>
    <section id="console" hidden></section>
  </main>
</body>
</html>"""


@dataclass
class AdminSessionStore:
    api_key: str
    ttl_seconds: int = 1800
    _tokens: dict[str, float] = field(default_factory=dict)

    def issue(self) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = time.time() + self.ttl_seconds
        return token

    def validate(self, token: str) -> bool:
        expires_at = self._tokens.get(token, 0)
        if expires_at < time.time():
            self._tokens.pop(token, None)
            return False
        return True


class APIServerAdminService:
    def __init__(self, adapter):
        self.adapter = adapter
        self.storage = HermesAdminStorage()
        self.sessions = AdminSessionStore(api_key=adapter._api_key)

    def _require_admin(self, request: web.Request) -> web.Response | None:
        token = request.cookies.get("hermes_admin_session", "")
        if self.sessions.validate(token):
            return None
        return web.json_response({"error": "admin_auth_required"}, status=401)

    async def handle_root(self, request: web.Request) -> web.Response:
        return web.Response(text=ADMIN_HTML, content_type="text/html")

    async def handle_auth(self, request: web.Request) -> web.Response:
        payload = await request.json()
        submitted = str(payload.get("api_key", ""))
        if not self.adapter._api_key or not hmac.compare_digest(submitted, self.adapter._api_key):
            return web.json_response({"error": "invalid_api_key"}, status=401)
        response = web.json_response({"ok": True})
        response.set_cookie("hermes_admin_session", self.sessions.issue(), httponly=True, samesite="Strict")
        return response

    async def handle_config(self, request: web.Request) -> web.Response:
        auth = self._require_admin(request)
        if auth:
            return auth
        return web.json_response(self.storage.read_current_summary())
```

And wire it into `api_server.py`:

```python
from gateway.platforms.api_server_admin import APIServerAdminService


class APIServerAdapter(BasePlatformAdapter):
    def __init__(self, config: PlatformConfig):
        ...
        self._admin_service = APIServerAdminService(self)

    async def _handle_root(self, request: "web.Request") -> "web.Response":
        return await self._admin_service.handle_root(request)

    def _build_test_app(self):
        mws = [mw for mw in (cors_middleware, security_headers_middleware) if mw is not None]
        app = web.Application(middlewares=mws)
        app["api_server_adapter"] = self
        app.router.add_get("/", self._handle_root)
        app.router.add_post("/api/admin/auth", self._admin_service.handle_auth)
        app.router.add_get("/api/admin/config", self._admin_service.handle_config)
        app.router.add_get("/health", self._handle_health)
        app.router.add_get("/v1/health", self._handle_health)
        app.router.add_get("/v1/models", self._handle_models)
        return app
```

- [ ] **Step 4: Re-run the admin-route tests and get them green**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server.py tests/gateway/test_api_server_admin.py -q
```

Expected: root-route and auth/config tests pass.

- [ ] **Step 5: Commit the admin-route slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent && test -d .git && git add docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py && git commit -m "feat: add hermes admin console routes" || true
```

### Task 4: Implement connection testing, apply/restart, restore, and deployment wiring

**Files:**
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py`
- Modify: `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Test: `docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py`

- [ ] **Step 1: Write failing tests for test-connection, apply, restore, and post-restart status**

```python
from unittest.mock import AsyncMock


async def test_test_connection_uses_form_values(monkeypatch):
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()
    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})

        async def fake_probe(**kwargs):
            return {"ok": True, "status": 200, "model_ids": ["gpt-4o-mini"]}

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
        assert payload["ok"] is True
        assert payload["model_ids"] == ["gpt-4o-mini"]


async def test_apply_writes_status_then_requests_restarts(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("model:\n  provider: custom\n  base_url: https://old.example/v1\n  default: old\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=old\n", encoding="utf-8")
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    app = adapter._build_test_app()
    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        monkeypatch.setattr(adapter._admin_service, "probe_provider", AsyncMock(return_value={"ok": True, "status": 200, "model_ids": ["gpt-4o-mini"]}))
        restart_calls = []
        monkeypatch.setattr(adapter._admin_service.runtime, "restart_service", lambda name: restart_calls.append(name))
        response = await client.post(
            "/api/admin/apply",
            json={"provider": "openai", "api_key": "sk-new", "base_url": "https://api.openai.com/v1", "model_name": "gpt-4o-mini"},
        )
        assert response.status == 202
        assert restart_calls == ["open-webui", "hermes-agent"]
        status = json.loads((tmp_path / "admin_apply_status.json").read_text(encoding="utf-8"))
        assert status["phase"] == "pending_verification"


async def test_restore_endpoint_restores_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text("model:\n  default: before\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=before\n", encoding="utf-8")
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "sk-admin"}))
    adapter._admin_service.storage.backup_current_state()
    (tmp_path / "config.yaml").write_text("model:\n  default: after\n", encoding="utf-8")
    app = adapter._build_test_app()
    async with TestClient(TestServer(app)) as client:
        await client.post("/api/admin/auth", json={"api_key": "sk-admin"})
        response = await client.post("/api/admin/restore")
        payload = await response.json()
        assert payload["ok"] is True
        assert "before" in (tmp_path / "config.yaml").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the apply-flow tests and confirm failure**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server_admin.py -q
```

Expected: failures for missing endpoints, missing probe/restart orchestration, or wrong status behavior.

- [ ] **Step 3: Implement test/apply/restore/status logic and wire deployment changes**

```python
import aiohttp
from aiohttp import web

from gateway.platforms.api_server_admin_docker import DockerComposeRuntime


class APIServerAdminService:
    def __init__(self, adapter):
        self.adapter = adapter
        self.storage = HermesAdminStorage()
        self.runtime = DockerComposeRuntime()
        self.sessions = AdminSessionStore(api_key=adapter._api_key)

    async def probe_provider(self, *, api_key: str, base_url: str, model_name: str) -> dict[str, object]:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                payload = await response.json()
                model_ids = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
                return {
                    "ok": response.status < 400,
                    "status": response.status,
                    "model_name": model_name,
                    "model_ids": model_ids,
                }

    async def handle_test_connection(self, request: web.Request) -> web.Response:
        auth = self._require_admin(request)
        if auth:
            return auth
        payload = await request.json()
        result = await self.probe_provider(
            api_key=str(payload.get("api_key", "")),
            base_url=str(payload.get("base_url", "")),
            model_name=str(payload.get("model_name", "")),
        )
        return web.json_response(result, status=200 if result["ok"] else 400)

    async def handle_apply(self, request: web.Request) -> web.Response:
        auth = self._require_admin(request)
        if auth:
            return auth
        payload = await request.json()
        probe = await self.probe_provider(
            api_key=str(payload.get("api_key", "")),
            base_url=str(payload.get("base_url", "")),
            model_name=str(payload.get("model_name", "")),
        )
        if not probe["ok"]:
            return web.json_response({"ok": False, "phase": "probe_failed", "probe": probe}, status=400)

        self.storage.backup_current_state()
        summary = self.storage.apply_provider_settings(
            provider=str(payload["provider"]),
            api_key=str(payload["api_key"]),
            base_url=str(payload["base_url"]),
            model_name=str(payload["model_name"]),
        )
        self.storage.sync_open_webui_config(
            db_path=self.storage.hermes_home.parent / "open-webui" / "webui.db",
            api_key=self.adapter._api_key,
        )
        self.storage.status_store.write({
            "phase": "pending_verification",
            "provider": summary["provider"],
            "model": summary["model"],
            "base_url": summary["base_url"],
        })
        self.runtime.restart_service("open-webui")
        self.runtime.restart_service("hermes-agent")
        return web.json_response({"ok": True, "phase": "pending_verification"}, status=202)

    async def handle_restore(self, request: web.Request) -> web.Response:
        auth = self._require_admin(request)
        if auth:
            return auth
        self.storage.restore_last_backup()
        self.storage.status_store.write({"phase": "restored"})
        return web.json_response({"ok": True, "phase": "restored"})

    async def handle_status(self, request: web.Request) -> web.Response:
        auth = self._require_admin(request)
        if auth:
            return auth
        status = self.storage.status_store.read()
        if status.get("phase") == "pending_verification":
            status = await self._verify_after_restart(status)
            self.storage.status_store.write(status)
        return web.json_response(status)
```

Update `api_server.py` route registration:

```python
self._app.router.add_post("/api/admin/auth", self._admin_service.handle_auth)
self._app.router.add_get("/api/admin/config", self._admin_service.handle_config)
self._app.router.add_post("/api/admin/test-connection", self._admin_service.handle_test_connection)
self._app.router.add_post("/api/admin/apply", self._admin_service.handle_apply)
self._app.router.add_get("/api/admin/status", self._admin_service.handle_status)
self._app.router.add_post("/api/admin/restore", self._admin_service.handle_restore)
```

Update `docker-compose.yml`:

```yaml
  hermes-agent:
    volumes:
      - ${HERMES_DATA_ROOT:-./data}/hermes:/opt/data
      - /var/run/docker.sock:/var/run/docker.sock
```

Update `README.md` with:

```md
## Config Console

- Console: `http://localhost:18642/`
- Login secret: the current `HERMES_API_KEY` from `.env`
- The standalone stack now mounts `/var/run/docker.sock` into `hermes-agent` so the console can restart `hermes-agent` and `open-webui` after provider changes.
```

- [ ] **Step 4: Run focused tests, then the broader API-server suite**

Run:

```bash
cd /Users/awk/lqf/hermes-agent/docker/hermes-agent/hermes-agent-src && source venv/bin/activate && pytest tests/gateway/test_api_server_admin.py tests/gateway/test_api_server.py -q
```

Expected: the new admin tests pass and no root-route regressions remain.

- [ ] **Step 5: Run the standalone stack verification commands**

Run:

```bash
cd /Users/awk/lqf/hermes-agent && docker compose up -d --build && curl -sS http://localhost:18642/ | head -20 && curl -sS http://localhost:18642/health && curl -sSI http://localhost:13000 | head -10
```

Expected:

- `GET /` returns HTML containing `Hermes Config Console`
- `GET /health` returns `{"status": "ok", "platform": "hermes-agent"}`
- Open WebUI still returns `HTTP/1.1 200 OK`

- [ ] **Step 6: Commit the apply-flow slice**

Run:

```bash
cd /Users/awk/lqf/hermes-agent && test -d .git && git add docker-compose.yml README.md docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin.py docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server_admin_storage.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server.py docker/hermes-agent/hermes-agent-src/tests/gateway/test_api_server_admin.py && git commit -m "feat: add hermes config console apply flow" || true
```

## Self-Review

### Spec coverage

- Locked HTML root and auth gate: Task 3
- Unlocked summary/config/test/apply/restore/status APIs: Tasks 3 and 4
- Provider preset persistence into `config.yaml` and `.env`: Task 1
- Open WebUI SQLite repair from `openclaw-hermes-agent` to `hermes-agent`: Task 2
- Restart of `open-webui` and `hermes-agent`: Task 4
- Persisted status/verification after restart: Tasks 1 and 4
- README and deployment notes: Task 4

### Placeholder scan

- No `TODO`, `TBD`, or “handle appropriately” placeholders remain.
- Every task names exact files, test commands, and implementation seams.
- The one infrastructure decision deferred by the design doc is now explicit: Docker Engine API over mounted Unix socket.

### Type and naming consistency

- `APIServerAdminService`, `HermesAdminStorage`, `AdminApplyStatusStore`, and `DockerComposeRuntime` are the only new top-level types introduced by the plan.
- Route names stay under `/api/admin/*` exactly as defined in the spec.
- Persisted phase names are `idle`, `pending_verification`, and `restored`; keep those exact spellings across code and tests.

Plan complete and saved to `docs/superpowers/plans/2026-04-13-hermes-config-console.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
