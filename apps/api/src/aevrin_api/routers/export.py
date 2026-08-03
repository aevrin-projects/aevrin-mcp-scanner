from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from aevrin_scanner_core import (
    NOT_TESTED_NOTE,
    STAGE_LABELS,
    OwaspMcpCategory,
    StageName,
    category_label,
)
from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..db import SupabaseRest
from ..deps import get_current_user, get_db
from ..r2_client import presigned_report_url, upload_report
from ..security import AuthenticatedUser

router = APIRouter(prefix="/scans", tags=["export"])

_TARGET_TYPE_LABELS = {
    "github_repo": "GitHub repository",
    "live_mcp_server": "Live MCP server",
    "config_paste": "Pasted configuration",
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


@router.get("/{scan_id}/export")
async def export_report(
    scan_id: UUID,
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[SupabaseRest, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    scan_rows = await db.select("scans", {"id": str(scan_id), "user_id": user.id})
    if not scan_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    scan = scan_rows[0]
    findings = await db.select("findings", {"scan_id": str(scan_id), "user_id": user.id})
    stages = await db.select("scan_stages", {"scan_id": str(scan_id)})

    report = _render_html(scan, findings, stages)
    key = f"reports/{user.id}/{scan_id}.html"
    upload_report(key, report.encode(), "text/html; charset=utf-8", settings)
    url = presigned_report_url(key, settings)
    return {"url": url}


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
    return parsed.astimezone(UTC).strftime("%b %-d, %Y, %H:%M UTC")


def _severity_counts(findings: list[dict[str, object]]) -> dict[str, int]:
    counts = {sev: 0 for sev in _SEVERITY_ORDER}
    for finding in findings:
        if finding.get("not_tested"):
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
    return f"""
    <div class="finding-card" style="border-left-color:{color}">
      <div class="finding-head">
        <span class="severity-chip" style="background:{color}">{_esc(severity)}</span>
        <span class="finding-title">{_esc(finding.get("title", "Untitled finding"))}</span>
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
    </div>
    """


def _render_html(
    scan: dict[str, object],
    findings: list[dict[str, object]],
    stages: list[dict[str, object]],
) -> str:
    real_findings = [f for f in findings if not f.get("not_tested")]
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
    generated_at = datetime.now(UTC).strftime("%b %-d, %Y, %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Aevrin Security Report &mdash; {_esc(target)}</title>
<style>
  :root {{
    --bg: oklch(0.99 0 0);
    --card: oklch(1 0 0);
    --border: oklch(0.9 0 0);
    --text: oklch(0.2 0 0);
    --muted: oklch(0.5 0 0);
    --brand: oklch(0.55 0.14 145);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    line-height: 1.5;
  }}
  .page {{ max-width: 880px; margin: 0 auto; padding: 48px 24px 96px; }}
  .brand-row {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 32px; }}
  .brand {{ font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; font-size: 14px; color: var(--brand); }}
  .generated {{ font-size: 12px; color: var(--muted); }}
  h1 {{ font-size: 22px; margin: 0 0 4px; word-break: break-all; }}
  .target-type {{ font-size: 13px; color: var(--muted); margin: 0 0 24px; }}
  .status-chip {{
    display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.04em; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--border);
    margin-bottom: 12px;
  }}
  .hero {{
    display: grid; grid-template-columns: 160px 1fr; gap: 32px; align-items: center;
    background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 28px;
    margin-bottom: 20px;
  }}
  .score-gauge {{ width: 140px; height: 140px; }}
  .score-gauge-track {{ fill: none; stroke: var(--border); stroke-width: 10; }}
  .score-gauge-value {{ fill: none; stroke-width: 10; stroke-linecap: round; transform: rotate(-90deg); transform-origin: 70px 70px; }}
  .score-gauge-number {{ font-size: 28px; font-weight: 700; fill: var(--text); }}
  .score-gauge-suffix {{ font-size: 11px; fill: var(--muted); }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }}
  .meta-item .meta-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 2px; }}
  .meta-item .meta-value {{ font-size: 14px; font-weight: 600; }}
  .severity-row {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
  .severity-count {{
    flex: 1; min-width: 90px; background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 14px; text-align: center;
  }}
  .severity-count .count {{ font-size: 22px; font-weight: 700; }}
  .severity-count .label {{ font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.04em; }}
  .coverage-bar {{ display: flex; gap: 8px; margin-bottom: 20px; }}
  .coverage-segment {{ flex: 1; text-align: center; }}
  .coverage-chip {{ height: 8px; border-radius: 999px; margin-bottom: 6px; }}
  .coverage-label {{ font-size: 11px; font-weight: 600; }}
  .coverage-status {{ font-size: 10px; color: var(--muted); text-transform: uppercase; }}
  .callout {{ border-radius: 14px; padding: 16px 18px; margin-bottom: 20px; font-size: 13px; }}
  .callout-warning {{ background: oklch(0.96 0.05 41); border: 1px solid oklch(0.8 0.12 41); color: oklch(0.35 0.12 41); }}
  .callout-info {{ background: oklch(0.96 0.02 245); border: 1px solid oklch(0.82 0.08 245); color: oklch(0.35 0.08 245); }}
  .print-button {{
    display: inline-block; margin-left: 10px; font: inherit; font-weight: 600; font-size: 12px;
    color: white; background: var(--brand); border: none; border-radius: 999px; padding: 6px 14px;
    cursor: pointer;
  }}
  kbd {{ font: inherit; font-size: 11px; background: oklch(0.94 0 0); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; }}
  .section-title {{ font-size: 16px; margin: 32px 0 4px; }}
  .section-subtitle {{ font-size: 12px; color: var(--muted); margin: 0 0 16px; }}
  .finding-card {{
    background: var(--card); border: 1px solid var(--border); border-left: 4px solid;
    border-radius: 12px; padding: 16px 18px; margin-bottom: 12px;
  }}
  .finding-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }}
  .severity-chip {{
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    color: white; padding: 2px 8px; border-radius: 999px;
  }}
  .triage-chip {{
    font-size: 10px; font-weight: 600; text-transform: uppercase; color: var(--muted);
    border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px;
  }}
  .finding-title {{ font-weight: 600; font-size: 14px; }}
  .finding-meta {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; display: flex; gap: 6px; flex-wrap: wrap; }}
  .finding-desc {{ font-size: 13px; margin: 0 0 10px; }}
  .finding-remediation {{ background: oklch(0.97 0 0); border-radius: 10px; padding: 10px 12px; }}
  .finding-remediation-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }}
  .finding-remediation p {{ margin: 4px 0 0; font-size: 13px; }}
  .empty-state {{ font-size: 13px; color: var(--muted); background: var(--card); border: 1px dashed var(--border); border-radius: 14px; padding: 20px; }}
  .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); }}
  @media print {{ body {{ background: white; }} .page {{ padding: 0; max-width: none; }} .print-hide {{ display: none; }} }}
  @media (max-width: 640px) {{ .hero {{ grid-template-columns: 1fr; text-align: center; }} .meta-grid {{ grid-template-columns: 1fr 1fr; }} }}
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
    <p class="target-type">{_esc(target_type_label)}</p>

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
