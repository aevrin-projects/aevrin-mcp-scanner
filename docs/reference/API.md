# API reference

Route inventory, extracted directly from `backend/api/aevrin_api/routes/`
(each domain's `APIRouter(prefix=...)` plus its decorated handlers) - not
restated from memory. This is a map to the code, not a second
specification that can drift from it: for exact request/response shapes,
read the route's own docstring (published as its OpenAPI `description`)
and its `schemas/` module, or the live `/docs` (FastAPI's generated Swagger
UI) against a running instance. Auth is `Authorization: Bearer` (Supabase
JWT) unless noted.

| Prefix | File | Routes |
|---|---|---|
| `/account` | `account.py` | `GET /usage` |
| `/admin` | `admin.py` | `GET /session`, `POST /totp/enrol`, `POST /totp/verify`, `GET /users`, `GET /users/{id}`, `POST /users/{id}/status`, `POST /users/{id}/plan`, `POST /users/{id}/seats`, `POST /users/{id}/overrides`, `DELETE /users/{id}/overrides/{bucket}`, `DELETE /users/{id}`, `POST /users/{id}/reset-usage`, `POST /users/{id}/password-reset`, `GET /analytics`, `GET /account-usage`, `GET /audit`, `GET /login-attempts` |
| `/admin/marketplace` | `admin_marketplace.py` | `GET /summary`, `GET /mcp`, `POST /mcp`, `PATCH /mcp/{listing_id}`, `POST /mcp/{listing_id}/status`, `POST /mcp/{listing_id}/scan`, `GET /submissions`, `POST /submissions/{id}/decision`, `GET /reports`, `POST /reports/{id}/decision` |
| `/agents` | `agents.py` | `POST /snapshots`, `GET ""`, `GET /mcp-servers`, `GET /skills`, `GET /permissions`, `GET /attack-paths`, `GET /{id}`, `DELETE /{id}` |
| `/ai` | `ai.py` | `GET /providers`, `PUT /providers`, `PATCH /providers/{provider}`, `DELETE /providers/{provider}`, `GET /models`, `POST /explain` |
| `/api-keys` | `api_keys.py` | `POST ""`, `GET ""`, `DELETE /{key_id}` |
| `/auth` | `auth_lookup.py` | `GET /lookup` |
| `/billing` | `billing.py` | `GET /pricing`, `POST /checkout`, `POST /verify`, `POST /webhook`, `GET /subscription`, `GET /payments` |
| `/cli` | `cli.py` | `GET /precheck` (`X-API-Key`), `POST /upload` (`X-API-Key`) |
| `/device` | `device.py` | `POST /code`, `POST /token`, `GET /{user_code}`, `POST /{user_code}/approve` |
| `/events` | `events.py` | `POST /pageview` |
| `/scans` (export) | `export.py` | `GET /{scan_id}/export` |
| `/findings` | `findings.py` | `GET /{id}`, `PATCH /{id}` (`X-API-Key` accepted, for CLI triage) |
| `/github` | `github.py` | `GET /status`, `GET /repos`, `GET /install-url`, `GET /callback` |
| `/hook` | `hook.py` | `POST /override` (`X-API-Key`), `GET /cache`, `POST /cache` |
| `/marketplace` | `marketplace.py` | `GET /mcp`, `GET /categories`, `GET /mcp/{slug}`, `POST /mcp/{slug}/install-plan`, `POST /submissions`, `GET /submissions`, `POST /mcp/{id}/report`, `PUT /mcp/{id}/favorite`, `GET /favorites`, `GET /policy`, `PUT /policy` |
| `/orgs` | `orgs.py` | `GET /permissions`, `GET /me`, `POST ""`, `PATCH ""`, `POST /leave`, `GET /members`, `PATCH /members/{id}`, `DELETE /members/{id}`, `GET /invites`, `POST /invites`, `DELETE /invites/{id}`, `POST /invites/{id}/accept`, `GET /roles`, `POST /roles`, `PATCH /roles/{id}`, `DELETE /roles/{id}` |
| `/scans` | `scans.py` | `POST ""`, `POST /upload` (`X-API-Key`), `GET /{id}/diff`, `GET ""`, `DELETE ""`, `GET /{id}`, `DELETE /{id}`, `GET /{id}/stages`, `GET /{id}/findings` |
| `/scheduler` | `scheduler.py` | `POST /registry-sync`, `POST /provider-sync`, `POST /uptime-check`, `GET /scan-queue` - all gated by `require_scheduler_token` (HMAC comparison against `SCHEDULER_TOKEN`, fails closed if unconfigured), not a user session |
| `/status` | `status.py` | `GET /history` - **unauthenticated by design**: it is the data behind the public status page, which has to stay readable when nobody can sign in. Carries no user, org, or scan data. |

`GET /health` is registered directly in `main.py`, outside `ROUTERS`.

## Notable behavioral details worth knowing before calling a route

- **`GET /cli/precheck`** returns `402` with `{bucket, resets_at,
  upgrade_url}` when quota is exhausted, `401` for an invalid/revoked key -
  the CLI's `_authenticated_preflight()` renders both directly rather than
  making a scan attempt that would fail anyway.
- **`PATCH /findings/{id}`** accepts either a user session or `X-API-Key`
  (the hook and `aevrin findings triage` both use the API key path).
  `false_positive` requires a `reason`.
- **`/scheduler/*`** routes authenticate with a static bearer-style token,
  not a user or API-key identity - they're meant to be called by an
  external scheduler (EventBridge, a cron container), not a human.
- **`GET /marketplace/mcp/{slug}`** returns `404`, not `403`, for a private
  listing the caller isn't authorized to see - existence itself isn't
  leaked to an unauthorized caller.
- **`admin_marketplace.py`**'s edit route (`PATCH /mcp/{listing_id}`)
  writes only from `services/marketplace/admin.py`'s `EDITABLE_FIELDS`
  allow-list, which contains no security-bearing column - an admin can
  correct curation metadata, never a grade.

## Adding a route

New file in `routes/`, registered in `routes/__init__.py`'s `ROUTERS` list
- that's the only place a router needs adding; `main.py` never changes for
a new domain. Update this file and
[`../architecture/BACKEND.md`](../architecture/BACKEND.md) in the same
change, per `CLAUDE.md`'s
[maintenance matrix](../../CLAUDE.md#documentation-maintenance-matrix).
