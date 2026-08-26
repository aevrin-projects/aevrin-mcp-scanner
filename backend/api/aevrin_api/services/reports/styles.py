"""Print-oriented stylesheet for the exported HTML report.

Kept apart from the markup so the visual design can be adjusted without
reading through the rendering logic.

This is a document, not a screen. The previous version was the dashboard
rendered to a page: cards inside cards, twenty-pixel corner radii, and a
score with no stated conclusion beside it. Someone attaches this to a
procurement thread or a compliance ticket, so it is built as something that
survives being printed and read by a person who has never seen the product.

Everything is inlined and no font is fetched, so a saved copy keeps working
with no network. The typographic character comes from a serif stack the
operating system already has.
"""

REPORT_CSS = """  :root {
    --paper: #ffffff;
    --ink: oklch(0.18 0 0);
    --muted: oklch(0.48 0 0);
    --faint: oklch(0.62 0 0);
    --rule: oklch(0.88 0 0);
    --hairline: oklch(0.93 0 0);
    --wash: oklch(0.975 0 0);
    /* The product's accent. This file still said green, from a lime mark
       the rest of the product replaced, so an exported report did not
       match the dashboard it came from. */
    --brand: oklch(0.55 0.15 246.66);
  }
  * { box-sizing: border-box; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    margin: 0;
    background: var(--wash);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    font-size: 14px;
    line-height: 1.55;
  }
  .page {
    max-width: 820px;
    margin: 0 auto;
    background: var(--paper);
    padding: 56px 56px 72px;
  }
  .serif { font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif; }

  /* Masthead ------------------------------------------------------------ */
  .masthead { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; }
  .wordmark { font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; font-size: 12px; color: var(--brand); }
  .generated { font-size: 11px; color: var(--faint); text-align: right; }
  .doc-title { font-size: 13px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--muted); margin: 28px 0 0; }
  .target {
    font-size: 21px; font-weight: 600; margin: 6px 0 0; word-break: break-all; line-height: 1.3;
  }
  .target-meta { font-size: 12px; color: var(--muted); margin: 6px 0 0; }
  .rule { border: 0; border-top: 1px solid var(--rule); margin: 28px 0 0; }

  /* Verdict ------------------------------------------------------------- */
  .verdict { display: flex; align-items: flex-start; justify-content: space-between; gap: 40px; margin-top: 28px; }
  .verdict-text { flex: 1; min-width: 0; }
  .verdict-line { font-size: 26px; line-height: 1.25; margin: 0; }
  .verdict-note { font-size: 13px; color: var(--muted); margin: 8px 0 0; max-width: 46em; }
  .score { text-align: right; flex-shrink: 0; }
  .score-number { font-size: 52px; font-weight: 600; line-height: 1; letter-spacing: -0.02em; }
  .score-of { font-size: 15px; color: var(--faint); }
  .score-label { font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--faint); margin-top: 6px; }

  /* Severity distribution ----------------------------------------------- */
  .dist { margin-top: 26px; }
  .dist-bar { display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: var(--hairline); }
  .dist-legend { display: flex; flex-wrap: wrap; gap: 18px; margin-top: 10px; font-size: 12px; }
  .dist-item { display: flex; align-items: baseline; gap: 6px; }
  .dist-swatch { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
  .dist-count { font-variant-numeric: tabular-nums; color: var(--muted); }
  .dist-none { font-size: 13px; color: var(--muted); margin-top: 10px; }

  /* Facts --------------------------------------------------------------- */
  .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 26px; padding-top: 20px; border-top: 1px solid var(--hairline); }
  .fact-label { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); }
  .fact-value { font-size: 13px; font-weight: 500; margin-top: 3px; }

  /* Notices -------------------------------------------------------------- */
  .notice { margin-top: 26px; padding: 0 0 0 16px; border-left: 3px solid var(--rule); }
  .notice-warning { border-left-color: oklch(0.65 0.2 41); }
  .notice-title { font-size: 13px; font-weight: 600; margin: 0; }
  .notice-warning .notice-title { color: oklch(0.5 0.18 41); }
  .notice p { font-size: 13px; color: var(--muted); margin: 5px 0 0; max-width: 46em; }

  /* Sections ------------------------------------------------------------- */
  .section { margin-top: 42px; }
  .section-title { font-size: 17px; margin: 0; }
  .section-sub { font-size: 12px; color: var(--muted); margin: 4px 0 0; max-width: 46em; }
  .section-head { padding-bottom: 12px; border-bottom: 1px solid var(--rule); }

  /* Coverage ------------------------------------------------------------- */
  .stages { margin-top: 4px; }
  .stage { display: flex; align-items: baseline; gap: 12px; padding: 9px 0; border-bottom: 1px solid var(--hairline); }
  .stage-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .stage-name { font-size: 13px; flex: 1; }
  .stage-status { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); }
  .stage-error { font-size: 12px; color: var(--muted); margin: 2px 0 0 19px; }

  /* Findings ------------------------------------------------------------- */
  .finding { padding: 20px 0; border-bottom: 1px solid var(--hairline); break-inside: avoid; page-break-inside: avoid; }
  .finding-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .finding-index { font-size: 12px; color: var(--faint); font-variant-numeric: tabular-nums; min-width: 22px; }
  .sev {
    font-size: 10px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 2px 7px; border-radius: 3px; color: #fff;
  }
  .finding-title { font-size: 15px; font-weight: 600; }
  .tag {
    font-size: 10px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
    border: 1px solid var(--rule); border-radius: 3px; padding: 1px 6px; color: var(--muted);
  }
  .tag-kev { border-color: oklch(0.75 0.14 27); color: oklch(0.48 0.2 27); }
  .finding-meta { font-size: 12px; color: var(--muted); margin: 6px 0 0 32px; }
  .finding-meta code { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace; font-size: 11px; }
  .finding-body { margin-left: 32px; }
  .finding-desc { font-size: 13px; margin: 9px 0 0; max-width: 46em; }
  .fix { margin: 12px 0 0; padding: 12px 14px; background: var(--wash); border-radius: 4px; max-width: 46em; }
  .fix-label { font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--faint); }
  .fix p { font-size: 13px; margin: 4px 0 0; }
  .audit { margin-top: 10px; font-size: 12px; color: var(--muted); }
  .empty { font-size: 13px; color: var(--muted); margin-top: 16px; max-width: 46em; }

  /* Footer --------------------------------------------------------------- */
  .footer { margin-top: 48px; padding-top: 18px; border-top: 1px solid var(--rule); font-size: 11px; color: var(--faint); line-height: 1.6; }
  .footer strong { color: var(--muted); font-weight: 600; }

  /* The one piece of screen furniture, and it removes itself from paper. */
  .print-bar {
    margin-top: 26px; padding: 12px 16px; background: var(--wash);
    border: 1px solid var(--hairline); border-radius: 4px; font-size: 12px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
  }
  .print-button {
    font: inherit; font-weight: 600; font-size: 12px; color: #fff; background: var(--brand);
    border: 0; border-radius: 4px; padding: 7px 14px; cursor: pointer; white-space: nowrap;
  }
  kbd { font: inherit; font-size: 11px; background: var(--paper); border: 1px solid var(--rule); border-radius: 3px; padding: 1px 5px; }

  @page { margin: 16mm 14mm 18mm; }
  @media print {
    body { background: var(--paper); font-size: 11pt; }
    .page { padding: 0; max-width: none; }
    .print-hide { display: none !important; }
    .section { margin-top: 30px; }
    /* A heading stranded at the foot of a page with its content overleaf is
       the classic way an exported report looks careless. */
    .section-head, .verdict { break-after: avoid; page-break-after: avoid; }
  }
  @media (max-width: 680px) {
    .page { padding: 32px 20px 48px; }
    .verdict { flex-direction: column; gap: 20px; }
    .score { text-align: left; }
    .facts { grid-template-columns: 1fr 1fr; }
  }"""
