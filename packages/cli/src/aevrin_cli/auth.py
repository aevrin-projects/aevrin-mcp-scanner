"""Device Authorization Grant (RFC 8628) login for the CLI —
AEVRIN_TIERING_AUTH_LANDING_PROMPT.md §2/§3. Same pattern as `gh auth
login` / `aws sso login`: no browser of our own, just a code the person
enters at a URL we print.
"""

from __future__ import annotations

import json
import os
import stat
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

import httpx

from .machine_id import get_machine_id_hash

DEFAULT_API_URL = "https://api-production-2617.up.railway.app"
CREDENTIALS_DIR = Path.home() / ".aevrin"
CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials"
# Separate from the CLI's own credentials — addendum §3: hook and CLI usage
# should be independently attributable even for the same person/account.
HOOK_CREDENTIALS_PATH = CREDENTIALS_DIR / "hook_credentials"


class DeviceLoginError(Exception):
    pass


def api_url() -> str:
    return os.environ.get("AEVRIN_API_URL", DEFAULT_API_URL)


def save_credentials(api_key: str, path: Path = CREDENTIALS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"api_key": api_key}))
    # 0600 — owner read/write only, never world-readable (explicit addendum requirement).
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def load_api_key(path: Path = CREDENTIALS_PATH) -> str | None:
    # AEVRIN_API_KEY stays supported as a CI/scripting override — the
    # credentials file is for interactive use.
    env_key = os.environ.get("AEVRIN_API_KEY")
    if env_key:
        return env_key
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        key = data.get("api_key")
        return key if isinstance(key, str) else None
    except (OSError, json.JSONDecodeError):
        return None


def clear_credentials(path: Path = CREDENTIALS_PATH) -> None:
    path.unlink(missing_ok=True)


def device_login(*, client_kind: str, on_prompt: Callable[[str, str], None] | None = None) -> str:
    """Runs the full device flow against the api service, returns the
    plaintext api_key on success. `on_prompt(user_code, verification_uri)`
    is called once the code is issued, before polling begins, so the caller
    controls exactly how it's displayed (the CLI prints it directly; the
    hook's setup flow may want different phrasing)."""
    base = api_url()
    machine_hash = get_machine_id_hash()

    resp = httpx.post(
        f"{base}/device/code", json={"client_kind": client_kind, "machine_id_hash": machine_hash}, timeout=15
    )
    if resp.status_code >= 400:
        raise DeviceLoginError(f"Could not start login ({resp.status_code}): {resp.text}")
    data = resp.json()
    device_code, user_code = data["device_code"], data["user_code"]
    verification_uri, interval, expires_in = data["verification_uri"], data["interval"], data["expires_in"]

    if on_prompt:
        on_prompt(user_code, verification_uri)
    try:
        webbrowser.open(verification_uri)
    except Exception:  # noqa: BLE001, S110 — headless environments have no browser to open; polling still works
        pass

    deadline = time.monotonic() + expires_in
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            poll = httpx.post(f"{base}/device/token", json={"device_code": device_code}, timeout=15)
        except httpx.HTTPError as exc:
            raise DeviceLoginError(f"Could not reach {base}: {exc}") from exc
        if poll.status_code >= 400:
            raise DeviceLoginError(f"Login poll failed ({poll.status_code}): {poll.text}")
        result = poll.json()
        poll_status = result["status"]
        if poll_status == "approved":
            api_key = result.get("api_key")
            if not api_key:
                raise DeviceLoginError("Server approved the login but returned no key — try again.")
            return str(api_key)
        if poll_status == "slow_down":
            interval += 5
            continue
        if poll_status == "expired_token":
            raise DeviceLoginError("The login code expired. Run this command again.")
        if poll_status == "access_denied":
            raise DeviceLoginError("Login was denied.")
        # authorization_pending — keep polling until expires_in.

    raise DeviceLoginError("Timed out waiting for approval. Run this command again.")
