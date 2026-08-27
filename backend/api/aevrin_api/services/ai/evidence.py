"""Building the evidence document an AI explanation is allowed to see.

The whole AI layer rests on one constraint: the model explains evidence, it
does not look for vulnerabilities. Aevrin's scanners decide what is true. The
model's only job is to say what a true thing means for the person reading it.

Two consequences shape this file.

**It must be complete enough to explain from.** A model asked "why is this
grade C" with nothing but the letter will invent a reason, because that is
what a language model does with an under-specified question. So the document
carries the actual factors, the actual findings, the actual capabilities.

**It must be minimal enough to be safe.** Least privilege applies to the
reviewer too. It gets a finding's title, severity, category and location --
never the matched secret, never the file's contents, never the environment.
`_redact` is not decoration: TruffleHog and Gitleaks findings routinely carry
the credential they found in their raw payload, and shipping that to a third
party would turn a security feature into a breach.

The hash at the bottom is what makes caching honest. It is computed over the
canonical form of exactly what the model was shown, so two requests share an
explanation only when the evidence behind them is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# Findings are capped so one noisy scan cannot push the important part of the
# document out of a context window. Ordered by severity first, so what
# survives truncation is what matters.
_MAX_FINDINGS = 40
_MAX_TOOLS = 60
_MAX_FIELD_CHARS = 600

# Anything shaped like a credential is removed before the document is built,
# regardless of which field it appeared in. This runs in addition to dropping
# raw payloads, not instead of it: defence in depth, because the cost of being
# wrong once is a leaked secret.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*\S{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_REDACTED = "[redacted]"


def _redact(value: str | None) -> str:
    """Strip anything credential-shaped, then bound the length.

    Applied to every free-text field that leaves this process, including ones
    that "should not" contain a secret. Fields that should not contain secrets
    are exactly where secrets keep turning up.
    """
    if not value:
        return ""
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text.strip()[:_MAX_FIELD_CHARS]


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def finding_evidence(finding: dict[str, Any]) -> dict[str, Any]:
    """One finding, reduced to what explaining it requires.

    `raw` is never included. It is the scanner's own payload and for the
    secret scanners it contains the secret itself.
    """
    location = finding.get("location") or {}
    if not isinstance(location, dict):
        location = {}
    return {
        "id": str(finding.get("id") or ""),
        "tool": finding.get("tool"),
        "severity": finding.get("severity"),
        "owasp_category": finding.get("owasp_category"),
        "title": _redact(finding.get("title")),
        "description": _redact(finding.get("description")),
        "remediation": _redact(finding.get("remediation")),
        # The path is useful context and is not itself sensitive; line numbers
        # are kept so the explanation can point somewhere real.
        "file_path": _redact(location.get("file_path")),
        "line": location.get("line_start"),
        "manifest_field": _redact(location.get("manifest_field")),
        # Whether a secret scanner proved the credential live. Materially
        # changes the severity of the advice, so it must survive.
        "verified": finding.get("verified"),
    }


def build_evidence(
    *,
    subject_type: str,
    subject_id: str | None = None,
    findings: list[dict[str, Any]] | None = None,
    trust_grade: dict[str, Any] | None = None,
    permissions: list[dict[str, Any]] | None = None,
    mcp_tools: list[dict[str, Any]] | None = None,
    skills: list[dict[str, Any]] | None = None,
    credentials_metadata: list[dict[str, Any]] | None = None,
    attack_paths: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the document, in the structure the prompt expects.

    Every section is optional, and an absent section is omitted rather than
    sent as an empty list. "There are no attack paths" and "attack paths were
    not part of this question" read identically as `[]`, and the first is a
    security claim this function has no standing to make.
    """
    document: dict[str, Any] = {"subject_type": subject_type}
    if subject_id:
        document["subject_id"] = str(subject_id)

    if findings:
        ordered = sorted(
            findings,
            key=lambda f: (_SEVERITY_ORDER.get(str(f.get("severity", "")).lower(), 9), str(f.get("title", ""))),
        )
        document["findings"] = [finding_evidence(f) for f in ordered[:_MAX_FINDINGS]]
        if len(findings) > _MAX_FINDINGS:
            # Said out loud in the document, so the model is not left to infer
            # a total from a truncated list and state it as fact.
            document["findings_truncated"] = {
                "shown": _MAX_FINDINGS,
                "total": len(findings),
            }

    if trust_grade:
        document["trust_grade"] = {
            "grade": trust_grade.get("grade"),
            "label": trust_grade.get("label"),
            "scan_score": trust_grade.get("scan_score"),
            "recommended_action": trust_grade.get("recommended_action"),
            "factors": [
                {"points": f.get("points"), "reason": _redact(f.get("reason"))}
                for f in (trust_grade.get("factors") or [])[:20]
            ],
        }

    if permissions:
        # Type and scope only. Never the credential, never the resolved path,
        # never the value behind an environment variable.
        document["permissions"] = [
            {
                "type": _redact(p.get("type") or p.get("kind")),
                "scope": _redact(p.get("scope")),
                "resource_category": _redact(p.get("resource_category") or p.get("resource")),
                "credential_present": bool(p.get("credential_present")),
            }
            for p in permissions[:40]
        ]

    if mcp_tools:
        document["mcp_tools"] = [
            {
                "name": _redact(t.get("name")),
                "description": _redact(t.get("description")),
                "capabilities": list(t.get("capabilities") or [])[:10],
            }
            for t in mcp_tools[:_MAX_TOOLS]
        ]

    if skills:
        document["skills"] = [
            {"name": _redact(s.get("name")), "description": _redact(s.get("description"))}
            for s in skills[:30]
        ]

    if credentials_metadata:
        # Metadata only, by construction: what kind of credential, where it
        # was configured, whether it is present. Never a value. This mirrors
        # the absolute rule the rest of the product follows.
        document["credentials_metadata"] = [
            {
                "kind": _redact(c.get("kind") or c.get("type")),
                "source": _redact(c.get("source")),
                "present": bool(c.get("present", True)),
            }
            for c in credentials_metadata[:30]
        ]

    if attack_paths:
        document["attack_paths"] = [
            {
                "title": _redact(a.get("title")),
                "severity": a.get("severity"),
                "steps": [_redact(s) for s in (a.get("steps") or [])[:10]],
            }
            for a in attack_paths[:15]
        ]

    if coverage:
        # The single most important section. Without it a model reading zero
        # findings in a category will explain that the category is clean,
        # which is the precise failure this product exists to prevent.
        document["coverage"] = {
            "complete": coverage.get("complete"),
            "unreliable_stages": list(coverage.get("unreliable_stages") or [])[:10],
            "note": (
                "Stages listed as unreliable did not run. Absence of findings in those "
                "categories is not evidence of safety and must not be described as clean."
            ),
        }

    if context:
        document["context"] = {
            str(k)[:60]: _redact(str(v)) for k, v in list(context.items())[:20]
        }

    return document


def evidence_hash(document: dict[str, Any]) -> str:
    """A stable fingerprint of exactly what the model will be shown.

    Canonical JSON -- sorted keys, no incidental whitespace -- so that two
    documents describing the same evidence hash identically regardless of how
    they were assembled. Cheap, deterministic, and the whole reason the same
    explanation is not paid for twice.
    """
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def render_for_prompt(document: dict[str, Any]) -> str:
    """The document as the model receives it.

    Pretty-printed JSON rather than prose: it is unambiguous, it is obviously
    data rather than instruction, and a nested structure survives it intact.
    """
    return json.dumps(document, indent=2, sort_keys=True, default=str)
