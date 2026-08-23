"""Print-oriented stylesheet for the exported HTML report.

Kept apart from the markup so the visual design can be adjusted without
reading through the rendering logic.
"""

REPORT_CSS = """  :root {
    --bg: oklch(0.99 0 0);
    --card: oklch(1 0 0);
    --border: oklch(0.9 0 0);
    --text: oklch(0.2 0 0);
    --muted: oklch(0.5 0 0);
    --brand: oklch(0.55 0.14 145);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    line-height: 1.5;
  }
  .page { max-width: 880px; margin: 0 auto; padding: 48px 24px 96px; }
  .brand-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 32px; }
  .brand { font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; font-size: 14px; color: var(--brand); }
  .generated { font-size: 12px; color: var(--muted); }
  h1 { font-size: 22px; margin: 0 0 4px; word-break: break-all; }
  .target-type { font-size: 13px; color: var(--muted); margin: 0 0 24px; }
  .status-chip {
    display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.04em; padding: 3px 10px; border-radius: 999px; border: 1px solid var(--border);
    margin-bottom: 12px;
  }
  .hero {
    display: grid; grid-template-columns: 160px 1fr; gap: 32px; align-items: center;
    background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 28px;
    margin-bottom: 20px;
  }
  .score-gauge { width: 140px; height: 140px; }
  .score-gauge-track { fill: none; stroke: var(--border); stroke-width: 10; }
  .score-gauge-value { fill: none; stroke-width: 10; stroke-linecap: round; transform: rotate(-90deg); transform-origin: 70px 70px; }
  .score-gauge-number { font-size: 28px; font-weight: 700; fill: var(--text); }
  .score-gauge-suffix { font-size: 11px; fill: var(--muted); }
  .meta-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
  .meta-item .meta-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 2px; }
  .meta-item .meta-value { font-size: 14px; font-weight: 600; }
  .severity-row { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
  .severity-count {
    flex: 1; min-width: 90px; background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 14px; text-align: center;
  }
  .severity-count .count { font-size: 22px; font-weight: 700; }
  .severity-count .label { font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.04em; }
  .coverage-bar { display: flex; gap: 8px; margin-bottom: 20px; }
  .coverage-segment { flex: 1; text-align: center; }
  .coverage-chip { height: 8px; border-radius: 999px; margin-bottom: 6px; }
  .coverage-label { font-size: 11px; font-weight: 600; }
  .coverage-status { font-size: 10px; color: var(--muted); text-transform: uppercase; }
  .callout { border-radius: 14px; padding: 16px 18px; margin-bottom: 20px; font-size: 13px; }
  .callout-warning { background: oklch(0.96 0.05 41); border: 1px solid oklch(0.8 0.12 41); color: oklch(0.35 0.12 41); }
  .callout-info { background: oklch(0.96 0.02 245); border: 1px solid oklch(0.82 0.08 245); color: oklch(0.35 0.08 245); }
  .print-button {
    display: inline-block; margin-left: 10px; font: inherit; font-weight: 600; font-size: 12px;
    color: white; background: var(--brand); border: none; border-radius: 999px; padding: 6px 14px;
    cursor: pointer;
  }
  kbd { font: inherit; font-size: 11px; background: oklch(0.94 0 0); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; }
  .section-title { font-size: 16px; margin: 32px 0 4px; }
  .section-subtitle { font-size: 12px; color: var(--muted); margin: 0 0 16px; }
  .finding-card {
    background: var(--card); border: 1px solid var(--border); border-left: 4px solid;
    border-radius: 12px; padding: 16px 18px; margin-bottom: 12px;
  }
  .finding-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
  .severity-chip {
    font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
    color: white; padding: 2px 8px; border-radius: 999px;
  }
  .triage-chip {
    font-size: 10px; font-weight: 600; text-transform: uppercase; color: var(--muted);
    border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px;
  }
  .kev-chip {
    font-size: 10px; font-weight: 700; text-transform: uppercase; color: oklch(0.5 0.2 27);
    background: oklch(0.94 0.06 27); border: 1px solid oklch(0.75 0.14 27); border-radius: 999px; padding: 2px 8px;
  }
  .epss-chip {
    font-size: 10px; font-weight: 600; color: var(--muted);
    border: 1px solid var(--border); border-radius: 999px; padding: 2px 8px;
  }
  .finding-title { font-weight: 600; font-size: 14px; }
  .finding-meta { font-size: 12px; color: var(--muted); margin-bottom: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
  .finding-desc { font-size: 13px; margin: 0 0 10px; }
  .finding-remediation { background: oklch(0.97 0 0); border-radius: 10px; padding: 10px 12px; }
  .finding-remediation-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .finding-remediation p { margin: 4px 0 0; font-size: 13px; }
  .empty-state { font-size: 13px; color: var(--muted); background: var(--card); border: 1px dashed var(--border); border-radius: 14px; padding: 20px; }
  .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); }
  @media print { body { background: white; } .page { padding: 0; max-width: none; } .print-hide { display: none; } }
  @media (max-width: 640px) { .hero { grid-template-columns: 1fr; text-align: center; } .meta-grid { grid-template-columns: 1fr 1fr; } }"""
