"""Renders a completed scan as a standalone, self-contained HTML report.

Every value is escaped on the way in, and the whole document is inlined so the
saved file keeps working with no network access.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from aevrin_scanner_core import (
    NOT_TESTED_NOTE,
    STAGE_LABELS,
    OwaspMcpCategory,
    StageName,
    category_label,
)

from .styles import REPORT_CSS

_TARGET_TYPE_LABELS = {
    "github_repo": "GitHub repository",
    "live_mcp_server": "Live MCP server",
    "config_paste": "Pasted configuration",
    "local_path": "Local path",
}

_SOURCE_LABELS = {
    "dashboard": "Dashboard scan",
    "cli": "CLI scan",
    "hook": "Claude Code hook scan",
}

_STATUS_LABELS = {
    "queued": "Queued",
    "running": "Running",
    "completed": "Complete",
    "incomplete": "Partial",
    "failed": "Failed",
}

_STAGE_ORDER = [
    StageName.CLONING,
    StageName.STATIC_ANALYSIS,
    StageName.SECRETS,
    StageName.DEPENDENCIES,
    StageName.MCP_ANALYSIS,
    StageName.TOOL_DESCRIPTION_CHECK,
    StageName.AGGREGATING,
]

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]

_SEVERITY_COLORS = {
    "critical": "oklch(0.55 0.24 27)",
    "high": "oklch(0.65 0.2 41)",
    "medium": "oklch(0.72 0.16 80)",
    "low": "oklch(0.6 0.14 245)",
    "info": "oklch(0.65 0 0)",
}

_STAGE_STATUS_COLORS = {
    "done": "oklch(0.64 0.19 145)",
    "failed": _SEVERITY_COLORS["critical"],
    "skipped": "oklch(0.72 0 0)",
    "running": "oklch(0.65 0.18 245)",
    "pending": "oklch(0.85 0 0)",
}

def _stamp(value: datetime) -> str:
    """`%-d` (no zero padding) is a POSIX-only strftime extension that raises on
    Windows, so the day is interpolated directly to keep dev machines working.
    """
    return f"{value:%b} {value.day}, {value:%Y, %H:%M} UTC"


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _score_color(score: int | None) -> str:
    if score is None:
        return _STAGE_STATUS_COLORS["skipped"]
    if score < 40:
        return _SEVERITY_COLORS["critical"]
    if score < 70:
        return _SEVERITY_COLORS["high"]
    if score < 90:
        return _SEVERITY_COLORS["medium"]
    return _STAGE_STATUS_COLORS["done"]


def _verdict_line(status: str, score: object, counts: dict[str, int]) -> str:
    """The conclusion, stated.

    The report showed a score and left the reader to decide what it meant.
    A number without a sentence beside it is the part of a security report
    people misread most.
    """
    if status == "failed":
        return "This scan did not complete"
    if counts["critical"]:
        return "Critical issues need attention before use"
    if counts["high"]:
        return "High-risk findings need review"
    if status == "incomplete":
        return "Inconclusive: some checks did not run"
    if isinstance(score, int) and score >= 90:
        return "No significant issues in the checks that ran"
    if isinstance(score, int) and score >= 70:
        return "Lower-severity issues found"
    return "Review the findings before use"


def _distribution_html(counts: dict[str, int]) -> str:
    total = sum(counts[s] for s in _SEVERITY_ORDER)
    if not total:
        return '<p class="dist-none">No open findings in the checks that ran.</p>'
    bar = "".join(
        f'<span style="width:{counts[s] / total * 100:.4f}%;background:{_SEVERITY_COLORS[s]}"></span>'
        for s in _SEVERITY_ORDER
        if counts[s]
    )
    legend = "".join(
        f'<span class="dist-item">'
        f'<span class="dist-swatch" style="background:{_SEVERITY_COLORS[s]}"></span>'
        f"{s.capitalize()} <span class=\"dist-count\">{counts[s]}</span></span>"
        for s in _SEVERITY_ORDER
        if counts[s]
    )
    return f'<div class="dist"><div class="dist-bar">{bar}</div><div class="dist-legend">{legend}</div></div>'


def _duration_label(created_at: str | None, completed_at: str | None) -> str:
    if not created_at or not completed_at:
        return "Not available"
    try:
        start = datetime.fromisoformat(str(created_at))
        end = datetime.fromisoformat(str(completed_at))
    except ValueError:
        return "Not available"
    seconds = max(0, round((end - start).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s" if seconds else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def _format_datetime(value: str | None) -> str:
    if not value:
        return "Not available"
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return _stamp(parsed.astimezone(UTC))


def _severity_counts(findings: list[dict[str, object]]) -> dict[str, int]:
    counts = {sev: 0 for sev in _SEVERITY_ORDER}
    for finding in findings:
        if finding.get("not_tested") or finding.get("excluded_path"):
            continue
        if finding.get("triage_status") not in (None, "open"):
            continue
        severity = str(finding.get("severity"))
        if severity in counts:
            counts[severity] += 1
    return counts


def _coverage_html(stages: list[dict[str, object]]) -> str:
    """Every stage, with the reason it did not run.

    The old version was six coloured chips with the error hidden in a title
    attribute, which does not survive being printed or being read by anyone
    who cannot hover.
    """
    by_name = {str(s.get("name")): s for s in stages}
    rows = []
    for stage_name in _STAGE_ORDER:
        stage = by_name.get(stage_name.value)
        stage_status = str(stage.get("status")) if stage else "pending"
        color = _STAGE_STATUS_COLORS.get(stage_status, _STAGE_STATUS_COLORS["pending"])
        error = stage.get("error") if stage else None
        rows.append(
            f"""
            <div class="stage">
              <span class="stage-dot" style="background:{color}"></span>
              <span class="stage-name">{_esc(STAGE_LABELS[stage_name])}</span>
              <span class="stage-status">{_esc(stage_status)}</span>
            </div>
            {f'<p class="stage-error">{_esc(error)}</p>' if error else ""}
            """
        )
    return f'<div class="stages">{"".join(rows)}</div>'


def _finding_html(finding: dict[str, object], index: int) -> str:
    severity = str(finding.get("severity", "info"))
    color = _SEVERITY_COLORS.get(severity, _SEVERITY_COLORS["info"])
    location = finding.get("file_path") or finding.get("manifest_field") or "Location not recorded"
    if finding.get("file_path") and finding.get("line_start"):
        location = f"{finding['file_path']}:{finding['line_start']}"
    try:
        category = category_label(OwaspMcpCategory(finding["owasp_category"]))
    except ValueError:
        category = str(finding.get("owasp_category", ""))

    triage = str(finding.get("triage_status") or "open")
    tags = []
    if finding.get("in_kev"):
        tags.append('<span class="tag tag-kev">Known exploited</span>')
    epss_score = finding.get("epss_score")
    if isinstance(epss_score, (int, float)):
        pct = f"{epss_score * 100:.2f}%" if epss_score < 0.01 else f"{epss_score * 100:.0f}%"
        tags.append(f'<span class="tag">EPSS {_esc(pct)}</span>')
    if triage != "open":
        tags.append(f'<span class="tag">{_esc(triage.replace("_", " "))}</span>')

    remediation = str(finding.get("remediation") or "").strip()
    fix_html = (
        f'<div class="fix"><span class="fix-label">Remediation</span><p>{_esc(remediation)}</p></div>'
        if remediation
        else ""
    )

    audit_html = ""
    if triage != "open" and (finding.get("triage_reason") or finding.get("triaged_at")):
        reason = _esc(finding.get("triage_reason") or "No reason recorded")
        when = _esc(_format_datetime(_str_or_none(finding.get("triaged_at"))))
        audit_html = f'<p class="audit">Triaged {when}. {reason}</p>'

    return f"""
    <div class="finding">
      <div class="finding-head">
        <span class="finding-index">{index}</span>
        <span class="sev" style="background:{color}">{_esc(severity)}</span>
        <span class="finding-title">{_esc(finding.get("title", "Untitled finding"))}</span>
        {"".join(tags)}
      </div>
      <p class="finding-meta">{_esc(finding.get("tool", ""))} &middot; {_esc(category)} &middot; <code>{_esc(location)}</code></p>
      <div class="finding-body">
        <p class="finding-desc">{_esc(finding.get("description", ""))}</p>
        {fix_html}
        {audit_html}
      </div>
    </div>
    """


def render_report_html(
    scan: dict[str, object],
    findings: list[dict[str, object]],
    stages: list[dict[str, object]],
) -> str:
    real_findings = [f for f in findings if not f.get("not_tested") and not f.get("excluded_path")]
    excluded_count = sum(1 for f in findings if f.get("excluded_path"))
    active_findings = [f for f in real_findings if f.get("triage_status") in (None, "open")]
    resolved_findings = [f for f in real_findings if f.get("triage_status") not in (None, "open")]
    counts = _severity_counts(findings)
    status = str(scan.get("status", "queued"))
    score = scan.get("score")
    unreliable = scan.get("unreliable_stages")
    unreliable_names = unreliable if isinstance(unreliable, list) else []
    unreliable_labels = [STAGE_LABELS.get(StageName(name), str(name)) for name in unreliable_names]

    trustworthy = status == "completed"
    verdict = _verdict_line(status, score, counts)
    open_total = sum(counts[s] for s in _SEVERITY_ORDER)
    finding_word = "finding" if open_total == 1 else "findings"
    verdict_note = (
        f"{open_total} open {finding_word} across every check that ran."
        if trustworthy
        else "Some checks did not run, so this result is inconclusive rather than clean."
    )

    notice_html = ""
    if status == "incomplete":
        named = ", ".join(unreliable_labels) if unreliable_labels else "One or more stages"
        notice_html = f"""
        <div class="notice notice-warning">
          <p class="notice-title">{_esc(named)} did not complete</p>
          <p>The score reflects only the checks that actually ran. Usually this is Docker not
          running, a missing scanner binary, or no network access. Treat the result as
          inconclusive, not clean.</p>
        </div>
        """
    elif status == "failed":
        notice_html = """
        <div class="notice notice-warning">
          <p class="notice-title">This scan failed</p>
          <p>The results below, if any, are not a reliable assessment of this target.</p>
        </div>
        """

    active_sorted = sorted(
        active_findings, key=lambda f: _SEVERITY_ORDER.index(str(f.get("severity", "info")))
    )
    findings_html = "".join(_finding_html(f, i) for i, f in enumerate(active_sorted, start=1))
    if not active_sorted:
        findings_html = """
        <p class="empty">No open findings in the checks that completed. That is not the same as
        the target being safe: read the coverage section below, and the limitations, before
        relying on this result.</p>
        """

    resolved_html = ""
    if resolved_findings:
        resolved_sorted = sorted(
            resolved_findings, key=lambda f: _SEVERITY_ORDER.index(str(f.get("severity", "info")))
        )
        rows = "".join(_finding_html(f, i) for i, f in enumerate(resolved_sorted, start=1))
        resolved_html = f"""
        <section class="section">
          <div class="section-head">
            <h2 class="section-title serif">Resolved findings</h2>
            <p class="section-sub">Marked fixed or false positive. Kept for audit history, and
            excluded from the counts above.</p>
          </div>
          {rows}
        </section>
        """

    excluded_html = ""
    if excluded_count:
        excluded_word = "finding" if excluded_count == 1 else "findings"
        excluded_html = f"""
        <section class="section">
          <div class="section-head">
            <h2 class="section-title serif">Excluded from scoring</h2>
          </div>
          <p class="empty">{excluded_count} {excluded_word} matched a test or fixture path
          convention, such as a <code>fixtures/</code> directory or a filename like
          <code>*.test.ts</code>. Sample code deliberately written to look vulnerable is not a real
          issue in the shipped server, so these are excluded from the score and from the list
          above.</p>
        </section>
        """

    target = str(scan.get("target", ""))
    target_type_label = _TARGET_TYPE_LABELS.get(
        str(scan.get("target_type")), str(scan.get("target_type"))
    )
    source_label = _SOURCE_LABELS.get(
        str(scan.get("source", "dashboard")), str(scan.get("source", "dashboard"))
    )
    generated_at = _stamp(datetime.now(UTC))
    done_stages = sum(1 for s in stages if str(s.get("status")) == "done")
    stage_total = len(stages) or 6
    score_text = str(score) if isinstance(score, int) else "N/A"
    mcp_text = (
        "Yes" if scan.get("mcp_detected") else ("No" if scan.get("mcp_detected") is False else "Not determined")
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Aevrin Security Report: {_esc(target)}</title>
<style>
{REPORT_CSS}
</style>
</head>
<body>
  <div class="page">
    <div class="masthead">
      <div class="wordmark">Aevrin</div>
      <div class="generated">Generated {_esc(generated_at)}</div>
    </div>

    <p class="doc-title">Security report</p>
    <h1 class="target">{_esc(target)}</h1>
    <p class="target-meta">{_esc(target_type_label)} &middot; {_esc(source_label)} &middot;
      {_esc(_STATUS_LABELS.get(status, status))}</p>

    <hr class="rule" />

    <div class="verdict">
      <div class="verdict-text">
        <p class="verdict-line serif">{_esc(verdict)}</p>
        <p class="verdict-note">{_esc(verdict_note)}</p>
      </div>
      <div class="score">
        <div class="score-number" style="color:{_score_color(score if isinstance(score, int) else None)}">
          {_esc(score_text)}<span class="score-of">/100</span>
        </div>
        <div class="score-label">Score</div>
      </div>
    </div>

    {_distribution_html(counts)}

    <div class="facts">
      <div>
        <div class="fact-label">Scanned</div>
        <div class="fact-value">{_esc(_format_datetime(_str_or_none(scan.get("completed_at")) or _str_or_none(scan.get("created_at"))))}</div>
      </div>
      <div>
        <div class="fact-label">Duration</div>
        <div class="fact-value">{_esc(_duration_label(_str_or_none(scan.get("created_at")), _str_or_none(scan.get("completed_at"))))}</div>
      </div>
      <div>
        <div class="fact-label">Coverage</div>
        <div class="fact-value">{done_stages} of {stage_total} stages</div>
      </div>
      <div>
        <div class="fact-label">MCP detected</div>
        <div class="fact-value">{mcp_text}</div>
      </div>
    </div>

    {notice_html}

    <div class="print-bar print-hide">
      <span>To keep a PDF copy, press <kbd>Ctrl</kbd>/<kbd>Cmd</kbd>+<kbd>P</kbd> and choose
      &ldquo;Save as PDF&rdquo;.</span>
      <button class="print-button" onclick="window.print()">Save as PDF</button>
    </div>

    <section class="section">
      <div class="section-head">
        <h2 class="section-title serif">Findings</h2>
        <p class="section-sub">Open findings from the checks that completed, worst first.
        Limitations are listed separately at the end.</p>
      </div>
      {findings_html}
    </section>

    {resolved_html}

    <section class="section">
      <div class="section-head">
        <h2 class="section-title serif">Coverage</h2>
        <p class="section-sub">Every stage and what it did. A stage that did not run is not a
        stage that passed, so the failures stay visible beside the score.</p>
      </div>
      {_coverage_html(stages)}
    </section>

    {excluded_html}

    <section class="section">
      <div class="section-head">
        <h2 class="section-title serif">Known limitations</h2>
      </div>
      <p class="empty">{_esc(NOT_TESTED_NOTE)}</p>
    </section>

    <div class="footer">
      <strong>How the score works.</strong> It starts at 100 and subtracts severity-weighted
      findings: critical 40 points each, high 20, medium 8, low 3.<br />
      <strong>What it does not mean.</strong> The score is self-reported by this scan and is not
      independently re-verified by Aevrin. It never guarantees safety, and it has to be read
      beside the coverage section: a high score from a scan that only half ran says very little.
    </div>
  </div>
</body>
</html>
"""
