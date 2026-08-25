"""DeepSeek client for LLM triage.

One module for both callers so model choice, caching, timeouts and error
handling stay in a single place.

Three things about this API are load-bearing and were confirmed against the
live endpoint rather than assumed:

1. **Prefix caching is automatic and worth designing for.** Sending an
   identical leading system message drops repeat input to a cache-hit rate
   50x cheaper. Measured: a 1600-token prompt billed 1600 miss tokens on the
   first call, then 1536 hit / 64 miss on every call after. Triage runs once
   per finding and a single scan averages ~39 findings, so the static
   instruction block is deliberately kept in its own system message and
   never interpolated with per-finding text, which would break the prefix.

2. **`response_format: json_object` requires the literal word "json"
   somewhere in the prompt**, otherwise the request is rejected outright
   with `invalid_request_error`. Both prompt builders here satisfy that.

3. **Completions include reasoning tokens, and they dominate the budget.**
   A trivial classification returned 129 completion tokens of which 121 were
   reasoning. A real triage prompt spent 694 of a 700-token budget and
   truncated the JSON mid-string; the same prompt at 2000 used 1199 and
   completed. `max_tokens` here is a reasoning budget with an answer
   attached, so it is set well above what the visible output needs.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("aevrin.deepseek")

BASE_URL = "https://api.deepseek.com"

# Free accounts get the cheap model; everything paid, including Hobby, gets
# the strong one.
FLASH_MODEL = "deepseek-v4-flash"
PRO_MODEL = "deepseek-v4-pro"


class DeepSeekError(RuntimeError):
    pass


@dataclass
class DeepSeekResult:
    content: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    truncated: bool

    @property
    def cache_hit_ratio(self) -> float:
        return self.cache_hit_tokens / self.prompt_tokens if self.prompt_tokens else 0.0


async def complete_json(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    timeout_s: float,
) -> DeepSeekResult:
    """One JSON-mode completion.

    `system_prompt` must be byte-identical across calls for prefix caching to
    engage, so callers pass a module-level constant rather than an f-string.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )

    if resp.status_code >= 400:
        # Body carries the actual reason (bad key, rate limit, insufficient
        # balance). Truncated because it is echoed into logs.
        raise DeepSeekError(f"{resp.status_code}: {resp.text[:300]}")

    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        raise DeepSeekError("response contained no choices")

    usage = body.get("usage") or {}
    return DeepSeekResult(
        content=choices[0]["message"]["content"],
        # Distinguishes "ran out of budget mid-JSON" from "returned something
        # unparseable". Both look identical to a JSON decoder, and only the
        # first is fixed by raising max_tokens; worth being able to tell
        # apart in logs rather than guessing.
        truncated=choices[0].get("finish_reason") == "length",
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        cache_hit_tokens=int(usage.get("prompt_cache_hit_tokens") or 0),
    )


def parse_json_object(raw: str) -> dict[str, Any]:
    """JSON mode still occasionally wraps the object in prose or a fence, so
    fall back to the outermost braces rather than failing the whole finding
    over a formatting quirk."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise TypeError("expected a JSON object")
    return parsed
