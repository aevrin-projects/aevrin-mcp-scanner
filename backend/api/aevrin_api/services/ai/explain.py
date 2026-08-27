"""Producing, caching, and attributing an AI explanation.

The contract with the rest of the product is narrow and one-directional:

* An explanation reads evidence. It never produces evidence, never edits a
  finding, never moves a score, and never changes a grade. Nothing in this
  module writes to `scans`, `findings`, or `mcp_listing_versions`.

* If it fails, the security result is unaffected. Every caller treats a
  failure here as "explanation unavailable", displayed next to a finding that
  is still entirely valid. The AI layer is not permitted to become a
  dependency of the scanner.

* The reader is always told which provider and model answered. Falling back
  from one vendor to another has billing and privacy consequences, so it is
  never silent.
"""

from __future__ import annotations

import logging
from typing import Any

from aevrin_api.config import Settings
from aevrin_api.db import SupabaseRest
from aevrin_api.integrations.ai_providers import (
    Completion,
    ProviderError,
    ProviderNotConfigured,
    complete,
)
from aevrin_api.services.ai.credentials import ProviderCredential, load_credentials
from aevrin_api.services.ai.evidence import evidence_hash, render_for_prompt

logger = logging.getLogger("aevrin.ai.explain")


class ExplanationUnavailable(Exception):
    """No explanation could be produced. Always safe to show to a user, and
    always safe to ignore: the finding it would have described stands."""


# The instruction half of the prompt. Provider-neutral, because every adapter
# delivers it through whatever that vendor calls a system message.
#
# The prohibitions are specific rather than a general plea for accuracy. "Do
# not speculate" is advice; "if the evidence does not say, write that it does
# not say" is an instruction with an observable outcome.
SYSTEM_PROMPT = """You are explaining a security finding produced by Aevrin, an MCP security scanner.

Aevrin's scanners have already determined what is true. Your job is to explain what it means to the person reading it, not to look for new vulnerabilities.

Rules, in order of importance:

1. Use only the supplied evidence. Every claim you make must be traceable to something in the evidence document. If the evidence does not establish something, say that it does not, rather than filling the gap.
2. Never invent a vulnerability, a CVE, a file, a tool, or a capability that is not in the evidence.
3. If the evidence includes a coverage section indicating incomplete scanning, say plainly that the unscanned categories are unknown, not safe. Never describe a partially scanned target as clean.
4. Do not restate the whole document. The reader can already see the finding.
5. Do not give reassurance the evidence does not support. If something is dangerous, say so directly.

Cover, briefly and in this order:
- What was found
- Why it matters
- What capability or access is involved
- What an attacker could plausibly reach, limited strictly to what the evidence shows
- What to change

Write plain prose for a working developer. No preamble, no headings, no markdown formatting, no bullet characters. Around 120 words unless asked for more."""

# The "Explain more" variant. Same rules, longer budget.
SYSTEM_PROMPT_DETAILED = SYSTEM_PROMPT.replace(
    "Around 120 words unless asked for more.",
    "Around 350 words. Walk through the mechanism concretely, still using only the supplied evidence.",
)


def _build_user_prompt(document: dict[str, Any], question: str | None) -> str:
    ask = question or _default_question(document.get("subject_type", ""))
    return f"{ask}\n\nEvidence:\n{render_for_prompt(document)}"


def _default_question(subject_type: str) -> str:
    return {
        "finding": "Explain this security finding.",
        "trust_grade": "Explain why this MCP server received this trust grade.",
        "agent_posture": "Explain the security risk in this agent's current posture.",
        "permission": "Explain what this permission actually allows.",
        "skill": "Explain what capability this skill grants.",
        "attack_path": "Explain this attack path and what makes it reachable.",
        "scan": "Explain the overall result of this scan.",
        "listing": "Explain the security position of this MCP server.",
    }.get(subject_type, "Explain this security evidence.")


async def get_cached(
    db: SupabaseRest, *, hash_value: str, subject_type: str
) -> dict[str, Any] | None:
    """A previous explanation of byte-identical evidence, if one exists.

    Shared across users deliberately. The evidence hash contains no identity,
    so two people looking at the same public listing genuinely are asking the
    same question, and charging both for it would be waste rather than
    isolation. Evidence built from a private scan hashes differently because
    the scan differs, so nothing crosses a tenant boundary by doing this.
    """
    try:
        rows = await db.select(
            "ai_explanations",
            {"evidence_hash": hash_value, "subject_type": subject_type},
            limit=1,
        )
    except Exception:
        logger.warning("explanation cache lookup failed", exc_info=True)
        return None
    return rows[0] if rows else None


async def explain(
    db: SupabaseRest,
    settings: Settings,
    *,
    user_id: str,
    document: dict[str, Any],
    subject_type: str,
    subject_id: str | None = None,
    question: str | None = None,
    detailed: bool = False,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Explain this evidence, from cache if possible and from a provider if not.

    Raises ExplanationUnavailable when no configured provider could answer.
    That is the only failure mode callers need to handle, and handling it means
    rendering the finding without an explanation.
    """
    # `detailed` changes the answer, so it has to change the key. Without this
    # the short version would be served forever to anyone pressing
    # "Explain more".
    keyed = {**document, "_detail": "long" if detailed else "short"}
    hash_value = evidence_hash(keyed)

    if not force_refresh:
        cached = await get_cached(db, hash_value=hash_value, subject_type=subject_type)
        if cached:
            return {**cached, "cached": True}

    credentials = await load_credentials(db, settings, user_id=user_id)
    if not credentials:
        raise ExplanationUnavailable(
            "No AI provider is configured. Add one in Settings, AI Providers."
        )

    system = SYSTEM_PROMPT_DETAILED if detailed else SYSTEM_PROMPT
    user_prompt = _build_user_prompt(document, question)

    completion, attempts = await _complete_with_fallback(
        credentials, system=system, user=user_prompt, detailed=detailed
    )
    if completion is None:
        raise ExplanationUnavailable(
            "AI explanation unavailable: " + "; ".join(attempts[:3])
        )

    stored = await _store(
        db,
        hash_value=hash_value,
        subject_type=subject_type,
        subject_id=subject_id,
        completion=completion,
        user_id=user_id,
        detailed=detailed,
    )
    return {**stored, "cached": False}


async def _complete_with_fallback(
    credentials: list[ProviderCredential], *, system: str, user: str, detailed: bool
) -> tuple[Completion | None, list[str]]:
    """Try each configured provider in priority order.

    Fallback is deliberately shallow: try the next one, in the order the user
    put them in, and stop. No health scoring, no circuit breaker, no automatic
    reordering. A user who ranked Groq first and Gemini second gets exactly
    that, every time, which is the only behaviour that can be reasoned about
    when the question is "which vendor saw my infrastructure details".
    """
    attempts: list[str] = []
    for credential in credentials:
        try:
            completion = await complete(
                credential.provider,
                credential.api_key,
                model=credential.model_id or "",
                system=credential.system_prompt or system,
                user=user,
                max_tokens=credential.max_tokens or (1600 if detailed else 700),
                temperature=credential.temperature if credential.temperature is not None else 0.2,
            )
            return completion, attempts
        except ProviderNotConfigured as exc:
            attempts.append(f"{credential.provider}: {exc}")
        except ProviderError as exc:
            attempts.append(f"{credential.provider}: {exc}")
            logger.info("provider %s failed, trying next", credential.provider)
        except Exception:
            attempts.append(f"{credential.provider}: unexpected error")
            logger.warning("provider %s raised unexpectedly", credential.provider, exc_info=True)
    return None, attempts


def _split_summary(text: str) -> tuple[str, str | None]:
    """First paragraph is the summary; the rest is detail.

    The UI shows a short answer by default and expands on request, so the
    split happens once here rather than in every component that renders one.
    """
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not parts:
        return text.strip(), None
    return parts[0], "\n\n".join(parts[1:]) or None


async def _store(
    db: SupabaseRest,
    *,
    hash_value: str,
    subject_type: str,
    subject_id: str | None,
    completion: Completion,
    user_id: str,
    detailed: bool,
) -> dict[str, Any]:
    summary, detail = _split_summary(completion.text)
    row = {
        "evidence_hash": hash_value,
        "subject_type": subject_type,
        "subject_id": str(subject_id) if subject_id else None,
        "provider": completion.provider,
        "model_id": completion.model_id,
        "summary": summary,
        "detail": detail,
        "input_tokens": completion.input_tokens,
        "output_tokens": completion.output_tokens,
        "created_by": user_id,
    }
    try:
        inserted = await db.insert("ai_explanations", row, upsert_on="evidence_hash,subject_type")
        if inserted:
            return inserted[0]
    except Exception:
        # Failing to cache is not failing to explain. The user gets their
        # answer; the next reader pays for it again.
        logger.warning("could not cache explanation", exc_info=True)
    return row


async def invalidate_for_subject(db: SupabaseRest, *, subject_type: str, subject_id: str) -> None:
    """Drop cached explanations for a subject whose evidence has been replaced.

    Called after a forced rescan. Strictly speaking the hash would already
    differ and the stale rows would simply never be read again, but leaving
    them means a detail page that looks up by subject rather than by hash
    could still surface an explanation of superseded evidence.
    """
    try:
        await db.delete("ai_explanations", {"subject_type": subject_type, "subject_id": subject_id})
    except Exception:
        logger.warning("could not invalidate explanations for %s", subject_id, exc_info=True)
