from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from hermes_cli.config import load_config, load_env, remove_env_value, save_config, save_env_value
from hermes_constants import get_hermes_home
from utils import atomic_json_write


_MANAGED_PROVIDER_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
}

_MANAGED_BASE_URL_ENV_KEYS = {
    "OPENAI_BASE_URL",
}

_PROVIDER_ENV_KEY = {
    "custom": "OPENAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

_OPEN_WEBUI_UPSTREAM = "http://hermes-agent:8642/v1"


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


class AdminApplyStatusStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"phase": "idle"}
        with self.path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def write(self, payload: dict[str, Any]) -> None:
        atomic_json_write(self.path, payload)


class HermesAdminStorage:
    def __init__(self, hermes_home: str | Path | None = None):
        self.hermes_home = Path(hermes_home) if hermes_home else get_hermes_home()
        self.config_path = self.hermes_home / "config.yaml"
        self.env_path = self.hermes_home / ".env"
        self.status_store = AdminApplyStatusStore(self.hermes_home / "admin_apply_status.json")

    def read_current_summary(self) -> dict[str, Any]:
        config = load_config()
        env_vars = load_env()
        model_config = dict(config.get("model") or {})
        provider = str(model_config.get("provider") or "").strip().lower()
        api_key_name = _PROVIDER_ENV_KEY.get(provider, "")
        api_key_value = env_vars.get(api_key_name, "") if api_key_name else ""
        return {
            "provider": provider,
            "base_url": str(model_config.get("base_url") or ""),
            "model": str(model_config.get("default") or model_config.get("model") or ""),
            "api_key_masked": _mask_secret(api_key_value),
            "has_api_key": bool(api_key_value),
        }

    def backup_current_state(self) -> dict[str, str]:
        self.hermes_home.mkdir(parents=True, exist_ok=True)
        config_backup = self.hermes_home / "config.yaml.bak"
        env_backup = self.hermes_home / ".env.bak"

        if self.config_path.exists():
            shutil.copy2(self.config_path, config_backup)
        if self.env_path.exists():
            shutil.copy2(self.env_path, env_backup)

        return {
            "config_backup_path": str(config_backup),
            "env_backup_path": str(env_backup),
        }

    def apply_provider_settings(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        model_name: str,
    ) -> dict[str, str]:
        normalized_provider = provider.strip().lower()
        if normalized_provider == "openai":
            normalized_provider = "custom"
        if normalized_provider not in _PROVIDER_ENV_KEY:
            raise ValueError(f"Unsupported provider: {provider}")

        config = load_config()
        model_config = dict(config.get("model") or {})
        model_config["provider"] = normalized_provider
        model_config["base_url"] = base_url
        model_config["default"] = model_name
        config["model"] = model_config
        save_config(config)

        selected_env_key = _PROVIDER_ENV_KEY[normalized_provider]
        for env_key in sorted(_MANAGED_PROVIDER_ENV_KEYS):
            if env_key == selected_env_key:
                save_env_value(env_key, api_key)
            else:
                remove_env_value(env_key)

        if normalized_provider == "custom":
            save_env_value("OPENAI_BASE_URL", base_url)
        else:
            for env_key in sorted(_MANAGED_BASE_URL_ENV_KEYS):
                remove_env_value(env_key)

        return {
            "provider": normalized_provider,
            "base_url": base_url,
            "model": model_name,
            "api_key_masked": _mask_secret(api_key),
        }

    def apply_profile_record(self, profile: dict[str, Any]) -> dict[str, str]:
        provider_type = str(profile.get("provider_type") or "openai-compatible").strip().lower()
        provider = "custom" if provider_type in {"openai", "openai-compatible", "custom"} else provider_type
        return self.apply_provider_settings(
            provider=provider,
            api_key=str(profile.get("api_key", "")),
            base_url=str(profile.get("base_url", "")),
            model_name=str(profile.get("model_name", "")),
        )

    def restore_last_backup(self) -> None:
        config_backup = self.hermes_home / "config.yaml.bak"
        env_backup = self.hermes_home / ".env.bak"

        shutil.copy2(config_backup, self.config_path)
        shutil.copy2(env_backup, self.env_path)

    def sync_open_webui_config(self, *, db_path: str | Path, api_key: str) -> dict[str, Any]:
        db_path = Path(db_path)
        backup_path = self.hermes_home / "open_webui_config.bak.json"

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("SELECT id, data FROM config ORDER BY id LIMIT 1").fetchone()
            if row is None:
                raise RuntimeError(f"No config row found in {db_path}")

            row_id, raw_data = row
            payload = json.loads(raw_data)
            atomic_json_write(backup_path, payload)

            openai_config = dict(payload.get("openai") or {})
            openai_config["enable"] = True
            openai_config["api_base_urls"] = [_OPEN_WEBUI_UPSTREAM]
            openai_config["api_keys"] = [api_key]

            api_configs = dict(openai_config.get("api_configs") or {})
            api_config_0 = dict(api_configs.get("0") or {})
            api_config_0.update(
                {
                    "enable": True,
                    "tags": api_config_0.get("tags", []),
                    "prefix_id": api_config_0.get("prefix_id", ""),
                    "model_ids": api_config_0.get("model_ids", []),
                    "connection_type": "external",
                    "auth_type": "bearer",
                }
            )
            api_configs["0"] = api_config_0
            openai_config["api_configs"] = api_configs
            payload["openai"] = openai_config

            conn.execute("UPDATE config SET data = ? WHERE id = ?", (json.dumps(payload), row_id))
            conn.commit()
        finally:
            conn.close()

        return {
            "rewritten": True,
            "db_path": str(db_path),
            "backup_path": str(backup_path),
            "api_base_url": _OPEN_WEBUI_UPSTREAM,
        }
