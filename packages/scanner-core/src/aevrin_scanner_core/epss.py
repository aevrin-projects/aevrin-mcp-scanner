"""EPSS (Exploit Prediction Scoring System) integration — accuracy fix #4.

Fetches FIRST.org's public EPSS score for every CVE-bearing finding, batched
into as few HTTP calls as the CVE count needs (comma-separated `cve=` query
param, no API key required). Fail-open throughout: a network failure,
timeout, or a CVE FIRST.org simply has no data for must never fail the
scan — it just leaves epss_score unset and logs a warning, mirroring
pipeline.py's _run_isolated: a broken external dependency degrades this one
signal, it never takes down the scan.

EPSS is a probability of exploitation in the wild in the next 30 days, not a
severity — it's used here only to soften (never sharpen) the scanner's own
severity call, and only once the prediction is confidently low. FIRST.org
publishes ~0.02 (2%) as roughly the median EPSS score across all scored
CVEs; scoring below that puts a CVE in the bottom half of *all* known CVEs
for predicted exploitation, which is a reasonable bar for "not urgent enough
to keep the scanner's original severity" without being so low that it'd be
defensible to drop the finding further than one tier.
"""

from __future__ import annotations

import logging
import re

import httpx

from .models import Finding, ToolName
from .severity_utils import downweight_one_tier

logger = logging.getLogger("aevrin.scanner_core.epss")

_EPSS_URL = "https://api.first.org/data/v1/epss"
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
_BATCH_SIZE = 100
_LOW_EPSS_THRESHOLD = 0.02

# Tools whose findings can plausibly carry a CVE ID.
_CVE_BEARING_TOOLS = frozenset({ToolName.TRIVY, ToolName.OSV_SCANNER})


def finding_cve_id(finding: Finding) -> str | None:
    """Best-available CVE id for a finding — the tool's own id if it's
    already CVE-shaped, else the first CVE-shaped alias OSV-Scanner
    reported (osv.dev vulnerability objects carry an `aliases` list; a
    GHSA-primary entry often aliases the CVE for the same issue)."""
    if finding.tool not in _CVE_BEARING_TOOLS or not finding.raw:
        return None
    candidates: list[str] = []
    if finding.tool == ToolName.TRIVY:
        candidates.append(str(finding.raw.get("VulnerabilityID") or ""))
    else:
        candidates.append(str(finding.raw.get("id") or ""))
        candidates.extend(str(a) for a in finding.raw.get("aliases") or [])
    return next((c.upper() for c in candidates if _CVE_RE.fullmatch(c)), None)


def fetch_epss_scores(cve_ids: list[str]) -> dict[str, float]:
    """Batched GET against FIRST.org, _BATCH_SIZE CVEs per request. Returns
    whatever it managed to fetch — never raises, so a failed batch just
    means those CVEs' epss_score stays unset."""
    scores: dict[str, float] = {}
    unique_ids = sorted(set(cve_ids))
    with httpx.Client(timeout=10) as client:
        for i in range(0, len(unique_ids), _BATCH_SIZE):
            batch = unique_ids[i : i + _BATCH_SIZE]
            try:
                response = client.get(_EPSS_URL, params={"cve": ",".join(batch)})
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("EPSS fetch failed for %d CVE(s): %s", len(batch), exc)
                continue
            for row in payload.get("data", []):
                try:
                    scores[str(row["cve"]).upper()] = float(row["epss"])
                except (KeyError, TypeError, ValueError):
                    continue
    return scores


def apply_epss(findings: list[Finding]) -> None:
    """Mutates CVE-bearing findings in place: sets epss_score, and softens
    severity one tier when the prediction is confidently low. Must run
    before apply_kev — a CISA KEV match overrides this unconditionally, so
    running KEV afterward is what makes "confirmed exploited" always win
    over "predicted unlikely to be exploited"."""
    cve_by_index: dict[int, str] = {}
    for idx, finding in enumerate(findings):
        cve = finding_cve_id(finding)
        if cve:
            cve_by_index[idx] = cve
    if not cve_by_index:
        return
    scores = fetch_epss_scores(list(cve_by_index.values()))
    for idx, cve in cve_by_index.items():
        score = scores.get(cve)
        if score is None:
            continue
        finding = findings[idx]
        finding.epss_score = score
        if score < _LOW_EPSS_THRESHOLD:
            if finding.original_severity is None:
                finding.original_severity = finding.severity
            finding.severity = downweight_one_tier(finding.severity)
