#!/usr/bin/env python3
"""Aevrin PreToolUse hook: blocks unsafe MCP server installs.

Deliberately stdlib-only (no pip install required) so it stays fast and
robust as a hook script matched on nearly every Bash/Write tool call; it
must return well within its settings.json `timeout` budget.

Decision logic (exactly per the master build spec, Section 8):
1. Check for a cached score first (POST /hook/cache, a fast Supabase lookup,
   not a scan).
2. Clean cached score -> allow silently.
3. Cached score shows critical/high -> block, with score + specific
   findings (including file/line and remediation, so the session that just
   got blocked has enough to actually fix the code) + three explicit next
   steps: fix it directly, `aevrin hook allow <target>` to install anyway,
   or `aevrin findings triage <id> false_positive` to dispute a finding.
3a. An active `aevrin hook allow` override for this exact target -> allow,
    once, without re-blocking.
3b. Cached scan's tools failed to run (Docker down, missing binary, no
    network) -> block as "incomplete", never allow_clean, an empty
    findings list from a scan that never ran isn't the same thing as a
    clean one.
4. No cached score -> allow with a visible "not yet scanned" warning. The
   actual background scan is triggered server-side by the /hook/cache call
   itself (FastAPI BackgroundTasks); this script never runs or waits on a
   scan itself, only ever makes one short HTTP request.

Any failure mode (no API key configured, network error, timeout, malformed
response) fails OPEN; allow silently. A security hook that blocks installs
whenever Aevrin itself is unreachable is a hook that gets disabled by
annoyed developers, which defeats the point.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Kept in step with aevrin_cli.services.auth.DEFAULT_API_URL. This file is
# stdlib-only on purpose, so it cannot import that constant.
_DEFAULT_API_URL = "https://api.mcp.aevrin.net"


def _validated_api_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    is_local_dev = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (parsed.scheme != "https" and not is_local_dev) or not parsed.hostname or parsed.username or parsed.password:
        return _DEFAULT_API_URL
    return value.rstrip("/")


API_URL = _validated_api_url(os.environ.get("AEVRIN_API_URL", _DEFAULT_API_URL))


def _load_hook_api_key() -> str | None:
    # AEVRIN_API_KEY stays supported as an override; the normal path is the
    # credentials file `aevrin hook setup` writes, deliberately separate
    # from the CLI's own ~/.aevrin/credentials (addendum §3: hook and CLI
    # usage should be independently attributable even for the same person).
    env_key = os.environ.get("AEVRIN_API_KEY")
    if env_key:
        return env_key
    try:
        with open(os.path.expanduser("~/.aevrin/hook_credentials"), encoding="utf-8") as f:
            data = json.load(f)
            key = data.get("api_key")
            return key if isinstance(key, str) else None
    except (OSError, ValueError):
        return None


API_KEY = _load_hook_api_key()
HTTP_TIMEOUT_S = 4  # keep well under the hook's settings.json `timeout` (recommend 5-8s)

_URL_RE = re.compile(r"https?://[^\s\"']+")
_MCP_ADD_RE = re.compile(r"claude\s+mcp\s+add\b(.*)$")


def _allow(context: str | None = None) -> None:
    output: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }
    if context:
        output["hookSpecificOutput"]["additionalContext"] = context
    print(json.dumps(output))
    sys.exit(0)


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _no_decision() -> None:
    # Not a target we understand (e.g. an unrelated Bash/Write call); stay
    # completely out of the way, no output, no opinion.
    sys.exit(0)


def extract_target(tool_name: str, tool_input: dict[str, Any]) -> tuple[str, str] | None:
    """Returns (target_type, target) for a tool call this hook cares about,
    or None if this call isn't an MCP install this hook should look at."""
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        match = _MCP_ADD_RE.search(command)
        if not match:
            return None
        url_match = _URL_RE.search(command)
        if url_match:
            return "live_mcp_server", url_match.group(0).rstrip("\"')")
        # No URL: likely a stdio server (`-- npx ...` / `-- docker run ...`).
        # Best-effort: reconstruct a single-server mcp.json from the command
        # so the backend can still attempt manifest-level checks. This is
        # intentionally approximate; `claude mcp add` accepts many flag
        # forms and we don't try to fully parse all of them.
        entry = _best_effort_stdio_entry(command)
        return "config_paste", json.dumps({"mcpServers": {"unknown": entry}})

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if not file_path.endswith((".mcp.json", "claude_desktop_config.json")):
            return None
        contents = tool_input.get("file_contents") or tool_input.get("content") or ""
        try:
            parsed = json.loads(contents)
        except json.JSONDecodeError:
            return None
        servers = parsed.get("mcpServers", parsed)
        if not servers:
            return None
        # Prefer a URL if any server declares one; otherwise pass the whole
        # config through for manifest-level checks.
        for entry in servers.values():
            if isinstance(entry, dict) and entry.get("url"):
                return "live_mcp_server", entry["url"]
        return "config_paste", json.dumps({"mcpServers": servers})

    return None


def _best_effort_stdio_entry(command: str) -> dict[str, Any]:
    try:
        tokens = shlex.split(command)
        if "--" in tokens:
            rest = tokens[tokens.index("--") + 1 :]
            if rest:
                return {"command": rest[0], "args": rest[1:]}
    except ValueError:
        pass
    return {"command": command}


def check_cache(target_type: str, target: str) -> dict[str, Any] | None:
    if not API_KEY:
        return None
    body = json.dumps({"target": target, "target_type": target_type}).encode()
    req = urllib.request.Request(
        f"{API_URL}/hook/cache",
        data=body,
        method="POST",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
    )
    try:
        # The URL is either Aevrin's fixed HTTPS API origin or an explicit
        # loopback development origin; it never comes from hook input.
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:  # nosemgrep # nosec B310
            response_body: Any = json.loads(resp.read())
            return response_body if isinstance(response_body, dict) else None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def _block_message(result: dict[str, Any], override_target: str) -> str:
    """The full block explanation: what was found, where, and what to do next.

    Written for Claude reading it in the session that was just blocked, so every
    option names the exact command that resolves it.
    """
    score = result.get("score")
    findings = result.get("findings_summary", [])

    lines = [f"Aevrin: this MCP server scored {score}/100 with unresolved high/critical findings:"]
    for f in findings[:5]:
        loc = f", {f['file_path']}" + (f":{f['line_start']}" if f.get("line_start") else "") if f.get("file_path") else ""
        lines.append(f"  - [{f['severity'].upper()}] {f['title']} ({f['owasp_category']}){loc}")
        if f.get("remediation"):
            lines.append(f"      fix: {f['remediation']}")
        lines.append(f"      finding id: {f['id']}")
    if len(findings) > 5:
        lines.append(f"  ...and {len(findings) - 5} more; see your Aevrin dashboard for the full list.")
    lines.append("")

    options = [
        [
            "Fix it: edit the flagged files yourself (you have full tool access in this",
            "session) using the locations and remediation above, then retry the install.",
        ],
        [f"Install anyway: run `aevrin hook allow {override_target}`, then retry."],
        [
            "False report: if a specific finding above is wrong, run",
            "`aevrin findings triage <finding id> false_positive --reason \"why it is wrong\"`,",
            "then retry.",
        ],
    ]
    lines.append(f"You have {len(options)} options. Ask the person which they want:")
    for i, option_lines in enumerate(options, start=1):
        lines.append(f"  {i}. {option_lines[0]}")
        lines.extend(f"     {rest}" for rest in option_lines[1:])
    return "\n".join(lines)


def _incomplete_message(target_type: str, target_value: str, override_target: str) -> str:
    """An unverifiable scan is not a clean one, so this blocks and says exactly
    which recovery path fits the target."""
    lines = [
        (
            "Aevrin: this target's last scan could not be verified: required scanning "
            "tools failed to run (Docker not running, a missing tool, or no network "
            "access on the machine that scanned it). An empty findings list here does "
            "NOT mean this target is clean."
        ),
        "",
        "You have two options. Ask the person which they want:",
        f"  1. Install anyway: run `aevrin hook allow {override_target}`, then retry, but only",
        "     if you trust the source independently of this scan.",
    ]
    if target_type == "config_paste":
        lines.extend(
            [
                "  2. Re-scan: open the Aevrin dashboard, choose Pasted configuration,",
                "     and scan the MCP configuration on a worker with all tools available.",
            ]
        )
    else:
        lines.extend(
            [
                f"  2. Re-scan: run `aevrin scan {shlex.quote(target_value)}` on a machine",
                "     with Docker running and network access, then retry the install.",
            ]
        )
    return "\n".join(lines)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        _no_decision()
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    target = extract_target(tool_name, tool_input)
    if target is None:
        _no_decision()
        return
    target_type, target_value = target

    if not API_KEY:
        _allow(
            "Aevrin hook is installed but not logged in. This install was not checked. "
            "Aevrin's free tier includes 2 hook auto-scans a month; run `aevrin hook setup` "
            "to get started."
        )
        return

    result = check_cache(target_type, target_value)
    if result is None:
        _allow()  # unreachable/error; fail open, no noise
        return

    decision = result.get("decision")
    override_target = shlex.quote(str(result.get("target_key") or target_value))
    if decision == "allow_override":
        _allow("Aevrin: proceeding, an install-anyway override is active for this target.")
        return

    if decision == "block":
        _deny(_block_message(result, override_target))
        return

    if decision == "block_incomplete":
        _deny(_incomplete_message(target_type, target_value, override_target))
        return

    if decision == "quota_exceeded":
        # Not a security block, exceeding a scan quota isn't a finding, so
        # this stays an allow with an explanatory note, same two-part
        # shape (what happened + where to upgrade) as the CLI/dashboard.
        resets_at = result.get("quota_resets_at")
        upgrade_url = result.get("upgrade_url")
        _allow(
            f"Aevrin: hook scan quota used up for this billing period"
            f"{f' (resets {resets_at})' if resets_at else ''}. "
            f"This install was not checked. Upgrade at {upgrade_url}"
        )
        return

    if decision == "allow_unscanned":
        _allow(
            "Aevrin: this target has not been scanned yet. Allowing for now; a background "
            "scan has been started and will be cached for next time."
        )
        return

    # "allow_clean" or anything else recognized-but-fine
    score = result.get("score")
    _allow(f"Aevrin: clean scan on record (score {score}/100)." if score is not None else None)


if __name__ == "__main__":
    main()
