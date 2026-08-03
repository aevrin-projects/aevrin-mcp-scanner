"""Stable, privacy-respecting machine identifier for abuse-prevention
(AEVRIN_TIERING_AUTH_LANDING_PROMPT.md §4). Hashed before it ever leaves the
machine — only the SHA-256 digest is sent with a device-flow login request,
never the raw platform ID.
"""

from __future__ import annotations

import hashlib
import platform

# This module executes one fixed OS command; no argv comes from user input.
import subprocess  # nosec B404


def _read_linux_machine_id() -> str | None:
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, encoding="ascii") as f:
                value = f.read().strip()
                if value:
                    return value
        except OSError:
            continue
    return None


def _read_macos_platform_uuid() -> str | None:
    try:
        # Fixed absolute executable and argv, with shell=False.
        out = subprocess.run(  # nosec B603
            ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if "IOPlatformUUID" in line:
            parts = line.split('"')
            if len(parts) >= 4:
                return parts[3]
    return None


def _read_windows_machine_guid() -> str | None:
    try:
        import winreg  # typeshed's winreg stub is Windows-only; mypy on other platforms can't see its members

        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")  # type: ignore[attr-defined]
            return str(value)
    except Exception:  # noqa: BLE001 — registry access can fail in many ways, all equally "no id available"
        return None


def get_machine_id_hash() -> str | None:
    """Returns a SHA-256 hex digest of the OS's own machine identifier, or
    None if it couldn't be read (never fatal — abuse-prevention signals are
    best-effort, per the addendum's own "don't over-build this" guidance)."""
    system = platform.system()
    raw: str | None
    if system == "Linux":
        raw = _read_linux_machine_id()
    elif system == "Darwin":
        raw = _read_macos_platform_uuid()
    elif system == "Windows":
        raw = _read_windows_machine_guid()
    else:
        raw = None

    if not raw:
        return None
    return hashlib.sha256(raw.encode()).hexdigest()
