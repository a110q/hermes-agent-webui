from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import aiohttp
from aiohttp import web

from gateway.platforms.api_server_admin_docker import DockerComposeRuntime
from gateway.platforms.api_server_admin_profiles import AdminProfilesStore
from gateway.platforms.api_server_admin_storage import HermesAdminStorage
from gateway.platforms.api_server_admin_ui import render_admin_shell


def _normalize_model_name(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if "/" in normalized:
        normalized = normalized.split("/")[-1]
    return normalized


def _model_name_matches(requested: str, actual: str) -> bool:
    requested_normalized = _normalize_model_name(requested)
    actual_normalized = _normalize_model_name(actual)
    return bool(requested_normalized and actual_normalized and requested_normalized == actual_normalized)


def _extract_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code")
            if message:
                return str(message)
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return ""


@dataclass
class AdminSessionStore:
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
        self.runtime = DockerComposeRuntime()
        self.sessions = AdminSessionStore()
        self.profiles = AdminProfilesStore(self.storage.hermes_home / "admin_profiles.json")

    def _require_admin(self, request: web.Request):
        token = request.cookies.get("hermes_admin_session", "")
        if self.sessions.validate(token):
            return None
        return web.json_response({"error": "admin_auth_required"}, status=401)

    def _open_webui_db_path(self) -> Path:
        return self.storage.hermes_home.parent / "open-webui" / "webui.db"

    def _status_payload(
        self,
        *,
        phase: str,
        summary: dict[str, Any] | None = None,
        profile_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"phase": phase}
        if profile_id:
            payload["profile_id"] = profile_id
        if summary:
            for key in ("provider", "model", "base_url"):
                value = summary.get(key)
                if value:
                    payload[key] = value
        if error:
            payload["error"] = error
        return payload

    def _rollback_runtime_change(
        self,
        *,
        profile_id: str | None,
        summary: dict[str, Any] | None,
        error: Exception,
    ) -> web.Response:
        error_message = str(error)

        try:
            self.storage.restore_last_backup()
        except Exception as restore_exc:
            error_message = f"{error_message}; rollback restore failed: {restore_exc}"

        try:
            self.runtime.restart_service("open-webui")
            self.runtime.wait_for_service("open-webui", timeout_seconds=90)
        except Exception as restart_exc:
            error_message = f"{error_message}; open-webui rollback failed: {restart_exc}"

        self.storage.status_store.write(
            self._status_payload(
                phase="rollback_complete",
                summary=summary,
                profile_id=profile_id,
                error=error_message,
            )
        )
        return web.json_response({"ok": False, "phase": "failed", "error": error_message}, status=500)

    async def _commit_runtime_change(
        self,
        apply_change: Callable[[], dict[str, str]],
        *,
        profile_id: str | None = None,
        activate_profile_id: str | None = None,
    ) -> web.Response:
        self.storage.backup_current_state()
        summary: dict[str, str] | None = None

        try:
            self.storage.status_store.write(self._status_payload(phase="writing_runtime_config", profile_id=profile_id))
            summary = apply_change()
            self.storage.status_store.write(
                self._status_payload(phase="syncing_open_webui", summary=summary, profile_id=profile_id)
            )
            self.storage.sync_open_webui_config(db_path=self._open_webui_db_path(), api_key=self.adapter._api_key)
            self.storage.status_store.write(
                self._status_payload(phase="restarting_open_webui", summary=summary, profile_id=profile_id)
            )
            self.runtime.restart_service("open-webui")
            self.storage.status_store.write(
                self._status_payload(phase="verifying_open_webui", summary=summary, profile_id=profile_id)
            )
            self.runtime.wait_for_service("open-webui", timeout_seconds=90)

            if activate_profile_id:
                self.profiles.set_active_profile(activate_profile_id)
                self.profiles.mark_last_known_good(activate_profile_id)

            ready_status = self._status_payload(phase="ready", summary=summary, profile_id=profile_id)
            self.storage.status_store.write(ready_status)

            payload: dict[str, Any] = {"ok": True, "phase": "ready"}
            if activate_profile_id:
                payload["active_profile_id"] = activate_profile_id
            return web.json_response(payload, status=202)
        except Exception as exc:
            return self._rollback_runtime_change(profile_id=profile_id, summary=summary, error=exc)

    async def handle_root(self, request: web.Request) -> web.Response:
        return web.Response(text=render_admin_shell(), content_type="text/html")

    async def handle_auth(self, request: web.Request) -> web.Response:
        payload = await request.json()
        submitted = str(payload.get("api_key", ""))
        if not self.adapter._api_key or not hmac.compare_digest(submitted, self.adapter._api_key):
            return web.json_response({"error": "invalid_api_key"}, status=401)

        response = web.json_response({"ok": True})
        response.set_cookie(
            "hermes_admin_session",
            self.sessions.issue(),
            httponly=True,
            samesite="Strict",
        )
        return response

    async def handle_config(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        return web.json_response(self.storage.read_current_summary())

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
        if "api_key" in payload and not str(payload.get("api_key") or "").strip():
            payload.pop("api_key", None)
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

    async def probe_provider(self, *, api_key: str, base_url: str, model_name: str) -> dict[str, Any]:
        base = base_url.rstrip("/")
        target = f"{base}/models"
        chat_target = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        timeout = aiohttp.ClientTimeout(total=15)
        requested_model = str(model_name or "").strip()

        result: dict[str, Any] = {
            "ok": False,
            "status": 0,
            "model_name": requested_model,
            "model_ids": [],
        }

        if not requested_model:
            result["error"] = "模型名称不能为空"
            return result

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    async with session.get(target, headers=headers) as response:
                        payload = await response.json(content_type=None)
                        result["models_status"] = response.status
                        result["model_ids"] = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
                        models_error = _extract_error_message(payload)
                        if models_error:
                            result["models_error"] = models_error
                except Exception as exc:
                    result["models_error"] = str(exc)

                async with session.post(
                    chat_target,
                    headers={**headers, "Content-Type": "application/json"},
                    json={
                        "model": requested_model,
                        "messages": [{"role": "user", "content": "Reply exactly: OK"}],
                        "max_tokens": 8,
                        "temperature": 0,
                    },
                ) as response:
                    payload = await response.json(content_type=None)
                    result["status"] = response.status
                    resolved_model = str(payload.get("model") or "")
                    if resolved_model:
                        result["resolved_model"] = resolved_model

                    if response.status >= 400:
                        result["error"] = _extract_error_message(payload) or f"HTTP {response.status}"
                        return result

                    if resolved_model and not _model_name_matches(requested_model, resolved_model):
                        result["error"] = f"请求模型 {requested_model}，但上游实际返回的是 {resolved_model}"
                        return result

                    result["ok"] = True
                    return result
        except Exception as exc:
            result["error"] = str(exc)
            return result

    async def handle_test_connection(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        payload = await request.json()
        result = await self.probe_provider(
            api_key=str(payload.get("api_key", "")),
            base_url=str(payload.get("base_url", "")),
            model_name=str(payload.get("model_name", "")),
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    async def handle_apply(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        payload = await request.json()
        provider = str(payload.get("provider", ""))
        api_key = str(payload.get("api_key", ""))
        base_url = str(payload.get("base_url", ""))
        model_name = str(payload.get("model_name", ""))

        probe = await self.probe_provider(api_key=api_key, base_url=base_url, model_name=model_name)
        if not probe.get("ok"):
            return web.json_response({"ok": False, "phase": "probe_failed", "probe": probe}, status=400)

        return await self._commit_runtime_change(
            lambda: self.storage.apply_provider_settings(
                provider=provider,
                api_key=api_key,
                base_url=base_url,
                model_name=model_name,
            )
        )

    async def _verify_after_restart(self, status: dict[str, Any]) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=5)
        headers = {"Authorization": f"Bearer {self.adapter._api_key}"} if self.adapter._api_key else {}
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("http://127.0.0.1:8642/health") as health_response:
                    if health_response.status >= 400:
                        return status
                async with session.get("http://127.0.0.1:8642/v1/models", headers=headers) as models_response:
                    if models_response.status >= 400:
                        return status
            next_status = dict(status)
            next_status["phase"] = "ready"
            return next_status
        except Exception:
            return status

    async def handle_status(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        status = self.storage.status_store.read()
        if status.get("phase") == "pending_verification":
            status = await self._verify_after_restart(status)
            self.storage.status_store.write(status)
        current_summary = self.storage.read_current_summary()
        for key in ("provider", "model", "base_url"):
            if current_summary.get(key) and not status.get(key):
                status[key] = current_summary[key]
        return web.json_response(status)

    async def _activate_profile(self, profile: dict[str, Any]) -> web.Response:
        probe = await self.probe_provider(
            api_key=str(profile.get("api_key", "")),
            base_url=str(profile.get("base_url", "")),
            model_name=str(profile.get("model_name", "")),
        )
        if not probe.get("ok"):
            return web.json_response({"ok": False, "phase": "probe_failed", "probe": probe}, status=400)

        return await self._commit_runtime_change(
            lambda: self.storage.apply_profile_record(profile),
            profile_id=profile["id"],
            activate_profile_id=profile["id"],
        )

    async def handle_restore(self, request: web.Request) -> web.Response:
        auth_error = self._require_admin(request)
        if auth_error:
            return auth_error
        try:
            self.storage.restore_last_backup()
            self.runtime.restart_service("open-webui")
            self.runtime.wait_for_service("open-webui", timeout_seconds=90)
            self.storage.status_store.write({"phase": "restored"})
            return web.json_response({"ok": True, "phase": "restored"})
        except Exception as exc:
            self.storage.status_store.write({"phase": "restore_failed", "error": str(exc)})
            return web.json_response({"ok": False, "phase": "restore_failed", "error": str(exc)}, status=500)
