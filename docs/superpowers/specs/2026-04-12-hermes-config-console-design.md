# Hermes Config Console Design

## Goal

Build a protected configuration console at `http://localhost:18642/` that lets a local user configure Hermes Agent's active LLM provider, API key, base URL, and model name, apply the change immediately, automatically repair Open WebUI's upstream connection, and restore model visibility in `http://localhost:13000` without requiring manual database or container edits.

## Problem Summary

The current Hermes API server root only returns a JSON overview. Users must manually edit `data/hermes/config.yaml`, `data/hermes/.env`, and sometimes `data/open-webui/webui.db` to switch models. The current deployment also has a broken Open WebUI connection record pointing at `http://openclaw-hermes-agent:8642/v1`, while the live Compose service is `http://hermes-agent:8642/v1`. As a result, Hermes itself can respond on `http://localhost:18642/v1/models`, but Open WebUI shows no selectable models.

## Scope

### In Scope

- Replace the root JSON overview at `GET /` with a lightweight admin console HTML page.
- Protect the console with the current `HERMES_API_KEY`.
- Support provider presets plus a custom OpenAI-compatible mode.
- Let the user set:
  - provider
  - API key
  - base URL
  - default model name
- Provide a connection test before saving.
- Persist Hermes configuration into `data/hermes/config.yaml` and `data/hermes/.env`.
- Repair Open WebUI's saved OpenAI connection target and API key in `data/open-webui/webui.db`.
- Restart the relevant containers automatically so the new settings load immediately.
- Verify both Hermes and Open WebUI after apply.

### Out of Scope

- Multi-user authentication and role management.
- A full settings dashboard for every Hermes feature.
- Secret vault integration.
- Model capability introspection beyond basic connectivity testing.
- Supporting multiple concurrent provider profiles in the first version.

## User Personas

### Local operator

Runs the standalone Docker Compose stack on a workstation, wants the fastest possible way to point Hermes at a new API provider, and expects Open WebUI to start showing models again without manual troubleshooting.

### Advanced operator

Uses a custom OpenAI-compatible proxy or gateway, wants to override base URLs manually, and needs visibility into test failures and the currently effective runtime settings.

## UX Overview

The root page becomes a local admin console with two states.

### 1. Locked state

- Shows a single password-style input labeled `Current HERMES_API_KEY`.
- Shows a primary action button labeled `Enter Console`.
- Does not reveal current provider details or stored secrets before authentication.

### 2. Unlocked state

Shows five stacked sections:

1. **Status bar**
   - current health
   - current effective model
   - last apply result
2. **Provider config**
   - provider preset selector: `OpenAI`, `OpenRouter`, `Gemini`, `Custom`
   - base URL input
   - API key input
   - model name input
   - advanced options collapse for apply behavior
3. **Connection testing**
   - `Test Hermes Direct`
   - `Test Open WebUI Visibility`
   - result panel with HTTP status and model IDs returned
4. **Current config summary**
   - current provider
   - current base URL
   - current model
   - masked secret indicator
5. **Apply actions**
   - `Save and Apply Now`
   - `Restore Previous Backup`
   - progress state and recent event log

## Interaction Design

### Provider presets

Selecting a preset pre-fills a recommended base URL:

- `OpenAI` -> `https://api.openai.com/v1`
- `OpenRouter` -> `https://openrouter.ai/api/v1`
- `Gemini` -> `https://generativelanguage.googleapis.com/v1beta/openai`
- `Custom` -> leaves base URL editable and unopinionated

The model field remains manually editable even before successful testing. This avoids a dead end where the user cannot continue because the model list failed to load.

### Test flow

`Test Hermes Direct` performs a minimal provider request using the in-form values without persisting them yet.

Success state shows:

- connection reachable
- tested model name
- any model IDs discovered from the provider if available

Failure state shows:

- failed step
- HTTP status or transport error
- a concise diagnostic message

### Apply flow

`Save and Apply Now` runs an ordered sequence:

1. validate payload
2. backup current files
3. write Hermes config
4. write Hermes secret env
5. repair Open WebUI connection record
6. restart containers
7. poll Hermes health and `/v1/models`
8. verify Open WebUI can see at least one model

The UI shows step-by-step progress so the user can tell whether failure happened during save, sync, restart, or verification.

## System Design

### Entry point

The current root handler in `docker/hermes-agent/hermes-agent-src/gateway/platforms/api_server.py` currently returns JSON. It becomes the HTML console entry point while all existing machine-readable endpoints remain unchanged.

New admin endpoints are added under `/api/admin/*` to keep UI actions separate from OpenAI-compatible API routes.

## Backend endpoints

### `GET /`

Returns the embedded admin HTML.

### `POST /api/admin/auth`

Validates the supplied `HERMES_API_KEY` against the active API server key.

Response:

- success flag
- short-lived admin session token or signed cookie

### `GET /api/admin/config`

Returns a sanitized summary of current runtime config:

- provider
- base URL
- default model
- masked API key presence
- Open WebUI sync target summary

### `POST /api/admin/test-connection`

Uses the supplied form values to test provider connectivity without applying them.

Response includes:

- direct connectivity result
- optional remote model IDs
- a normalized diagnostic string

### `POST /api/admin/apply`

Performs the full apply operation atomically as far as practical.

### `GET /api/admin/status`

Returns the latest apply result and verification summary for the page to refresh after restart.

### `POST /api/admin/restore`

Restores the most recent config and env backups if the last apply produced a bad state.

## Persistence strategy

### Hermes config

Write `data/hermes/config.yaml` fields:

- `model.provider`
- `model.base_url`
- `model.default`

For preset providers, the stored provider should align with Hermes runtime resolution rules:

- `OpenAI` -> `custom` with OpenAI-compatible base URL, or direct named provider if later implementation prefers provider-native auth semantics
- `OpenRouter` -> `openrouter`
- `Gemini` -> `gemini`
- `Custom` -> `custom`

MVP preference: store the exact provider mode Hermes already resolves correctly with the least surprise, even if presets map internally to different provider IDs than the display labels.

### Hermes secrets

Write `data/hermes/.env` provider-specific key variables and clean stale ones that could override the selected provider unexpectedly.

Examples:

- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `GOOGLE_API_KEY`
- `GEMINI_API_KEY`

The apply logic should preserve unrelated env settings already present in the file.

### Backup model

Before any write:

- copy `config.yaml` to `config.yaml.bak`
- copy `.env` to `.env.bak`
- store the last known Open WebUI config JSON snapshot for restore purposes

## Open WebUI synchronization

The current standalone stack mounts `data/open-webui/webui.db`. Hermes apply logic should update the saved `config.data` JSON inside the `config` table so that Open WebUI uses the live Hermes service rather than stale historical endpoints.

Target values:

- OpenAI base URL: `http://hermes-agent:8642/v1`
- OpenAI API key: current `HERMES_API_KEY`

This directly fixes the current known issue where Open WebUI still points to `http://openclaw-hermes-agent:8642/v1` and therefore fails to list models.

## Apply / restart model

The chosen implementation should favor restart over in-process hot reload.

Reasoning:

- Hermes already reads config and env through established startup/runtime resolution paths.
- Restarting is simpler and more reliable than attempting to reload state inside a long-running gateway process.
- Open WebUI also benefits from a clean reconnect cycle after its database config is repaired.

MVP restart behavior:

- restart `hermes-agent`
- restart `open-webui`

Verification after restart:

- `http://hermes-agent:8642/health`
- `http://hermes-agent:8642/v1/models` with bearer auth
- Open WebUI models endpoint or equivalent internal visibility check

## Security model

### Access control

- Console access is gated by the current `HERMES_API_KEY`.
- Admin APIs require a valid admin session issued by `/api/admin/auth`.
- The page should reject unauthenticated reads of current config.

### Secret handling

- Never return full API keys in API responses.
- Mask secrets in UI summaries.
- Avoid logging full request bodies that contain secrets.
- Do not store the admin unlock secret in browser local storage.

### Deployment posture

This feature is intended for the local standalone deployment exposed at `localhost`. It is not a hardened internet-facing admin console.

## Failure handling

### Connection test failure

- Do not write any files.
- Return structured error details.

### Config write failure

- Stop before restart.
- Show which file failed.
- Keep backups intact.

### Open WebUI sync failure

- Do not claim success.
- Surface that Hermes config was updated but WebUI repair failed.
- Offer rollback.

### Restart failure

- Report which container failed to come back healthy.
- Keep the last written config, but make restore available.

### Verification failure

- Mark the run as incomplete even if writes succeeded.
- Persist detailed status for `/api/admin/status`.

## Visual design direction

Use a simple operator-console aesthetic:

- clean single-column layout
- compact cards
- neutral colors with one clear accent
- monospace status details for diagnostics
- obvious success/warning/error states

This should feel utilitarian and trustworthy rather than marketing-oriented.

## Accessibility

- Keyboard reachable form controls
- Visible focus states
- Error messages tied to inputs
- Sufficient contrast for status text
- No hidden critical state only conveyed by color

## Testing strategy

### Backend

- handler tests for auth, config fetch, connection test, apply, and restore
- tests for YAML/env update logic
- tests for Open WebUI SQLite config rewrite
- tests for rollback behavior on partial failure

### UI

- basic route response test for the root page
- form submission tests at the handler level
- if practical, snapshot or HTML assertions for locked vs unlocked state

### Integration

- verify apply updates the persisted Hermes files
- verify Open WebUI config rewrites from `openclaw-hermes-agent` to `hermes-agent`
- verify post-apply health checks succeed when container restart is stubbed or simulated

## Implementation Notes

- Keep the frontend minimal and embedded to avoid introducing a separate frontend build pipeline.
- Add helper functions for config mutation rather than writing ad hoc string replacements inline.
- Keep Open WebUI sync logic isolated so it can be reused later or disabled behind a flag if needed.

## Acceptance Criteria

- Visiting `http://localhost:18642/` shows an admin console instead of raw JSON.
- Entering the current `HERMES_API_KEY` unlocks the page.
- A user can set provider, API key, base URL, and model name from the page.
- `Test Hermes Direct` validates form values before apply.
- `Save and Apply Now` updates Hermes config, repairs Open WebUI, restarts containers, and verifies health.
- After apply, `http://localhost:13000` shows at least one selectable model.
- The known stale Open WebUI connection value `http://openclaw-hermes-agent:8642/v1` is replaced with `http://hermes-agent:8642/v1`.

## Open Questions Deferred from MVP

- Whether provider presets should map to Hermes native providers or a unified custom-provider path internally.
- Whether restart should be executed from inside the container, via Docker socket, via host-side helper, or through a dedicated orchestrator shim.
- Whether the admin session should be cookie-based or bearer-token-based.

These are implementation decisions, not product-definition blockers for the approved design.
