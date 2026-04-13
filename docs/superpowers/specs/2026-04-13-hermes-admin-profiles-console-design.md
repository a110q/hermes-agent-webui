# Hermes Admin Profiles Console Design

## Goal

Build a protected local admin console at `http://localhost:18642/` that lets the operator manage multiple upstream LLM configuration profiles for Hermes Agent, choose a default profile used at startup, activate any profile immediately, automatically repair Open WebUI's upstream connection, and ensure Open WebUI can select models after configuration changes.

## Problem Summary

The current standalone deployment has two linked problems:

1. Hermes itself exposes a healthy OpenAI-compatible API at `http://localhost:18642`, but the root page is not an operator console.
2. Open WebUI can show `暂无可用模型` because its saved upstream connection still points to a stale historical endpoint such as `http://openclaw-hermes-agent:8642/v1` instead of the live Compose service `http://hermes-agent:8642/v1`.

Today, changing the upstream provider requires manual edits to `data/hermes/config.yaml`, `data/hermes/.env`, and sometimes `data/open-webui/webui.db`. That is fragile, easy to break, and does not support multiple reusable provider profiles.

## Approved Product Direction

The approved product behavior is:

- a local password-protected admin page at `http://localhost:18642/`
- multiple saved upstream configuration profiles
- one default profile used automatically on service startup
- one currently active profile used by the running Hermes instance
- a `Save and Apply` flow that makes changes effective immediately
- automatic restart and health verification after apply
- automatic rollback to the last known good runtime configuration when apply fails
- Open WebUI always connects to Hermes, never directly to the external provider URL

## Scope

### In Scope

- Replace `GET /` on the Hermes API server with a lightweight admin console HTML page.
- Protect the console with the current `HERMES_API_KEY`.
- Store multiple reusable upstream configuration profiles.
- Support a default profile and an active profile.
- Let the user configure, per profile:
  - profile name
  - provider type
  - base URL
  - API key
  - model name
- Support at least OpenAI-compatible upstreams in the first version.
- Allow testing a profile connection before saving or applying.
- Allow setting a profile as default without immediately activating it.
- Allow activating a profile immediately so the running Hermes instance starts using it.
- Persist the currently active runtime config into `data/hermes/config.yaml` and `data/hermes/.env`.
- Repair Open WebUI's saved OpenAI connection target and API key in `data/open-webui/webui.db`.
- Restart `hermes-agent` and `open-webui` automatically when applying a profile.
- Verify Hermes and Open WebUI after apply.
- Keep backups and allow rollback to the last known good runtime config.
- Persist status and recent apply results for the UI.
- On startup, automatically materialize the default profile into the runtime config before Hermes starts.

### Out of Scope

- Multi-user authentication and role management.
- Internet-facing hardening beyond local workstation use.
- External secrets managers or vault integration.
- Per-profile advanced provider routing knobs in the first version.
- Direct Open WebUI connection to the external provider.
- A full settings dashboard for all Hermes features.

## User Personas

### Local operator

Runs the standalone Compose stack on one machine, wants to paste a provider URL, key, and model name into a web form, and expects the stack to become usable immediately without touching files or databases.

### Power operator

Wants several saved upstream profiles, such as production OpenAI, a proxy endpoint, and a cheaper fallback model, and expects one of them to be the default profile on restart.

## UX Overview

The root page becomes a local operator console with two states.

### 1. Locked state

- shows one password-style field labeled `Current HERMES_API_KEY`
- shows one primary action labeled `Enter Console`
- reveals no provider details or saved secrets before authentication

### 2. Unlocked state

The unlocked page is a compact two-column operator console.

#### Left rail: profile library

Shows all saved profiles with:

- profile name
- model name
- truncated base URL
- badges for:
  - `Default`
  - `Active`
  - `Last Known Good` if helpful

Actions in the left rail:

- `New Profile`
- `Duplicate`
- `Delete`
- selecting a profile loads it into the editor

#### Main pane: profile editor and apply controls

Shows fields for the selected profile:

- `Profile Name`
- `Provider Type`
- `Base URL`
- `API Key`
- `Model Name`

Actions:

- `Test Connection`
- `Save`
- `Save as New Profile`
- `Set as Default`
- `Apply Now`
- `Rollback Previous Runtime`

#### Status area

Shows:

- Hermes health
- current active profile
- current default profile
- last apply result
- last verification result
- recent operation log with step-by-step state updates

## Interaction Design

### Provider model

The first version stores a `provider_type` field per profile, but the primary supported path is OpenAI-compatible upstreams. That means the most important operator inputs are:

- URL
- API key
- model name

The provider field exists so the design can grow cleanly, but the initial UX should keep these three fields visually prominent.

### Profile behavior

- `Save` updates the selected profile in the profile library only.
- `Set as Default` changes which profile is used automatically at startup.
- `Apply Now` makes the selected profile the active runtime config immediately.
- `Set as Default` does not need to imply `Apply Now`.
- `Apply Now` only changes the active runtime profile in the first version.
- `Set as Default` only changes startup default behavior in the first version.
- The first version does not include a combined `Set Default and Apply` action.

### Model field behavior

The model name remains manually editable even if remote model discovery fails. This avoids dead ends when an upstream does not expose a full `/models` list or when the user already knows the correct model name.

### Secret handling in UI

- saved keys are masked in summaries
- the editor may show a placeholder such as `••••••••` for an existing key
- the full stored key is never returned to the browser after save
- replacing a key is explicit: if the operator types a new key, it overwrites the stored one

## Current Root Cause That Must Be Fixed

The current live Open WebUI config contains a stale upstream endpoint:

- stale value: `http://openclaw-hermes-agent:8642/v1`
- required value: `http://hermes-agent:8642/v1`

The admin console must repair that automatically during profile apply. This is not optional because Hermes can already return `/v1/models` correctly while Open WebUI still shows no selectable models.

## Architecture

The implementation uses a split model:

1. **Profile library state** — a dedicated admin profiles file containing all saved profiles and metadata.
2. **Runtime state** — the actual Hermes runtime config files that the running service consumes.
3. **WebUI sync state** — the persisted Open WebUI config row that must always point to Hermes.

This keeps the profile library separate from the active runtime configuration and minimizes changes to Hermes' existing startup and runtime config loading behavior.

## Persistence Model

### 1. Profile library

Create `data/hermes/admin_profiles.json`.

Suggested structure:

```json
{
  "version": 1,
  "default_profile_id": "prof_openai_prod",
  "active_profile_id": "prof_openai_prod",
  "last_known_good_profile_id": "prof_openai_prod",
  "profiles": [
    {
      "id": "prof_openai_prod",
      "name": "OpenAI Prod",
      "provider_type": "openai-compatible",
      "base_url": "https://api.openai.com/v1",
      "api_key": "stored-secret",
      "model_name": "gpt-4.1",
      "created_at": "2026-04-13T00:00:00Z",
      "updated_at": "2026-04-13T00:00:00Z",
      "last_test_result": {
        "ok": true,
        "checked_at": "2026-04-13T00:00:00Z",
        "status": 200,
        "model_ids": ["gpt-4.1", "gpt-4o-mini"]
      }
    }
  ]
}
```

This file is the source of truth for all saved profiles.

### 2. Hermes runtime config

Keep using:

- `data/hermes/config.yaml`
- `data/hermes/.env`

These remain the source of truth for the currently running Hermes process. Activating a profile means materializing that profile into these runtime files.

### 3. Apply status and backups

Use:

- `data/hermes/admin_apply_status.json`
- `data/hermes/config.yaml.bak`
- `data/hermes/.env.bak`
- `data/hermes/open_webui_config.bak.json`

These support operator feedback, health checks, and rollback.

## Runtime Activation Model

### Save only

Saving a profile updates `admin_profiles.json` only. It does not change the currently running service.

### Set default

Setting default updates `default_profile_id` only. The new default should be used the next time the stack starts.

### Apply now

Applying a profile performs the full runtime activation flow.

## Startup Behavior

On `hermes-agent` container startup, before the gateway fully starts, the service should:

1. read `data/hermes/admin_profiles.json` if it exists
2. find `default_profile_id`
3. materialize that profile into `config.yaml` and `.env`
4. start Hermes using that runtime config

If the default profile is invalid or missing, the startup path should prefer the last known good profile when available. The service should not silently point Open WebUI somewhere else.

## Apply Flow

The approved apply order is:

1. load the selected profile
2. run `Test Connection` with the selected profile values
3. if the test fails, stop immediately and do not write any runtime files
4. backup current Hermes runtime files and current Open WebUI config snapshot
5. write the selected profile into `config.yaml` and `.env`
6. restart `hermes-agent`
7. verify Hermes health and model visibility
8. repair Open WebUI config to point to Hermes
9. restart `open-webui`
10. verify Open WebUI health and model availability path
11. mark the profile as active and last known good
12. persist final status as `ready`

## Why Open WebUI Must Always Point To Hermes

The external provider URL belongs to Hermes, not to Open WebUI.

That means:

- profile switching changes how Hermes reaches the external upstream
- Open WebUI should always connect to Hermes at `http://hermes-agent:8642/v1`
- Open WebUI should always use the current `HERMES_API_KEY`

This separation keeps Open WebUI stable and makes Hermes the only place where external provider routing changes.

## Open WebUI Synchronization Rules

During apply, rewrite the `config.data` JSON in `data/open-webui/webui.db` so that:

- `openai.enable` is true
- `openai.api_base_urls[0]` is `http://hermes-agent:8642/v1`
- `openai.api_keys[0]` is the current `HERMES_API_KEY`
- `openai.api_configs[0]` is enabled and marked as bearer-auth external connection

This repair must happen on every apply because the stored DB state can drift or contain stale endpoints from older projects.

## Health Verification Standards

A profile apply is only successful when all of the following are true.

### Hermes success criteria

- `GET /health` returns HTTP 200
- `GET /v1/models` returns HTTP 200 with auth
- `/v1/models` returns at least one model entry

### Open WebUI success criteria

- `http://localhost:13000` or container-local health endpoint responds successfully
- the persisted Open WebUI connection target is `http://hermes-agent:8642/v1`
- the post-apply verification path can confirm that model visibility should work again

In the first version, the final Open WebUI verification may be based on:

- service health
- correct DB rewrite
- successful Hermes `/v1/models`

If a stronger internal Open WebUI model-list validation endpoint is available and stable, it should be used.

## Failure Handling

The console should be explicit about which phase failed.

### Apply state machine

Use readable phases such as:

- `idle`
- `testing_connection`
- `saving_profile`
- `backing_up_runtime`
- `writing_runtime_config`
- `restarting_hermes`
- `verifying_hermes`
- `syncing_open_webui`
- `restarting_open_webui`
- `verifying_open_webui`
- `ready`
- `failed`
- `rollback_complete`

### Failure rules

- If connection test fails: do not write any runtime files.
- If writing config fails: stop and report the file failure.
- If Hermes restart or verification fails: rollback automatically.
- If Open WebUI sync fails: rollback automatically.
- If Open WebUI restarts but model availability still fails verification: rollback automatically.

### Rollback flow

Rollback restores:

- `config.yaml.bak`
- `.env.bak`
- `open_webui_config.bak.json`

Then it restarts `hermes-agent` and `open-webui`, and records `rollback_complete`.

## Access Control

The admin console uses the current `HERMES_API_KEY` as the unlock secret.

### Rules

- unauthenticated users cannot read current config or profile details
- admin routes require a short-lived session cookie or equivalent server-issued session token
- API responses never return the full provider API key after save
- secrets should not be written into logs

## Deployment Model

This feature targets the local standalone Docker Compose deployment.

To support automatic restarts from inside `hermes-agent`, the service needs access to the Docker Engine socket:

- mount `/var/run/docker.sock` into the `hermes-agent` container

The admin apply logic may then restart sibling containers through the Docker API over the Unix socket.

## API Design

Recommended endpoints:

- `GET /` — admin HTML shell
- `POST /api/admin/auth` — authenticate with current `HERMES_API_KEY`
- `GET /api/admin/profiles` — list saved profiles and current metadata
- `POST /api/admin/profiles` — create a new profile
- `PATCH /api/admin/profiles/{profile_id}` — update an existing profile
- `DELETE /api/admin/profiles/{profile_id}` — delete a profile
- `POST /api/admin/profiles/{profile_id}/test` — test the selected profile
- `POST /api/admin/profiles/{profile_id}/activate` — apply a profile immediately
- `POST /api/admin/profiles/{profile_id}/default` — set default profile
- `GET /api/admin/status` — latest apply state and verification result
- `POST /api/admin/restore` — rollback to previous runtime state

### First implementation slice

To keep delivery safe, the rollout should be incremental:

1. automate Open WebUI repair and current single-profile runtime apply
2. add the local admin page with single-profile edit/apply flow
3. extend that to a multi-profile library and default-profile startup behavior
4. polish UI and operator feedback

This preserves a usable path even before the full profile library is complete.

## Testing Strategy

### Storage and profile tests

- profile library CRUD tests
- masking tests for secrets
- runtime materialization tests for `config.yaml` and `.env`
- backup and restore tests

### Open WebUI sync tests

- rewrite stale `openclaw-hermes-agent` endpoint to `hermes-agent`
- verify API key rewrite
- verify backup snapshot creation

### API tests

- locked vs unlocked root page
- auth success and failure
- profile create/update/list/delete
- test connection success and failure
- apply flow success path
- rollback on partial failure
- status persistence across restart windows

### Integration tests

- default profile materialized on startup
- applying a profile updates Hermes runtime files
- applying a profile repairs Open WebUI DB
- applying a profile produces a usable `/v1/models` path afterwards

## Acceptance Criteria

- Visiting `http://localhost:18642/` shows an admin console, not raw JSON.
- The console is protected by `HERMES_API_KEY`.
- The operator can save multiple upstream profiles.
- One profile can be marked default and is used on startup.
- One profile can be activated immediately from the UI.
- `Test Connection` validates a profile before apply.
- `Apply Now` updates Hermes runtime config, repairs Open WebUI, restarts services, and verifies health.
- Open WebUI stops using stale endpoints such as `http://openclaw-hermes-agent:8642/v1`.
- After successful apply, Open WebUI can select models again.
- Failed applies automatically rollback to the last known good runtime configuration.

## Open Questions Resolved For This Version

- **Should the console save only one config or multiple configs?** Multiple profiles.
- **Should there be a default profile at startup?** Yes.
- **Should apply auto-restart the services?** Yes.
- **Is a short outage acceptable during apply?** Yes, roughly 10 to 30 seconds is acceptable.
- **Should Open WebUI ever connect directly to the external provider?** No.

## Implementation Notes

- Keep the frontend embedded and lightweight. Do not introduce a separate frontend build system.
- Reuse Hermes' existing config writing helpers for runtime files.
- Keep profile-library storage isolated from runtime config mutation logic.
- Keep Docker restart logic isolated behind a dedicated helper module.
- Keep Open WebUI sync logic isolated and deterministic.
