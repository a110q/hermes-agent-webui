from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from gateway.platforms.api_server_admin_profiles import AdminProfilesStore
from gateway.platforms.api_server_admin_storage import HermesAdminStorage


def materialize_default_profile_if_present(hermes_home: str | Path) -> dict[str, Any]:
    hermes_home = Path(hermes_home)
    profiles_path = hermes_home / "admin_profiles.json"
    if not profiles_path.exists():
        return {"applied": False, "reason": "profile_library_missing"}

    previous_home = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(hermes_home)
    try:
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
    finally:
        if previous_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous_home
