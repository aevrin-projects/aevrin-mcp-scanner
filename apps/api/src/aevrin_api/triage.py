"""LLM triage layer — paid tiers only, addendum §2.

Detection stays 100% deterministic (packages/scanner-core); this is a
second pass that reads each *surviving* finding (already filtered/scored by
scanner-core's Section-1 fixes — excluded_path/not_tested findings are
skipped here, there's no point spending a model call on something that
already doesn't count toward the score) alongside its own description and
classifies it: confirmed / likely_false_positive / needs_review, with an
adjusted severity, a one-sentence reason, and an optional remediation
rewrite.

Fail-open, no exceptions: any error, timeout, or malformed response for a
given finding is caught and that finding is simply skipped — the caller
keeps the original deterministic result untouched. A triage failure must
never be the reason a real vulnerability goes missing from a report.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from aevrin_scanner_core import Finding

from .config import Settings
from .deepseek import FLASH_MODEL, PRO_MODEL, DeepSeekError, complete_json, parse_json_object

logger = logging.getLogger("aevrin.triage")

_TRIAGE_TIMEOUT_S = 30.0
# Reasoning tokens are billed as completion tokens and dominate the budget:
# measured 1199 completion tokens for a triage that emits ~120 tokens of
# visible JSON. At 700 the JSON truncated mid-string.
_TRIAGE_MAX_TOKENS = 2000

# Findings are independent, so they go out in parallel. Bounded because an
# unbounded gather on a 167-finding monorepo scan would open 167 sockets and
# invite a rate limit; 8 turns a ~5 minute serial run into well under one.
_TRIAGE_CONCURRENCY = 8

# Caps exist because cost tracks findings-per-scan, not user count.
_TRIAGE_CAP_FREE = 40
_TRIAGE_CAP_PAID = 200
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "classification": {"type": "string", "enum": ["confirmed", "likely_false_positive", "needs_review"]},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low", "info"]},
        "reasoning": {"type": "string"},
        "remediation": {"type": "string"},
    },
    "required": ["classification", "severity", "reasoning"],
    "additionalProperties": False,
}


@dataclass
class TriageResult:
    finding_id: str
    classification: str  # confirmed | likely_false_positive | needs_review
    severity: str
    reasoning: str
    remediation: str | None
    model: str


def routing_for_tier(tier: str) -> str | None:
    """Which model mix a tier gets triaged with; None means no triage at
    all (Free) — addendum §2 model-routing table."""
    if tier in ("hobby", "pro", "team"):
        return "pro"
    # Free accounts now get triage too, on the cheap model. Previously they
    # got none at all, which meant the deterministic scanner output was the
    # entire free experience.
    return "flash"


_SYSTEM_PROMPT = """You are a security triage assistant reviewing findings from static scanners on Model Context Protocol (MCP) server code.

For each finding, decide whether the scanner is right.

Reply with a single json object containing:
- "classification": one of "confirmed", "likely_false_positive", "needs_review".
- "severity": one of "critical", "high", "medium", "low", "info". Adjust the scanner's severity only when the context genuinely warrants it.
- "reasoning": one sentence explaining the classification. Be concrete about the evidence, not generic.
- "remediation": optional. Include it only if you can give a fix direction more specific than the guidance already provided; otherwise omit the key entirely.

Rules:
- A test fixture, example, or clearly non-routable placeholder credential is usually "likely_false_positive".
- A real credential, an injectable command path, or a reachable traversal is "confirmed".
- When the surrounding context is not visible enough to be sure, say "needs_review" rather than guessing.
- Never invent file contents you were not shown.
- Only lower the scanner's severity for a specific, stated reason: the code path is unreachable, the pattern is a documented false-positive shape for that exact rule, or the credential is clearly a placeholder. Never raise severity beyond what a KEV listing or explicit critical evidence in the description justifies on its own.
- A finding with a verified live credential, or one listed in CISA KEV, must never be "likely_false_positive".
- Vague uncertainty is "needs_review", never a dismissal.

Findings reaching you have already passed deterministic filtering: they are not test or fixture code and are not excluded from scoring. Your job is the judgment a static rule cannot make."""


def _prompt(finding: Finding) -> str:
    signals: list[str] = []
    if finding.epss_score is not None:
        signals.append(f"EPSS exploitation probability (next 30 days): {finding.epss_score:.3f}")
    if finding.in_kev:
        signals.append("Listed in CISA's Known Exploited Vulnerabilities catalog — confirmed real-world exploitation.")
    if finding.dependency_scope is not None:
        signals.append(f"Dependency scope: {finding.dependency_scope.value}")
    if finding.corroborated_by:
        signals.append(f"Independently corroborated by: {', '.join(t.value for t in finding.corroborated_by)}")
    if finding.confidence:
        signals.append(f"Scanner-reported confidence: {finding.confidence}")
    if finding.verified is not None:
        signals.append(f"Verified live credential: {finding.verified}")
    signal_block = "\n".join(f"- {s}" for s in signals) or "- none"

    location = finding.location.file_path or finding.location.manifest_field or "unknown location"

    return f"""Triage this json finding.

Finding: {finding.title}
Severity (as scored by the deterministic scanner): {finding.severity.value}
OWASP MCP category: {finding.owasp_category.value}
Location: {location}
Description: {finding.description}
Existing remediation guidance: {finding.remediation}

Deterministic signals already computed for this finding:
{signal_block}
"""


async def triage_findings(
    settings: Settings, account: dict[str, Any], findings: list[Finding]
) -> tuple[list[TriageResult], str | None]:
    """Returns (results, note). `note` is a user-facing sentence when triage
    was capped, so a partially-triaged scan says so instead of quietly
    looking fully reviewed."""
    routing = routing_for_tier(str(account.get("tier", "free")))
    api_key = settings.deepseek_api_key
    if not api_key:
        logger.info("triage: no DeepSeek key configured, skipping")
        return [], None

    candidates = [f for f in findings if not f.excluded_path and not f.not_tested]
    if not candidates:
        return [], None

    model = PRO_MODEL if routing == "pro" else FLASH_MODEL
    cap = _TRIAGE_CAP_PAID if routing == "pro" else _TRIAGE_CAP_FREE

    note: str | None = None
    if len(candidates) > cap:
        # Cost scales with findings per scan, not accounts: one monorepo
        # scan in this database produced 167 triageable findings, so an
        # uncapped free tier is one large repository away from a surprising
        # bill. Highest severity first, so the cap spends the budget on what
        # matters rather than on whatever the scanner happened to emit first.
        candidates = sorted(candidates, key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 9))[:cap]
        note = (
            f"AI review covered the {cap} highest-severity findings of {len(findings)}. "
            "Every finding is still fully reported by the scanners; only the AI second opinion is capped"
            + (" on the Free plan." if routing != "pro" else ".")
        )

    sem = asyncio.Semaphore(_TRIAGE_CONCURRENCY)
    stats = {"hit": 0, "total": 0, "truncated": 0}

    async def triage_one(finding: Finding) -> TriageResult | None:
        async with sem:
            try:
                result = await complete_json(
                    api_key=api_key,
                    model=model,
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=_prompt(finding),
                    max_tokens=_TRIAGE_MAX_TOKENS,
                    timeout_s=_TRIAGE_TIMEOUT_S,
                )
            except (DeepSeekError, httpx.HTTPError):
                # Fail open, per finding. A triage outage must never be the
                # reason a real vulnerability goes missing from a report: the
                # deterministic scanner result stands on its own.
                logger.warning("triage: call failed for finding %s", finding.id, exc_info=True)
                return None

        stats["total"] += result.prompt_tokens
        stats["hit"] += result.cache_hit_tokens
        if result.truncated:
            stats["truncated"] += 1

        try:
            raw = parse_json_object(result.content)
            return TriageResult(
                finding_id=str(finding.id),
                classification=raw["classification"],
                severity=raw["severity"],
                reasoning=raw["reasoning"],
                remediation=raw.get("remediation"),
                model=model,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.warning(
                "triage: unusable response for finding %s (truncated=%s)", finding.id, result.truncated
            )
            return None

    # The first call alone, so it populates the prompt cache that the rest
    # then hit. Firing all of them at once would have every request in the
    # opening batch miss.
    first = await triage_one(candidates[0])
    rest = await asyncio.gather(*(triage_one(f) for f in candidates[1:]))
    results = [r for r in (first, *rest) if r is not None]

    if stats["total"]:
        logger.info(
            "triage: %s/%s findings on %s, cache hit rate %.0f%%, %s truncated",
            len(results), len(candidates), model,
            100 * stats["hit"] / stats["total"], stats["truncated"],
        )
    return results, note
