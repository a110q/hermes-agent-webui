from __future__ import annotations

import json
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

    def create_profile(
        self,
        *,
        name: str,
        provider_type: str,
        base_url: str,
        api_key: str,
        model_name: str,
    ) -> dict[str, Any]:
        document = self.read_document()
        now = _utc_now()
        created = {
            "id": f"prof_{secrets.token_hex(6)}",
            "name": name,
            "provider_type": provider_type,
            "base_url": base_url,
            "api_key": api_key,
            "model_name": model_name,
            "created_at": now,
            "updated_at": now,
            "last_test_result": None,
        }
        document["profiles"].append(created)
        self._write_document(document)
        listed = dict(created)
        listed["api_key_masked"] = _mask_secret(api_key)
        listed.pop("api_key", None)
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
        document["profiles"] = [profile for profile in document["profiles"] if profile["id"] != profile_id]
        for key in ("default_profile_id", "active_profile_id", "last_known_good_profile_id"):
            if document.get(key) == profile_id:
                document[key] = None
        self._write_document(document)

    def set_default_profile(self, profile_id: str | None) -> None:
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
