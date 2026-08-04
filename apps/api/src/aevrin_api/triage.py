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

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from aevrin_scanner_core import Finding, Severity
from anthropic import AsyncAnthropic

from .config import Settings
from .crypto import decrypt_byok_key

logger = logging.getLogger("aevrin.triage")

_HAIKU_MODEL = "claude-haiku-4-5"
_GEMINI_MODEL = "gemini-flash-lite-latest"
_GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"
_TRIAGE_TIMEOUT_S = 20.0
_HIGH_SEVERITIES = (Severity.CRITICAL, Severity.HIGH)

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
    if tier == "hobby":
        return "flash_lite_only"
    if tier in ("pro", "team"):
        return "routed"
    return None


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

    return f"""You are a security triage assistant reviewing one finding from an automated MCP (Model Context Protocol) server security scan. The finding below already passed deterministic filtering — it is not test/fixture code and is not already excluded from scoring. Your job is to add judgment a static rule can't: is this actually a real, actionable risk here.

Finding: {finding.title}
Severity (as scored by the deterministic scanner): {finding.severity.value}
OWASP MCP category: {finding.owasp_category.value}
Location: {location}
Description: {finding.description}
Existing remediation guidance: {finding.remediation}

Deterministic signals already computed for this finding:
{signal_block}

Rules:
- Only lower severity from what the deterministic scanner assigned if you have a specific, stated reason (e.g. the code path is unreachable, the pattern is a documented false-positive shape for this exact rule, the credential is clearly a placeholder/example value). Never raise severity past what a KEV listing or explicit critical evidence in the description would justify on its own.
- "likely_false_positive" requires a specific, stated reason — vague uncertainty is "needs_review", not a dismissal.
- A finding with a verified live credential, or listed in CISA KEV, must never be classified "likely_false_positive".
- "remediation" is optional — include it only if you can give a fix direction more specific than the existing guidance above; otherwise omit it.
"""


async def _call_haiku(client: AsyncAnthropic, finding: Finding) -> dict[str, Any] | None:
    response = await client.messages.create(
        model=_HAIKU_MODEL,
        max_tokens=500,
        output_config={"format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA}},
        messages=[{"role": "user", "content": _prompt(finding)}],
    )
    if response.stop_reason == "refusal":
        return None
    for block in response.content:
        if block.type == "text":
            result: dict[str, Any] = json.loads(block.text)
            return result
    return None


async def _call_gemini(http: httpx.AsyncClient, api_key: str, finding: Finding) -> dict[str, Any] | None:
    body = {
        "contents": [{"parts": [{"text": _prompt(finding)}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
            "maxOutputTokens": 500,
        },
    }
    resp = await http.post(_GEMINI_URL, params={"key": api_key}, json=body, timeout=_TRIAGE_TIMEOUT_S)
    resp.raise_for_status()
    payload = resp.json()
    candidates = payload.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts") or []
    if not parts:
        return None
    result: dict[str, Any] = json.loads(parts[0]["text"])
    return result


async def triage_findings(settings: Settings, account: dict[str, Any], findings: list[Finding]) -> list[TriageResult]:
    routing = routing_for_tier(str(account.get("tier", "free")))
    if routing is None:
        return []

    anthropic_key = settings.anthropic_api_key
    gemini_key = settings.gemini_api_key
    if account.get("byok_enabled") and account.get("byok_key_encrypted"):
        byok_plaintext = decrypt_byok_key(settings, account["byok_key_encrypted"])
        if byok_plaintext:
            if account.get("byok_provider") == "anthropic":
                anthropic_key = byok_plaintext
            elif account.get("byok_provider") == "google":
                gemini_key = byok_plaintext

    candidates = [f for f in findings if not f.excluded_path and not f.not_tested]
    if not candidates:
        return []

    results: list[TriageResult] = []
    async with httpx.AsyncClient() as http:
        anthropic_client = AsyncAnthropic(api_key=anthropic_key, timeout=_TRIAGE_TIMEOUT_S) if anthropic_key else None
        try:
            for finding in candidates:
                use_haiku = routing == "routed" and finding.severity in _HIGH_SEVERITIES and anthropic_client is not None
                model_used = _HAIKU_MODEL if use_haiku else _GEMINI_MODEL
                try:
                    if use_haiku:
                        assert anthropic_client is not None
                        raw = await _call_haiku(anthropic_client, finding)
                    elif gemini_key:
                        raw = await _call_gemini(http, gemini_key, finding)
                    else:
                        continue  # no usable key for this call shape — fail open, silently
                except Exception:
                    logger.warning(
                        "triage: call failed for finding %s (model=%s), keeping deterministic result",
                        finding.id,
                        model_used,
                        exc_info=True,
                    )
                    continue

                if raw is None:
                    continue
                try:
                    results.append(
                        TriageResult(
                            finding_id=str(finding.id),
                            classification=raw["classification"],
                            severity=raw["severity"],
                            reasoning=raw["reasoning"],
                            remediation=raw.get("remediation"),
                            model=model_used,
                        )
                    )
                except (KeyError, TypeError):
                    logger.warning("triage: malformed response for finding %s, keeping deterministic result", finding.id)
                    continue
        finally:
            if anthropic_client is not None:
                await anthropic_client.close()

    return results
