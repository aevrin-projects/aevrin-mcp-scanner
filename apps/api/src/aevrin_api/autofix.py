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

import httpx
from aevrin_scanner_core import Finding
from aevrin_scanner_core.adapters import ADAPTER_BY_TOOL
from aevrin_scanner_core.runner import sanitized_subprocess_env

from .config import Settings
from .deepseek import PRO_MODEL, DeepSeekError, parse_json_object, stream_json

logger = logging.getLogger("aevrin.autofix")


class PatchFailed(Exception):
    """Carries a reason meant for the person reading it on the dashboard.

    generate_patch used to return None for every failure — no key, file too
    big, model error, truncation, malformed reply — and the caller rendered
    one guess for all of them: "the model is unavailable or the file is too
    large". That sentence was wrong in production for a file that was
    neither, and left nothing behind to diagnose.
    """

# The model never sees a whole large file. It sees the lines around the
# finding plus the top of the file, and rewrites only those. This is both
# cheaper and safer: a region it was never shown is a region it cannot
# accidentally rewrite.
#
# The head matters because a real fix usually spans two places: the call site
# and an import. Swapping `exec` for `execFile` is not a fix if the import
# still says `exec`.
_HEAD_LINES = 40          # imports and preamble live here
_CONTEXT_LINES = 60       # either side of the finding
_WHOLE_FILE_LINES = 400   # below this, the regions would cover it anyway

# A ceiling on what gets sent, applied to the extracted regions rather than
# the file. Previously a 60k-char *file* was rejected outright and — the real
# problem — returned None with no log at all, so the failure surfaced to the
# user as a guess ("the model is unavailable or the file is too large") and
# left nothing behind to diagnose it with.
_MAX_REGION_CHARS = 60_000
_MODEL_TIMEOUT_S = 300.0
_CLONE_TIMEOUT_S = 60
_SCAN_TIMEOUT_S = 180

# Fix It always uses the strong model regardless of plan. A patch is opened
# as a pull request against someone's repository, so a cheaper model saving
# fractions of a cent is not a trade worth making on the one output that
# writes to a user's code.
_PATCH_SYSTEM_PROMPT = """You are fixing one specific static-analysis finding in a Model Context Protocol (MCP) server codebase.

Make the smallest change that actually resolves the finding. Do not refactor unrelated code, do not restyle or reformat lines you are not fixing, and do not add comments explaining the fix.

You are not shown the whole file. You are shown one or more numbered excerpts from it. Everything outside those excerpts stays exactly as it is and is not yours to change.

Reply with a single json object:
- "patched_excerpts": an array of strings, exactly one per excerpt you were given, in the same order. Each string is the complete replacement text for that excerpt: every line of it, rewritten or unchanged. Never a diff, never a fragment, never an elision like "... rest unchanged". Return an excerpt unchanged if it needs no edit.
- "explanation": one sentence on what you changed and why it resolves the finding.

Rules:
- Preserve the file's existing indentation style and quoting style exactly.
- Do not add comments explaining the fix.
- An excerpt starts and ends mid-file. Do not add or remove enclosing braces, brackets, or indentation levels to "balance" it; it is already balanced in context.
- If the fix needs an import or a require that is not in any excerpt you were given, add it to the first excerpt, which is the top of the file.
- If the finding cannot be fixed by editing this file, return every excerpt unchanged and say so in "explanation" rather than inventing a change."""


def _extract_regions(
    file_content: str, line_start: int | None, line_end: int | None
) -> list[tuple[int, int]]:
    """Half-open [start, end) line ranges to send to the model.

    Returns one region when the finding is near the top of the file or the
    file is small enough that windowing buys nothing, otherwise two: the
    head (imports) and the window around the finding.
    """
    total = len(file_content.splitlines())
    if line_start is None or total <= _WHOLE_FILE_LINES:
        return [(0, total)]

    lines = file_content.splitlines()
    focus_start = _snap_to_blank_line(lines, max(0, line_start - 1 - _CONTEXT_LINES))
    focus_end = _snap_to_blank_line(lines, min(total, (line_end or line_start) + _CONTEXT_LINES))
    # Snapping must never pull the boundary past the finding itself.
    focus_start = min(focus_start, max(0, line_start - 1))
    focus_end = max(focus_end, min(total, line_end or line_start))
    head_end = min(_HEAD_LINES, total)

    # Overlapping or adjacent regions become one: two excerpts that touch
    # would be spliced back with a phantom boundary between them.
    if focus_start <= head_end:
        return [(0, focus_end)]
    return [(0, head_end), (focus_start, focus_end)]


_BRACKETS = {"{": "}", "[": "]", "(": ")"}
_CLOSERS = {v: k for k, v in _BRACKETS.items()}


def _bracket_delta(text: str) -> dict[str, int]:
    """Net open-minus-close count per bracket type.

    An excerpt starts and ends mid-file, so it is normally unbalanced — a
    window into the middle of a function has more openers than closers. What
    must not change is *how* unbalanced it is. A rewrite that alters this has
    added or dropped a brace, which silently shifts every line after the
    splice point and corrupts the file even when the fix itself is correct.

    Not a parser: quotes and comments are not tracked. It is a cheap
    tripwire for the specific failure it exists to catch, and a false
    positive only costs one discarded patch.
    """
    delta = dict.fromkeys(_BRACKETS, 0)
    for char in text:
        if char in _BRACKETS:
            delta[char] += 1
        elif char in _CLOSERS:
            delta[_CLOSERS[char]] -= 1
    return delta


def _snap_to_blank_line(lines: list[str], index: int, *, search: int = 12) -> int:
    """Nudge a region boundary onto a blank line when one is close by.

    A window that starts and ends between top-level declarations is far
    easier to rewrite correctly than one cutting through the middle of a
    function body, and it removes most of the temptation to "close" a
    dangling block.
    """
    for offset in range(search):
        for candidate in (index - offset, index + offset):
            if 0 <= candidate < len(lines) and not lines[candidate].strip():
                return candidate
    return index


def _render_regions(file_content: str, regions: list[tuple[int, int]]) -> str:
    """Excerpts with real file line numbers, so the model can place the
    finding's reported line and reason about what surrounds it."""
    lines = file_content.splitlines()
    blocks: list[str] = []
    for index, (start, end) in enumerate(regions):
        body = "\n".join(lines[start:end])
        label = "top of file" if start == 0 else f"lines {start + 1}-{end}"
        blocks.append(f"--- excerpt {index} ({label}) ---\n{body}")
    return "\n\n".join(blocks)


def _splice_regions(
    file_content: str, regions: list[tuple[int, int]], replacements: list[str]
) -> str:
    """Put the rewritten excerpts back. Applied last-region-first so earlier
    line offsets stay valid while later ones are being replaced."""
    lines = file_content.splitlines(keepends=True)
    ends_with_newline = file_content.endswith("\n")

    for (start, end), replacement in sorted(zip(regions, replacements, strict=True), reverse=True):
        new_lines = replacement.splitlines(keepends=True)
        # An excerpt that is not the file's tail must end in a newline, or
        # splicing would weld its last line onto the next untouched one.
        if new_lines and end < len(lines) and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        lines[start:end] = new_lines

    result = "".join(lines)
    if ends_with_newline and not result.endswith("\n"):
        result += "\n"
    return result


def _patch_prompt(
    finding: Finding, file_content: str, regions: list[tuple[int, int]], *, retry_feedback: str | None
) -> str:
    location = finding.location
    retry_block = (
        f"\n\nA previous attempt did not resolve this — the scanner still reported it after that patch, "
        f"with this detail: {retry_feedback}\nProduce a different, more thorough fix this time."
        if retry_feedback
        else ""
    )
    return f"""Finding: {finding.title}
Tool: {finding.tool.value}
Severity: {finding.severity.value}
OWASP MCP category: {finding.owasp_category.value}
File: {location.file_path}
Line: {location.line_start or "unknown"}
Description: {finding.description}
Existing remediation guidance: {finding.remediation}

You are given {len(regions)} excerpt(s). Return exactly {len(regions)} string(s) in "patched_excerpts", in this order.{retry_block}

{_render_regions(file_content, regions)}
"""


async def generate_patch(
    settings: Settings, finding: Finding, file_content: str, *, retry_feedback: str | None = None
) -> str:
    """Raises PatchFailed with a specific, user-facing reason. Every failure
    path is also logged, including the file-size one, which previously
    returned silently and so left a real production failure with no trace."""
    if not settings.deepseek_api_key:
        logger.warning("autofix: no model key configured, cannot fix finding %s", finding.id)
        raise PatchFailed("Automatic fixes aren't configured on this deployment yet.")

    regions = _extract_regions(file_content, finding.location.line_start, finding.location.line_end)
    rendered = _render_regions(file_content, regions)
    if len(rendered) > _MAX_REGION_CHARS:
        logger.warning(
            "autofix: finding %s needs %d chars of context, over the %d ceiling",
            finding.id, len(rendered), _MAX_REGION_CHARS,
        )
        raise PatchFailed(
            "This finding needs more surrounding code than one request can carry. "
            "It needs a manual fix."
        )

    try:
        result = await stream_json(
            api_key=settings.deepseek_api_key,
            model=PRO_MODEL,
            system_prompt=_PATCH_SYSTEM_PROMPT,
            user_prompt=_patch_prompt(finding, file_content, regions, retry_feedback=retry_feedback),
            # Only the excerpts come back, not the file, so this scales with
            # the region size rather than the repository's largest file.
            max_tokens=min(32_000, len(rendered) // 2 + 8_000),
            timeout_s=_MODEL_TIMEOUT_S,
        )
    except (DeepSeekError, httpx.HTTPError) as exc:
        logger.warning("autofix: model call failed for finding %s", finding.id, exc_info=True)
        raise PatchFailed("The model could not be reached while drafting the fix. Try again.") from exc

    if result.truncated:
        # A truncated rewrite is a half-written file. Opening a PR with that
        # would be worse than not fixing at all.
        logger.warning("autofix: patch for finding %s hit the token ceiling, discarding", finding.id)
        raise PatchFailed("The drafted fix was cut short, so it was discarded rather than opened as a partial change.")

    try:
        excerpts = parse_json_object(result.content)["patched_excerpts"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("autofix: unusable model response for finding %s", finding.id, exc_info=True)
        raise PatchFailed("The drafted fix came back malformed and was discarded.") from exc

    if not isinstance(excerpts, list) or len(excerpts) != len(regions):
        logger.warning(
            "autofix: finding %s got %s excerpts back for %d regions",
            finding.id, len(excerpts) if isinstance(excerpts, list) else type(excerpts).__name__, len(regions),
        )
        raise PatchFailed("The drafted fix did not cover the whole affected region and was discarded.")
    if not all(isinstance(e, str) for e in excerpts):
        logger.warning("autofix: finding %s returned a non-string excerpt", finding.id)
        raise PatchFailed("The drafted fix came back malformed and was discarded.")

    lines = file_content.splitlines()
    for index, ((start, end), replacement) in enumerate(zip(regions, excerpts, strict=True)):
        original = "\n".join(lines[start:end])
        if _bracket_delta(original) != _bracket_delta(replacement):
            logger.warning(
                "autofix: finding %s excerpt %d changed bracket balance, discarding",
                finding.id, index,
            )
            raise PatchFailed(
                "The drafted fix would have unbalanced the file's brackets, so it was discarded."
            )

    patched = _splice_regions(file_content, regions, excerpts)
    if file_content.strip() and not patched.strip():
        # Blanking the file is never the fix, and committing it would be
        # destructive in a way a reviewer might not catch in a large diff.
        logger.warning("autofix: patch for finding %s emptied the file, discarding", finding.id)
        raise PatchFailed("The drafted fix would have emptied the file, so it was discarded.")
    if patched == file_content:
        # The model was explicitly told to do this when a fix isn't possible
        # from this file alone, so it is a real answer rather than an error.
        logger.info("autofix: model returned finding %s unchanged", finding.id)
        raise PatchFailed("This finding can't be resolved by changing this file alone. It needs a manual fix.")
    return patched


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
