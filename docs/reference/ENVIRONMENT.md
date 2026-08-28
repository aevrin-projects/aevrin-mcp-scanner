# Environment reference

Names, purpose, and whether each is secret. Never a value - see
[`../security/SECURITY.md`](../security/SECURITY.md). Source of truth:
`backend/api/aevrin_api/config/settings.py` (backend) and the two deploy
workflows (`deploy-frontend.yml`, `deploy-backend.yml`) for
frontend/CI-only variables.

## Backend (`backend/api`, one `Settings` model - every variable it reads is declared here)

| Variable | Required | Secret | Purpose |
|---|---|---|---|
| `SUPABASE_URL` | yes | no | Supabase project URL; also derives the JWKS endpoint for JWT verification. |
| `SUPABASE_ANON_KEY` | yes | no (public by design) | Supabase anon key. |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | **yes** | Bypasses RLS - the API's trusted-orchestrator identity. |
| `API_KEY_PEPPER` | yes | **yes** | HMAC pepper for hashing CLI/hook API keys before storage. |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | yes | token is secret | Primary Redis (rate limiting, hook cache). |
| `UPSTASH_FALLBACK_REDIS_REST_URL` / `..._TOKEN` | no | token is secret | Failover instance; unset means callers fail open if the primary refuses. |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_S3_ENDPOINT` | yes | keys are secret | Cloudflare R2 (S3-compatible), scan report storage. |
| `R2_BUCKET` | no (default `aevrin-report`) | no | Bucket name. |
| `GITHUB_TOKEN` | no | **yes** | Plain PAT for Scorecard/OSV rate limits and private clone - distinct from the GitHub App below. |
| `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` / `GITHUB_APP_SLUG` | no (all three, or none) | private key is secret | "Connect GitHub." Unset disables Connect (returns 503), not an error. |
| `TRUSTED_PROXY_HOPS` | no (default `1`) | no | How many reverse proxies append to `X-Forwarded-For`. Must match the real deployment topology - see `docs/architecture/DEPLOYMENT.md`. |
| `DEFECTDOJO_URL` / `DEFECTDOJO_API_KEY` | no | key is secret | DefectDojo integration; unset disables it. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` | no | secret/webhook are secret | Billing. Unset means billing is disabled, not broken. |
| `DEEPSEEK_API_KEY` | no | **yes** | Powers LLM triage; unset fails open to the deterministic scanner result. |
| `BYOK_ENCRYPTION_KEY` | no (but required for any encrypted-secret feature) | **yes** | Fernet key encrypting AI provider keys and admin TOTP secrets. Unset disables both at the point of use. Minted automatically on first EC2 deploy if blank - see `backend/deploy/remote-deploy.sh`. |
| `ADMIN_USER_IDS` | no | no (IDs, not credentials) | Comma-separated Supabase user IDs allowed into the admin panel. |
| `ADMIN_SESSION_IDLE_MINUTES` | no (default `30`) | no | Admin session idle timeout. |
| `MARKETPLACE_SCAN_USER_ID` | no | no | Supabase user ID that catalogue (marketplace) scans are attributed to, so they don't land in a real customer's history/quota. Unset disables catalogue scanning. |
| `SCHEDULER_TOKEN` | no (required for `/scheduler/*` to function) | **yes** | Bearer token protecting the scheduled-job endpoints; those routes fail closed without it. |
| `GROQ_CATALOG_API_KEY` / `OPENAI_CATALOG_API_KEY` / `ANTHROPIC_CATALOG_API_KEY` / `GEMINI_CATALOG_API_KEY` | no | **yes** | Aevrin's own credentials for refreshing the public AI-model catalogue - never a customer's key. A provider with no key here just isn't refreshed. |
| `WEB_ORIGIN` | no (default `http://localhost:3000`) | no | The authenticated app's own origin (`frontend/`) - allowed for CORS, and also the base URL for links this API constructs back into that app (device-pairing verification URLs, quota-exceeded upgrade links, the GitHub App post-install redirect). |
| `PUBLIC_WEB_ORIGIN` | no | no | An additional allowed CORS origin for the public marketing site (`frontend-public/`), which calls this API (status checks, pageview tracking) from a different origin than `WEB_ORIGIN`. Never used to construct a link - see `docs/architecture/DEPLOYMENT.md`. |
| `SCANS_PER_USER_PER_HOUR` / `SCANS_PER_IP_PER_HOUR` / `CLI_UPLOADS_PER_KEY_PER_HOUR` | no (sane defaults) | no | Rate limits. |
| `PORT` | no (default `8000`) | no | Listen port. |

## Frontend (`frontend`, build-time and runtime)

| Variable | Where used | Secret |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Every `shared/api` call target | no |
| `NEXT_PUBLIC_SITE_URL` | Canonical URLs, sitemap | no |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase client init | no |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase client init | no (publishable by design) |

All four are read at build time *and* runtime - a placeholder used to
satisfy CI's build step can never reach a deployed page, since the real
value is what the deployed Worker actually reads.

## CI/CD-only (GitHub Actions secrets and environment `vars`, never in application code)

| Name | Used by | Secret |
|---|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | `deploy-backend.yml` (temporary SSH security-group rule) | **yes** |
| `AWS_SECURITY_GROUP_ID` / `AWS_HOST` | `deploy-backend.yml` | ID/host are not sensitive but treated as secrets here for convenience |
| `AWS_SSH_PRIVATE_KEY` | `deploy-backend.yml` (SSH to the EC2 instance) | **yes** |
| `AEVRIN_ENV_OVERRIDES` | `deploy-backend.yml` (optional KEY=VALUE lines applied to `/opt/aevrin/api.env`) | **yes** |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | `deploy-frontend.yml` (`wrangler deploy`) | token is secret |
| `NPM_TOKEN` | `publish-npm.yml` | **yes** |
| (PyPI Trusted Publishing) | `publish.yml` | OIDC - no stored token at all |

## Local operator credential files (not environment variables)

The five `.aws-keys/`, `.github-keys/`, `.cloudflare-keys/`, `.npmjs-key/`,
`.supabase-keys/` directories at the repository root hold `.pem` files used
directly by whoever operates this deployment (e.g. to SSH into the EC2
instance, or to mint the GitHub Actions secrets above) - they are not read
by the running application. See
[`../security/SECURITY.md#local-credential-files`](../security/SECURITY.md#local-credential-files).
