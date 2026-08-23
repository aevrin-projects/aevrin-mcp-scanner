"""CISA Known Exploited Vulnerabilities cross-reference: accuracy fix #5.

A KEV match means CISA has confirmed real-world, in-the-wild exploitation,
categorically stronger evidence than EPSS's predictive score. It overrides
any EPSS-driven downweighting and elevates the finding to CRITICAL, surfaced
distinctly via in_kev rather than folded into epss_score, so a report can
always tell "predicted likely to be exploited" apart from "already is being
exploited by someone, confirmed by CISA".

Same fail-open shape as epss.py: the catalog is a large JSON file, fetched
and cached once per scan run (see fetch_kev_catalog, called once from
postprocess.py) rather than once per finding. A failed fetch just means
every finding's in_kev stays False; it never blocks or fails the scan.
"""

from __future__ import annotations

import logging

import httpx

from ..models import Finding, Severity
from .epss import finding_cve_id

logger = logging.getLogger("aevrin.scanner_core.kev")

_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def fetch_kev_catalog() -> frozenset[str]:
    """Returns the set of CVE IDs CISA has confirmed active exploitation
    for. Never raises; a fetch failure just returns an empty set, so
    nothing gets (incorrectly) flagged rather than the scan failing."""
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(_KEV_URL)
            response.raise_for_status()
            payload = response.json()
        return frozenset(
            str(v["cveID"]).upper() for v in payload.get("vulnerabilities", []) if v.get("cveID")
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("CISA KEV fetch failed, proceeding without it: %s", exc)
        return frozenset()


def apply_kev(findings: list[Finding], kev_ids: frozenset[str]) -> None:
    """Mutates matching findings in place: sets in_kev and elevates severity
    to CRITICAL, overriding any scanner-assigned or EPSS-downweighted value;
    confirmed active exploitation always wins."""
    if not kev_ids:
        return
    for finding in findings:
        cve = finding_cve_id(finding)
        if cve and cve in kev_ids:
            finding.in_kev = True
            if finding.original_severity is None:
                finding.original_severity = finding.severity
            finding.severity = Severity.CRITICAL
