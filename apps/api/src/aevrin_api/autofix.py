"""Auto-fix orchestration — "Fix It" (V5 prompt §7).

Detection stays deterministic; this only ever acts on a finding a real
scanner already reported. The flow is deliberately linear and each step can
fail closed without opening anything on GitHub:

  generate a patch (Sonnet) -> apply it to a throwaway clone -> re-run the
  *specific* scanner that flagged this finding -> if still present, retry
  generation once with that failure as context -> if it still doesn't
  clear, report failure honestly -> only then open a draft PR.

Never opens a PR that hasn't been independently confirmed, by the same
deterministic tool that raised the finding, to actually resolve it.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path
from uuid import uuid4

from aevrin_scanner_core import Finding
from aevrin_scanner_core.adapters import ADAPTER_BY_TOOL
from aevrin_scanner_core.runner import sanitized_subprocess_env
from anthropic import AsyncAnthropic

from .config import Settings

logger = logging.getLogger("aevrin.autofix")

_SONNET_MODEL = "claude-sonnet-5"
_MAX_FILE_CHARS = 60_000  # keeps cost/latency bounded; larger files fail open with an honest message
_MODEL_TIMEOUT_S = 300.0
_CLONE_TIMEOUT_S = 60
_SCAN_TIMEOUT_S = 180

_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "patched_content": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["patched_content", "explanation"],
    "additionalProperties": False,
}


def _patch_prompt(finding: Finding, file_content: str, *, retry_feedback: str | None) -> str:
    location = finding.location
    retry_block = (
        f"\n\nA previous attempt did not resolve this — the scanner still reported it after that patch, "
        f"with this detail: {retry_feedback}\nProduce a different, more thorough fix this time."
        if retry_feedback
        else ""
    )
    return f"""You are fixing one specific static-analysis finding in an MCP (Model Context Protocol) server codebase. Make the smallest change that actually resolves it — do not refactor unrelated code, do not change formatting elsewhere in the file, do not add comments explaining the fix.

Finding: {finding.title}
Tool: {finding.tool.value}
Severity: {finding.severity.value}
OWASP MCP category: {finding.owasp_category.value}
File: {location.file_path}
Line: {location.line_start or "unknown"}
Description: {finding.description}
Existing remediation guidance: {finding.remediation}
{retry_block}

Full current file content follows. Return the complete corrected file content — every line, not a diff or a snippet — with only the necessary change(s) applied.

--- {location.file_path} ---
{file_content}
"""


async def generate_patch(
    settings: Settings, finding: Finding, file_content: str, *, retry_feedback: str | None = None
) -> str | None:
    """None means generation failed or refused — caller treats that as a
    failed fix attempt, same as a patch that didn't clear re-verification."""
    if not settings.anthropic_api_key:
        return None
    if len(file_content) > _MAX_FILE_CHARS:
        return None
    # Long request, so: stream, and give it real time. A full-file rewrite
    # emits thousands of tokens and the previous non-streaming 60s ceiling
    # made that a coin flip — three of four findings in one live run failed
    # with APITimeoutError and reported "the model is unavailable or the file
    # is too large", which was true of neither. Streaming keeps the
    # connection active so a slow generation completes instead of tripping
    # an idle timeout.
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=_MODEL_TIMEOUT_S)
    try:
        async with client.messages.stream(
            model=_SONNET_MODEL,
            max_tokens=min(8000, len(file_content) // 2 + 2000),
            output_config={"format": {"type": "json_schema", "schema": _PATCH_SCHEMA}},
            messages=[{"role": "user", "content": _patch_prompt(finding, file_content, retry_feedback=retry_feedback)}],
        ) as stream:
            response = await stream.get_final_message()
        if response.stop_reason == "refusal":
            return None
        for block in response.content:
            if block.type == "text":
                parsed = json.loads(block.text)
                content: str = parsed["patched_content"]
                return content
        return None
    except Exception:
        logger.warning("autofix: patch generation failed for finding %s", finding.id, exc_info=True)
        return None
    finally:
        await client.close()


def _findings_equivalent(a: Finding, b: Finding) -> bool:
    """Pragmatic equivalence for "is the finding still there" — same rule
    signature (title) at the same file, since raw tool payload shape
    differs per adapter and title already encodes the specific rule/secret
    type each of these tools reports."""
    return a.title == b.title and a.location.file_path == b.location.file_path


def reverify_finding(finding: Finding, target_dir: str) -> bool:
    """Runs the *specific* scanner that originally flagged `finding` against
    the patched checkout and returns True iff that finding no longer
    appears. Never runs the whole pipeline — just the one tool, which is
    both faster and the actual point: prove this fix against the same
    detector that raised the alarm, not a different one."""
    adapter_cls = ADAPTER_BY_TOOL[finding.tool]
    rescanned = adapter_cls().run(uuid4(), target_dir)
    return not any(_findings_equivalent(finding, f) for f in rescanned)


class CloneError(RuntimeError):
    """Clone failed. The message is always safe to show a user and to log —
    see _redact."""


def _redact(text: str, token: str | None) -> str:
    """git echoes the remote URL back in most failure messages, and with a
    token embedded in that URL an unredacted stderr would write a live
    GitHub credential straight into the logs (and, via the failure_reason
    column, into the dashboard). Never let the raw token out."""
    if not text:
        return ""
    cleaned = text.replace(token, "***") if token else text
    return cleaned.replace("x-access-token:***@", "").strip()


def clone_repo(clone_url: str, *, token: str | None = None) -> str:
    """`token` is a GitHub App installation token. Without it this can only
    reach public repositories — which silently defeated Fix It on exactly
    the private repos the App installation exists to grant access to.
    x-access-token is GitHub's documented username for HTTP-based git auth
    with an installation token.

    The credential does land in the clone's .git/config, which is why the
    caller must always cleanup_clone() — nothing here is ever pushed from,
    so the token's only job is the initial fetch.
    """
    workdir = tempfile.mkdtemp(prefix="aevrin-autofix-")
    repo_dir = f"{workdir}/repo"
    authed_url = (
        clone_url.replace("https://", f"https://x-access-token:{token}@", 1) if token else clone_url
    )
    try:
        subprocess.run(  # nosec B603 B607
            ["git", "clone", "--depth", "1", authed_url, repo_dir],
            capture_output=True,
            text=True,
            timeout=_CLONE_TIMEOUT_S,
            check=True,
            env=sanitized_subprocess_env(),
        )
    except subprocess.CalledProcessError as exc:
        raise CloneError(_redact(exc.stderr or "git clone failed", token)) from None
    except subprocess.TimeoutExpired:
        raise CloneError(f"Cloning the repository timed out after {_CLONE_TIMEOUT_S}s.") from None
    return repo_dir


def cleanup_clone(repo_dir: str) -> None:
    shutil.rmtree(Path(repo_dir).parent, ignore_errors=True)


def write_patched_file(repo_dir: str, relative_path: str, content: str) -> None:
    target = Path(repo_dir) / relative_path
    target.write_text(content, encoding="utf-8")
