"""One interface over Groq, OpenAI, Anthropic and Google Gemini.

Why this and not LiteLLM
------------------------
LiteLLM was evaluated for this. Its core is MIT licensed (everything outside
`enterprise/`), so it clears the licence bar. It was not adopted because of
what it costs to carry: a very large dependency surface, its own retry,
caching and routing opinions, and a release cadence that would put a moving
third party directly in the path of a security product's explanation feature.

What Aevrin actually needs from a provider is two HTTP calls -- list the
models, complete a prompt -- against four vendors, three of which already
speak the same wire format. That is this file. It is small enough to read in
one sitting, has no dependency beyond httpx (already present), and fails in
ways this codebase already knows how to handle.

The evaluation and its outcome are recorded in EXTERNAL_REFERENCES.md.

Shape of the thing
------------------
Providers differ in exactly three ways: the base URL, how the key is
presented, and the JSON shape. Everything else is common, so the differences
live in a table and the logic does not branch.

Nothing here ever logs a key, echoes one back, or puts one in an exception
message. The failure paths were written first, because a provider integration
that leaks its credential in a stack trace has done more damage than the
outage it was reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

logger = logging.getLogger("aevrin.ai_providers")

ProviderKey = Literal["groq", "gemini", "anthropic", "openai"]

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
# A ceiling on what any single explanation may consume, independent of what a
# user configures. Explanations are short by design; this exists so a
# misconfigured max_tokens cannot turn one button press into a large bill.
MAX_OUTPUT_TOKENS_CEILING = 4096
MAX_INPUT_CHARS = 60_000


class ProviderError(Exception):
    """A provider call failed.

    Carries a message safe to show a user and, deliberately, nothing else. The
    provider's raw response body is not attached: it can echo request content,
    and request content is one careless log line away from being the API key.
    """

    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class ProviderNotConfigured(ProviderError):
    pass


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    display_name: str
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)
    deprecated: bool = False


@dataclass(frozen=True)
class Completion:
    text: str
    model_id: str
    provider: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    models_path: str
    chat_path: str
    # 'bearer'  -> Authorization: Bearer <key>          (Groq, OpenAI)
    # 'x-api-key' -> x-api-key + anthropic-version      (Anthropic)
    # 'goog'    -> x-goog-api-key                       (Gemini)
    auth_style: str
    console_url: str
    docs_url: str


# Endpoints verified against each vendor's current published reference.
# Note on Gemini: its OpenAI-compatibility shim does *not* serve a working
# models list (it answers 401 for API-key auth), so the native v1beta endpoint
# is used instead. Sending the key as a header rather than the `?key=` query
# parameter keeps it out of URLs, and therefore out of access logs.
SPECS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        key="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        models_path="/models",
        chat_path="/chat/completions",
        auth_style="bearer",
        console_url="https://console.groq.com/",
        docs_url="https://console.groq.com/docs/models",
    ),
    "openai": ProviderSpec(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        models_path="/models",
        chat_path="/chat/completions",
        auth_style="bearer",
        console_url="https://platform.openai.com/",
        docs_url="https://platform.openai.com/docs/models",
    ),
    "anthropic": ProviderSpec(
        key="anthropic",
        label="Anthropic",
        base_url="https://api.anthropic.com/v1",
        models_path="/models",
        chat_path="/messages",
        auth_style="x-api-key",
        console_url="https://console.anthropic.com/",
        docs_url="https://docs.claude.com/en/docs/about-claude/models",
    ),
    "gemini": ProviderSpec(
        key="gemini",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        models_path="/models",
        chat_path="/models",  # completed as /models/{model}:generateContent
        auth_style="goog",
        console_url="https://aistudio.google.com/",
        docs_url="https://ai.google.dev/gemini-api/docs/models",
    ),
}

PROVIDER_KEYS: tuple[str, ...] = tuple(SPECS)


def _auth_headers(spec: ProviderSpec, api_key: str) -> dict[str, str]:
    if spec.auth_style == "bearer":
        return {"Authorization": f"Bearer {api_key}"}
    if spec.auth_style == "x-api-key":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    if spec.auth_style == "goog":
        return {"x-goog-api-key": api_key}
    raise ProviderNotConfigured(f"unknown auth style for {spec.key}")


def _raise_for_status(spec: ProviderSpec, response: httpx.Response) -> None:
    """Translate a provider's failure into something a user can act on.

    The provider's body is examined for a message but never included wholesale
    -- some vendors echo the submitted prompt back inside an error, and that
    prompt is evidence about somebody's infrastructure.
    """
    if response.status_code < 400:
        return
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message", ""))[:200]
            elif isinstance(error, str):
                detail = error[:200]
    except ValueError:
        detail = ""

    if response.status_code in (401, 403):
        raise ProviderError(
            f"{spec.label} rejected the API key. Check it in Settings, AI Providers.",
            status_code=response.status_code,
        )
    if response.status_code == 429:
        raise ProviderError(
            f"{spec.label} rate limit reached. Try again shortly.",
            status_code=429,
            retryable=True,
        )
    if response.status_code >= 500:
        raise ProviderError(
            f"{spec.label} is unavailable right now.", status_code=response.status_code, retryable=True
        )
    raise ProviderError(
        f"{spec.label} refused the request" + (f": {detail}" if detail else "."),
        status_code=response.status_code,
    )


# --------------------------------------------------------------------------
# Model listing


async def list_models(provider: str, api_key: str) -> list[ModelInfo]:
    """Every model this key can reach.

    Requires a key for all four providers. That is a fact about their APIs,
    not a design choice here: none of them publish a model list anonymously.
    The catalogue sync therefore needs a credential of Aevrin's own, and never
    borrows a customer's -- see services/ai/provider_sync.py.
    """
    spec = SPECS.get(provider)
    if spec is None:
        raise ProviderNotConfigured(f"unknown provider {provider!r}")
    if not api_key:
        raise ProviderNotConfigured(f"no API key available for {spec.label}")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.get(
                f"{spec.base_url}{spec.models_path}",
                headers={**_auth_headers(spec, api_key), "Accept": "application/json"},
                params={"pageSize": 200} if spec.auth_style == "goog" else None,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{spec.label} could not be reached.", retryable=True) from exc

    _raise_for_status(spec, response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(f"{spec.label} returned a non-JSON model list.") from exc

    if provider == "gemini":
        return _parse_gemini_models(payload)
    if provider == "anthropic":
        return _parse_anthropic_models(payload)
    return _parse_openai_style_models(payload)



# Model families that exist on the same /v1/models list as the chat models
# but cannot be used through the /chat/completions endpoint complete() calls
# -- they belong to a different endpoint (audio transcription, text-to-speech,
# embeddings, moderation, image/video generation, legacy text completion) and
# a request against them would fail with a provider error the moment someone
# picked "Explain this finding" and it actually ran. Matched against the
# model id, case-insensitively; this is a statement about API surface, not
# about quality, so nothing here is excluded for being a smaller or older
# chat model. "guard"/"safeguard" classifiers (llama-prompt-guard,
# gpt-oss-safeguard) are included too: they answer with a safety label, not
# an explanation, so they are just as unusable for this feature even though
# they do technically accept a /chat/completions request.
_NON_CHAT_MODEL_MARKERS = (
    "whisper",
    "tts",
    "embed",
    "moderation",
    "dall-e",
    "gpt-image",
    "sora",
    "davinci",
    "babbage",
    "computer-use",
    "guard",
    "safeguard",
)


def _looks_like_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NON_CHAT_MODEL_MARKERS)


def _parse_openai_style_models(payload: Any) -> list[ModelInfo]:
    """Groq and OpenAI both return {"data": [{"id": ...}]}.

    Groq adds context_window and a public `active` flag; OpenAI adds neither,
    so both are read optionally rather than assumed. Neither endpoint
    distinguishes chat models from audio/embedding/moderation/image models in
    this list, so _looks_like_chat_model does that filtering here -- the same
    reasoning Gemini's parser already applies via supportedGenerationMethods.
    """
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    models: list[ModelInfo] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        if not _looks_like_chat_model(model_id):
            continue
        models.append(
            ModelInfo(
                model_id=model_id[:200],
                display_name=model_id[:200],
                context_window=_positive_int(entry.get("context_window")),
                max_output_tokens=_positive_int(entry.get("max_completion_tokens")),
                capabilities={"owned_by": str(entry.get("owned_by", ""))[:80]},
                # Groq publishes `active: false` for a model it still lists.
                deprecated=entry.get("active") is False,
            )
        )
    return models


def _parse_anthropic_models(payload: Any) -> list[ModelInfo]:
    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    models: list[ModelInfo] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue
        models.append(
            ModelInfo(
                model_id=model_id[:200],
                display_name=str(entry.get("display_name") or model_id)[:200],
                capabilities={"type": str(entry.get("type", ""))[:40]},
            )
        )
    return models


def _parse_gemini_models(payload: Any) -> list[ModelInfo]:
    """Gemini returns {"models": [{"name": "models/x", "displayName": ...}]}.

    Only models that can actually generate content are kept: the same list
    carries embedding models, and offering one in a dropdown labelled
    "explain this finding" would produce a confusing failure at the moment of
    use rather than an honest absence at the moment of choosing.
    """
    entries = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return []
    models: list[ModelInfo] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw_name = entry.get("name")
        if not isinstance(raw_name, str) or not raw_name:
            continue
        methods = entry.get("supportedGenerationMethods")
        methods = methods if isinstance(methods, list) else []
        if methods and "generateContent" not in methods:
            continue
        model_id = raw_name.removeprefix("models/")
        models.append(
            ModelInfo(
                model_id=model_id[:200],
                display_name=str(entry.get("displayName") or model_id)[:200],
                context_window=_positive_int(entry.get("inputTokenLimit")),
                max_output_tokens=_positive_int(entry.get("outputTokenLimit")),
                capabilities={"methods": [str(m)[:40] for m in methods[:10]]},
            )
        )
    return models


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


# --------------------------------------------------------------------------
# Completion


async def complete(
    provider: str,
    api_key: str,
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 800,
    temperature: float = 0.2,
) -> Completion:
    """One prompt, one answer.

    The input is truncated to MAX_INPUT_CHARS before it leaves this process.
    Evidence documents are assembled from scan output, and scan output is
    ultimately shaped by a repository somebody else wrote; a bound here is
    what stops a hostile README turning an explanation request into a very
    expensive one.
    """
    spec = SPECS.get(provider)
    if spec is None:
        raise ProviderNotConfigured(f"unknown provider {provider!r}")
    if not api_key:
        raise ProviderNotConfigured(f"no API key configured for {spec.label}")
    if not model:
        raise ProviderNotConfigured(f"no model selected for {spec.label}")

    user = user[:MAX_INPUT_CHARS]
    max_tokens = max(1, min(int(max_tokens), MAX_OUTPUT_TOKENS_CEILING))
    temperature = max(0.0, min(float(temperature), 2.0))

    if provider == "anthropic":
        url = f"{spec.base_url}{spec.chat_path}"
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
    elif provider == "gemini":
        url = f"{spec.base_url}/models/{model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
    else:
        url = f"{spec.base_url}{spec.chat_path}"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.post(
                url,
                headers={**_auth_headers(spec, api_key), "Content-Type": "application/json"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"{spec.label} could not be reached.", retryable=True) from exc

    _raise_for_status(spec, response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(f"{spec.label} returned a non-JSON response.") from exc

    text, input_tokens, output_tokens = _extract_completion(provider, payload)
    if not text:
        raise ProviderError(f"{spec.label} returned an empty response.")

    return Completion(
        text=text,
        model_id=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _extract_completion(provider: str, payload: Any) -> tuple[str, int | None, int | None]:
    if not isinstance(payload, dict):
        return "", None, None

    # Every `x if isinstance(x, dict) else default` below binds x to a local
    # first, then narrows that local, rather than checking isinstance on one
    # call to .get(...) and reading a second, separate call to .get(...) in
    # the ternary's true branch: mypy cannot carry a narrowing across two
    # calls to the same method, even though they return the same value here.

    if provider == "anthropic":
        blocks = payload.get("content")
        text = ""
        if isinstance(blocks, list):
            text = "".join(
                b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
            )
        maybe_usage = payload.get("usage")
        usage = maybe_usage if isinstance(maybe_usage, dict) else {}
        return text.strip(), _positive_int(usage.get("input_tokens")), _positive_int(usage.get("output_tokens"))

    if provider == "gemini":
        candidates = payload.get("candidates")
        text = ""
        if isinstance(candidates, list) and candidates:
            first = candidates[0]
            maybe_content = first.get("content") if isinstance(first, dict) else None
            content = maybe_content if isinstance(maybe_content, dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if isinstance(parts, list):
                text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        maybe_usage = payload.get("usageMetadata")
        usage = maybe_usage if isinstance(maybe_usage, dict) else {}
        return (
            text.strip(),
            _positive_int(usage.get("promptTokenCount")),
            _positive_int(usage.get("candidatesTokenCount")),
        )

    choices = payload.get("choices")
    text = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            text = str(message.get("content") or "")
    maybe_usage = payload.get("usage")
    usage = maybe_usage if isinstance(maybe_usage, dict) else {}
    return (
        text.strip(),
        _positive_int(usage.get("prompt_tokens")),
        _positive_int(usage.get("completion_tokens")),
    )
