"""Severity-bucketing helpers shared by adapters whose source tool doesn't
already hand back a critical/high/medium/low label directly.
"""

from __future__ import annotations

import re

from .models import Severity


def cvss_vector_to_severity(vector: str | None, fallback: Severity = Severity.MEDIUM) -> Severity:
    """OSV-Scanner hands back a raw CVSS vector string, not a bucketed label.
    We don't pull in a full CVSS library for one field — this reads the
    Confidentiality/Integrity/Availability impact + attack vector + scope
    components directly off the vector string, which is enough to bucket
    severity without computing an exact numeric score.
    """
    if not vector:
        return fallback
    components = dict(part.split(":", 1) for part in vector.split("/") if ":" in part)
    impacts = [components.get(k) for k in ("C", "I", "A")]
    high_impacts = sum(1 for i in impacts if i == "H")
    network_vector = components.get("AV") == "N"
    changed_scope = components.get("S") == "C"

    if high_impacts >= 2 and network_vector:
        return Severity.CRITICAL
    if high_impacts >= 1 and (network_vector or changed_scope):
        return Severity.HIGH
    if high_impacts >= 1 or any(i == "L" for i in impacts):
        return Severity.MEDIUM
    return Severity.LOW


def ghsa_severity(label: str | None, fallback: Severity = Severity.MEDIUM) -> Severity:
    if not label:
        return fallback
    mapping = {
        "CRITICAL": Severity.CRITICAL,
        "HIGH": Severity.HIGH,
        "MODERATE": Severity.MEDIUM,
        "MEDIUM": Severity.MEDIUM,
        "LOW": Severity.LOW,
    }
    return mapping.get(label.upper(), fallback)


def scorecard_score_to_severity(score: float) -> Severity | None:
    """Scorecard scores each check 0-10, higher is better. We only emit a
    finding when a check scores below the 'healthy' threshold, and bucket
    severity by how far below it falls."""
    if score >= 8:
        return None
    if score < 3:
        return Severity.HIGH
    if score < 6:
        return Severity.MEDIUM
    return Severity.LOW


_SECRET_LIKE_ENV = re.compile(r"(key|token|secret|password|credential)", re.IGNORECASE)


def looks_like_secret_field(name: str) -> bool:
    return bool(_SECRET_LIKE_ENV.search(name))
