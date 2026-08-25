"""GitHub App client: "Connect GitHub for Auto-Fix" (V5 prompt §6/§7/§9).

Architecturally separate from two other GitHub touchpoints in this codebase:
- `settings.github_token`: a plain PAT used only for Scorecard/OSV rate
  limits during a scan. Never used here.
- Supabase's GitHub OAuth provider ("Sign in with GitHub", frontend
  login/actions.ts): identity-only, configured directly in the Supabase
  dashboard, grants zero repo access. Never used here either.

This client is JWT-based App auth: sign a short-lived JWT with the App's
private key, exchange it for a per-installation access token, and use that
token for real repo writes (branch, commit, draft PR), scoped by whatever
repos the person granted when they installed the App, enforced by GitHub
itself, not by anything in this codebase.

Prep-only until the user supplies GITHUB_APP_PRIVATE_KEY: every method
raises GithubAppUnavailable if unconfigured, mirroring
razorpay_client.py's RazorpayUnavailable pattern.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from aevrin_api.config import Settings

_API_BASE = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


class GithubAppUnavailable(Exception):
    pass


class GithubAppError(Exception):
    """A configured client made a real API call that failed, distinct from
    GithubAppUnavailable (not configured at all), so callers can tell
    "we can't try" apart from "we tried and GitHub said no"."""


def parse_github_repo(url: str) -> tuple[str, str] | None:
    """'https://github.com/owner/repo(.git)?' -> (owner, repo). None for
    anything else; callers treat that as "not fixable", not an error."""
    if not url.startswith("https://github.com/"):
        return None
    rest = url.removeprefix("https://github.com/").removesuffix(".git").strip("/")
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def sign_install_state(settings: Settings, user_id: str, *, ttl_s: int = 900) -> str:
    """Correlates the GitHub App installation callback (a plain browser
    redirect from GitHub, not an authenticated API call) back to the Aevrin
    user who started it. HMAC'd with the same server-side secret used to
    pepper API keys elsewhere (security.py); this doesn't need a dedicated
    env var, it's a short-lived, single-purpose token, not a credential."""
    expires_at = int(time.time()) + ttl_s
    payload = f"{user_id}.{expires_at}"
    sig = hmac.new(settings.api_key_pepper.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def install_url(settings: Settings, user_id: str) -> str:
    """Where to send someone to install the App, carrying signed state so the
    callback can attribute the installation back to them."""
    state = sign_install_state(settings, user_id)
    return f"https://github.com/apps/{settings.github_app_slug}/installations/new?state={state}"


def verify_install_state(settings: Settings, state: str) -> str | None:
    """Returns the user_id if `state` is a valid, unexpired token from
    sign_install_state above; None for anything forged, malformed, or
    expired; callers treat that as a failed installation, never a crash."""
    try:
        payload = base64.urlsafe_b64decode(state.encode()).decode()
        user_id, expires_at, sig = payload.rsplit(".", 2)
    except (ValueError, UnicodeDecodeError):
        return None
    expected = hmac.new(settings.api_key_pepper.encode(), f"{user_id}.{expires_at}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return None
    if int(expires_at) < int(time.time()):
        return None
    return user_id


@dataclass
class InstallationToken:
    token: str
    expires_at: str


class GithubAppClient:
    def __init__(self, settings: Settings):
        if not settings.github_app_id or not settings.github_app_private_key:
            raise GithubAppUnavailable("GITHUB_APP_ID/GITHUB_APP_PRIVATE_KEY not configured")
        self._app_id = settings.github_app_id
        # An env var holds one line, so GITHUB_APP_PRIVATE_KEY carries the PEM
        # with its newlines written as a literal backslash-n (the README says
        # to flatten it that way, and docker --env-file cannot express a
        # multi-line value at all). PyJWT needs the real thing, and rejects the
        # flattened form with "Could not parse the provided public key", so
        # undo it here. A PEM that already has real newlines contains no such
        # sequence and passes through untouched.
        self._private_key = settings.github_app_private_key.replace("\\n", "\n")

    def _app_jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": self._app_id}
        return jwt.encode(payload, self._private_key, algorithm="RS256")

    async def _app_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self._app_jwt()}",
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            return await client.request(method, f"{_API_BASE}{path}", headers=headers, **kwargs)

    async def _installation_request(self, method: str, path: str, token: str, **kwargs: Any) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": _ACCEPT,
            "X-GitHub-Api-Version": _API_VERSION,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            return await client.request(method, f"{_API_BASE}{path}", headers=headers, **kwargs)

    async def get_repo_installation_id(self, owner: str, repo: str) -> int | None:
        """None means this App isn't installed on this repo; the caller turns
        that into "prompt to connect GitHub", not an error."""
        resp = await self._app_request("GET", f"/repos/{owner}/{repo}/installation")
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise GithubAppError(f"lookup installation failed: {resp.status_code} {resp.text}")
        result: int = resp.json()["id"]
        return result

    async def create_installation_token(self, installation_id: int) -> InstallationToken:
        resp = await self._app_request("POST", f"/app/installations/{installation_id}/access_tokens")
        if resp.status_code >= 400:
            raise GithubAppError(f"create installation token failed: {resp.status_code} {resp.text}")
        body = resp.json()
        return InstallationToken(token=body["token"], expires_at=body["expires_at"])

    async def list_installation_repos(self, token: str, *, max_repos: int = 300) -> list[dict[str, Any]]:
        """Every repository this installation can actually reach.

        Which repos that covers is the person's choice at install time; they
        may have granted the App a handful or all of them, so this is the
        only honest source for "which repos can Aevrin work with". Paginated
        because "all repositories" on a large org is not a small list; capped
        so one enormous account can't stall the request.
        """
        repos: list[dict[str, Any]] = []
        page = 1
        while len(repos) < max_repos:
            resp = await self._installation_request(
                "GET", f"/installation/repositories?per_page=100&page={page}", token
            )
            if resp.status_code >= 400:
                raise GithubAppError(f"list installation repos failed: {resp.status_code} {resp.text}")
            body = resp.json()
            batch = body.get("repositories", [])
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos[:max_repos]

    async def looks_like_mcp_repo(self, owner: str, repo: str, token: str) -> bool | None:
        """Cheap heuristic for labelling a repo in the picker.

        Deliberately *not* authoritative and never used to block a scan: it
        checks only for a committed MCP client config or an MCP SDK
        dependency, so a server that ships neither reads as "not MCP" while
        being perfectly scannable. None means the check itself couldn't run
        (rate limit, permissions); the caller shows no label rather than
        claiming a negative it didn't establish.
        """
        try:
            for path in (".mcp/config.json", "mcp.json", "claude_desktop_config.json"):
                if await self.get_file(owner, repo, path, token) is not None:
                    return True
            for manifest in ("package.json", "pyproject.toml", "requirements.txt"):
                found = await self.get_file(owner, repo, manifest, token)
                if found is None:
                    continue
                content = found[0].lower()
                if "modelcontextprotocol" in content or "mcp-server" in content or "fastmcp" in content:
                    return True
            return False
        except GithubAppError:
            return None

    async def get_installation(self, installation_id: int) -> dict[str, Any]:
        resp = await self._app_request("GET", f"/app/installations/{installation_id}")
        if resp.status_code >= 400:
            raise GithubAppError(f"get installation failed: {resp.status_code} {resp.text}")
        result: dict[str, Any] = resp.json()
        return result

    async def get_file(self, owner: str, repo: str, path: str, token: str) -> tuple[str, str] | None:
        """Returns (decoded text content, blob sha) or None if the file
        doesn't exist at the default branch HEAD."""
        resp = await self._installation_request("GET", f"/repos/{owner}/{repo}/contents/{path}", token)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise GithubAppError(f"get file failed: {resp.status_code} {resp.text}")
        body = resp.json()
        if body.get("encoding") != "base64":
            raise GithubAppError(f"unexpected content encoding: {body.get('encoding')}")
        content = base64.b64decode(body["content"]).decode("utf-8", errors="replace")
        return content, body["sha"]
