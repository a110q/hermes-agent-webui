import json
import sqlite3
from pathlib import Path

from hermes_cli.config import get_config_path, get_env_path, load_config, load_env, save_config, save_env_value
from gateway.platforms.api_server_admin_storage import AdminApplyStatusStore, HermesAdminStorage


def test_apply_provider_settings_updates_yaml_and_env_preserving_unrelated_values():
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
    save_env_value("OPENROUTER_API_KEY", "stale-openrouter-key")
    save_env_value("TERMINAL_TIMEOUT", "60")

    storage = HermesAdminStorage()
    summary = storage.apply_provider_settings(
        provider="openrouter",
        api_key="openrouter_secret_1234",
        base_url="https://openrouter.ai/api/v1",
        model_name="openai/gpt-4.1-mini",
    )

    config = load_config()
    env_vars = load_env()

    assert config["model"]["provider"] == "openrouter"
    assert config["model"]["base_url"] == "https://openrouter.ai/api/v1"
    assert config["model"]["default"] == "openai/gpt-4.1-mini"
    assert env_vars["OPENROUTER_API_KEY"] == "openrouter_secret_1234"
    assert "OPENAI_API_KEY" not in env_vars
    assert env_vars["TERMINAL_TIMEOUT"] == "60"
    assert summary == {
        "provider": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1-mini",
        "api_key_masked": "••••1234",
    }


def test_backup_current_state_creates_backup_files():
    save_config({"model": {"provider": "custom", "base_url": "https://old.example/v1", "default": "old-model"}})
    save_env_value("OPENAI_API_KEY", "old-openai-key")

    storage = HermesAdminStorage()
    result = storage.backup_current_state()

    config_backup = Path(result["config_backup_path"])
    env_backup = Path(result["env_backup_path"])

    assert config_backup.exists()
    assert env_backup.exists()
    assert config_backup.read_text(encoding="utf-8") == get_config_path().read_text(encoding="utf-8")
    assert env_backup.read_text(encoding="utf-8") == get_env_path().read_text(encoding="utf-8")


def test_restore_last_backup_restores_previous_config_and_env():
    save_config({"model": {"provider": "custom", "base_url": "https://old.example/v1", "default": "old-model"}})
    save_env_value("OPENAI_API_KEY", "old-openai-key")

    storage = HermesAdminStorage()
    storage.backup_current_state()

    storage.apply_provider_settings(
        provider="gemini",
        api_key="gemini_secret_5678",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        model_name="gemini-2.5-pro",
    )

    storage.restore_last_backup()

    config = load_config()
    env_vars = load_env()

    assert config["model"]["provider"] == "custom"
    assert config["model"]["base_url"] == "https://old.example/v1"
    assert config["model"]["default"] == "old-model"
    assert env_vars["OPENAI_API_KEY"] == "old-openai-key"
    assert "GOOGLE_API_KEY" not in env_vars


def test_status_store_round_trip(tmp_path):
    status_path = tmp_path / "admin_apply_status.json"
    store = AdminApplyStatusStore(status_path)

    assert store.read() == {"phase": "idle"}

    payload = {"phase": "pending_verification", "provider": "gemini", "model": "gemini-2.5-pro"}
    store.write(payload)

    assert status_path.exists()
    assert json.loads(status_path.read_text(encoding="utf-8")) == payload
    assert store.read() == payload


def test_sync_open_webui_config_rewrites_stale_target(tmp_path):
    db_path = tmp_path / "webui.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE config (id INTEGER PRIMARY KEY, data JSON NOT NULL, version INTEGER NOT NULL)"
    )
    payload = {
        "version": 0,
        "openai": {
            "enable": True,
            "api_base_urls": ["http://openclaw-hermes-agent:8642/v1"],
            "api_keys": ["old-secret"],
            "api_configs": {
                "0": {
                    "enable": True,
                    "tags": [],
                    "prefix_id": "",
                    "model_ids": [],
                    "connection_type": "external",
                    "auth_type": "bearer",
                }
            },
        },
    }
    conn.execute(
        "INSERT INTO config (id, data, version) VALUES (1, ?, 0)",
        (json.dumps(payload),),
    )
    conn.commit()
    conn.close()

    storage = HermesAdminStorage(hermes_home=tmp_path)
    summary = storage.sync_open_webui_config(db_path=db_path, api_key="new-secret")

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT data FROM config WHERE id = 1").fetchone()
    conn.close()
    updated = json.loads(row[0])
    backup = json.loads((tmp_path / "open_webui_config.bak.json").read_text(encoding="utf-8"))

    assert updated["openai"]["api_base_urls"] == ["http://hermes-agent:8642/v1"]
    assert updated["openai"]["api_keys"] == ["new-secret"]
    assert updated["openai"]["api_configs"]["0"]["connection_type"] == "external"
    assert backup["openai"]["api_base_urls"] == ["http://openclaw-hermes-agent:8642/v1"]
    assert summary["rewritten"] is True
    assert summary["db_path"] == str(db_path)
