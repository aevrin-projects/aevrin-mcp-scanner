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


def _score_gauge_svg(score: int | None) -> str:
    radius = 54
    circumference = 2 * 3.14159265 * radius
    fraction = 0 if score is None else max(0, min(100, score)) / 100
    offset = circumference * (1 - fraction)
    color = _score_color(score)
    label = "N/A" if score is None else str(score)
    return f"""
    <svg viewBox="0 0 140 140" class="score-gauge" role="img" aria-label="Score {_esc(label)} out of 100">
      <circle cx="70" cy="70" r="{radius}" class="score-gauge-track" />
      <circle cx="70" cy="70" r="{radius}" class="score-gauge-value" stroke="{color}"
        stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" />
      <text x="70" y="64" text-anchor="middle" class="score-gauge-number">{_esc(label)}</text>
      <text x="70" y="86" text-anchor="middle" class="score-gauge-suffix">/ 100</text>
    </svg>
    """


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


def _coverage_bar_html(stages: list[dict[str, object]]) -> str:
    by_name = {str(s.get("name")): s for s in stages}
    segments = []
    for stage_name in _STAGE_ORDER:
        stage = by_name.get(stage_name.value)
        stage_status = str(stage.get("status")) if stage else "pending"
        color = _STAGE_STATUS_COLORS.get(stage_status, _STAGE_STATUS_COLORS["pending"])
        label = STAGE_LABELS[stage_name]
        error = stage.get("error") if stage else None
        segments.append(
            f"""
            <div class="coverage-segment">
              <div class="coverage-chip" style="background:{color}" title="{_esc(error) if error else ''}"></div>
              <div class="coverage-label">{_esc(label)}</div>
              <div class="coverage-status">{_esc(stage_status)}</div>
            </div>
            """
        )
    return f'<div class="coverage-bar">{"".join(segments)}</div>'


def _finding_card_html(finding: dict[str, object]) -> str:
    severity = str(finding.get("severity", "info"))
    color = _SEVERITY_COLORS.get(severity, _SEVERITY_COLORS["info"])
    location = finding.get("file_path") or finding.get("manifest_field") or "Not available"
    if finding.get("file_path") and finding.get("line_start"):
        location = f"{finding['file_path']}:{finding['line_start']}"
    try:
        category = category_label(OwaspMcpCategory(finding["owasp_category"]))
    except ValueError:
        category = str(finding.get("owasp_category", ""))
    triage = str(finding.get("triage_status") or "open")
    triage_badge = "" if triage == "open" else f'<span class="triage-chip">{_esc(triage.replace("_", " "))}</span>'
    kev_badge = '<span class="kev-chip">KEV</span>' if finding.get("in_kev") else ""
    epss_score = finding.get("epss_score")
    epss_badge = ""
    if isinstance(epss_score, (int, float)):
        pct = f"{epss_score * 100:.2f}%" if epss_score < 0.01 else f"{epss_score * 100:.0f}%"
        epss_badge = f'<span class="epss-chip">EPSS {_esc(pct)}</span>'
    triage_audit = ""
    if triage != "open" and (finding.get("triage_reason") or finding.get("triaged_at")):
        triage_audit = f"""
        <div class="finding-remediation">
          <span class="finding-remediation-label">Triage record</span>
          <p>{_esc(finding.get("triage_reason") or "No reason recorded")}</p>
          <p>{_esc(_format_datetime(_str_or_none(finding.get("triaged_at"))))}</p>
        </div>
        """
    return f"""
    <div class="finding-card" style="border-left-color:{color}">
      <div class="finding-head">
        <span class="severity-chip" style="background:{color}">{_esc(severity)}</span>
        <span class="finding-title">{_esc(finding.get("title", "Untitled finding"))}</span>
        {kev_badge}
        {epss_badge}
        {triage_badge}
      </div>
      <div class="finding-meta">
        <span>{_esc(finding.get("tool", ""))}</span>
        <span>&middot;</span>
        <span>{_esc(category)}</span>
        <span>&middot;</span>
        <span>{_esc(location)}</span>
      </div>
      <p class="finding-desc">{_esc(finding.get("description", ""))}</p>
      <div class="finding-remediation">
        <span class="finding-remediation-label">Remediation</span>
        <p>{_esc(finding.get("remediation", ""))}</p>
      </div>
      {triage_audit}
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

    warning_html = ""
    if status == "incomplete":
        warning_html = f"""
        <div class="callout callout-warning">
          <strong>Partial scan coverage.</strong> Required scanners did not complete for
          {_esc(", ".join(unreliable_labels)) if unreliable_labels else "one or more stages"}.
          The score above reflects only the checks that actually ran &mdash; treat this as
          inconclusive, not clean.
        </div>
        """
    elif status == "failed":
        warning_html = """
        <div class="callout callout-warning">
          <strong>Scan failed.</strong> This scan did not complete. The results below, if any,
          are not a reliable assessment of this target.
        </div>
        """

    active_sorted = sorted(active_findings, key=lambda f: _SEVERITY_ORDER.index(str(f.get("severity", "info"))))
    findings_html = "".join(_finding_card_html(f) for f in active_sorted)
    if not active_sorted:
        findings_html = """
        <div class="empty-state">
          No active findings in completed checks. That does not mean the target is fully
          safe &mdash; review the stage coverage and documented limitations below before
          trusting this result.
        </div>
        """

    resolved_html = ""
    if resolved_findings:
        resolved_sorted = sorted(
            resolved_findings, key=lambda f: _SEVERITY_ORDER.index(str(f.get("severity", "info")))
        )
        resolved_html = f"""
        <h2 class="section-title">Resolved findings</h2>
        <p class="section-subtitle">Marked fixed or false-positive &mdash; kept here for audit history.</p>
        {"".join(_finding_card_html(f) for f in resolved_sorted)}
        """

    target = str(scan.get("target", ""))
    target_type_label = _TARGET_TYPE_LABELS.get(str(scan.get("target_type")), str(scan.get("target_type")))
    source_label = _SOURCE_LABELS.get(str(scan.get("source", "dashboard")), str(scan.get("source", "dashboard")))
    generated_at = _stamp(datetime.now(UTC))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Aevrin Security Report &mdash; {_esc(target)}</title>
<style>
{REPORT_CSS}
</style>
</head>
<body>
  <div class="page">
    <div class="brand-row">
      <div class="brand">Aevrin</div>
      <div class="generated">Generated {_esc(generated_at)}</div>
    </div>

    <div class="callout callout-info print-hide">
      <strong>Want a PDF copy?</strong> Press <kbd>Ctrl/Cmd+P</kbd> and choose &ldquo;Save as PDF&rdquo;,
      or use the button below.
      <button class="print-button" onclick="window.print()">Print / Save as PDF</button>
    </div>

    <div class="status-chip">{_esc(_STATUS_LABELS.get(status, status))}</div>
    <h1>{_esc(target)}</h1>
    <p class="target-type">{_esc(target_type_label)} &middot; {_esc(source_label)}</p>

    <div class="hero">
      {_score_gauge_svg(score if isinstance(score, int) else None)}
      <div class="meta-grid">
        <div class="meta-item"><div class="meta-label">Scanned at</div><div class="meta-value">{_esc(_format_datetime(_str_or_none(scan.get("completed_at")) or _str_or_none(scan.get("created_at"))))}</div></div>
        <div class="meta-item"><div class="meta-label">Duration</div><div class="meta-value">{_esc(_duration_label(_str_or_none(scan.get("created_at")), _str_or_none(scan.get("completed_at"))))}</div></div>
        <div class="meta-item"><div class="meta-label">Coverage</div><div class="meta-value">{sum(1 for s in stages if str(s.get("status")) == "done")}/{len(stages) or 6} stages complete</div></div>
        <div class="meta-item"><div class="meta-label">MCP detected</div><div class="meta-value">{"Yes" if scan.get("mcp_detected") else ("No" if scan.get("mcp_detected") is False else "N/A")}</div></div>
      </div>
    </div>

    <div class="severity-row">
      <div class="severity-count"><div class="count" style="color:{_SEVERITY_COLORS['critical']}">{counts['critical']}</div><div class="label">Critical</div></div>
      <div class="severity-count"><div class="count" style="color:{_SEVERITY_COLORS['high']}">{counts['high']}</div><div class="label">High</div></div>
      <div class="severity-count"><div class="count" style="color:{_SEVERITY_COLORS['medium']}">{counts['medium']}</div><div class="label">Medium</div></div>
      <div class="severity-count"><div class="count" style="color:{_SEVERITY_COLORS['low']}">{counts['low']}</div><div class="label">Low</div></div>
    </div>

    {warning_html}

    <h2 class="section-title">Coverage</h2>
    <p class="section-subtitle">Keep skipped and failed scanner stages visible so the score is not mistaken for complete coverage.</p>
    {_coverage_bar_html(stages)}

    <h2 class="section-title">Findings</h2>
    <p class="section-subtitle">Active findings from completed checks. Limitation notices are listed separately below.</p>
    {findings_html}

    {resolved_html}

    {f'<h2 class="section-title">Excluded findings</h2><div class="callout callout-info">{_esc(f"{excluded_count} finding(s) matched a test or fixture path convention (a fixtures/-style directory, or a filename like *.test.ts) and are excluded from the score and the list above, sample code deliberately written to look vulnerable is not a real issue in the shipped server.")}</div>' if excluded_count else ""}

    <h2 class="section-title">Coverage limitations</h2>
    <div class="callout callout-info">{_esc(NOT_TESTED_NOTE)}</div>

    <div class="footer">
      Score method: starts at 100 and subtracts severity-weighted findings &mdash; critical &minus;40,
      high &minus;20, medium &minus;8, low &minus;3. Self-reported by this scan, not independently
      re-verified by Aevrin. The score never guarantees safety; coverage and failed stages must be
      read alongside it.
    </div>
  </div>
</body>
</html>
"""
