"""Request and response models for AI providers and explanations.

The single most important thing about this file is what is absent from it.
There is no response model anywhere below that carries an API key, and no
field named for one. `ProviderCredentialOut` reports `key_present` and a
four-character hint; the key itself has no route to a client because no shape
here can express it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Provider = Literal["groq", "gemini", "anthropic", "openai"]
SubjectType = Literal[
    "finding", "trust_grade", "agent_posture", "permission", "skill",
    "attack_path", "scan", "listing",
]


class SaveProviderRequest(BaseModel):
    """Adding or rotating a key.

    `api_key` is write-only by construction: it appears in this request model
    and in no response model anywhere in the codebase.
    """

    provider: Provider
    api_key: str = Field(min_length=8, max_length=400)
    model_id: str | None = Field(default=None, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    system_prompt: str | None = Field(default=None, max_length=4000)
    priority: int = Field(default=1, ge=1, le=5)


class UpdateProviderRequest(BaseModel):
    """Changing configuration without touching the key.

    Deliberately has no `api_key` field. Rotating a key goes through
    SaveProviderRequest, which makes rotation an explicit act rather than
    something a partial update can do by accident.
    """

    model_id: str | None = Field(default=None, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32000)
    system_prompt: str | None = Field(default=None, max_length=4000)
    priority: int | None = Field(default=None, ge=1, le=5)
    enabled: bool | None = None


class ProviderCredentialOut(BaseModel):
    provider: str
    label: str
    console_url: str | None = None
    docs_url: str | None = None
    key_present: bool
    key_hint: str = ""
    model_id: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    priority: int = 1
    enabled: bool = True
    created_at: str | None = None
    updated_at: str | None = None


class ModelOut(BaseModel):
    provider: str
    model_id: str
    display_name: str
    status: Literal["active", "deprecated", "unavailable"]
    context_window: int | None = None
    max_output_tokens: int | None = None
    documentation_url: str | None = None
    last_checked_at: str | None = None


class ProviderStatusOut(BaseModel):
    """What the admin panel shows for one provider.

    `catalog_credential_configured` is here because its absence is the most
    common reason a model list is empty, and an admin staring at zero models
    deserves to be told that rather than left to guess.
    """

    provider: str
    label: str
    console_url: str | None = None
    docs_url: str | None = None
    catalog_credential_configured: bool
    active_models: int
    last_successful_sync: str | None = None
    last_attempted_sync: str | None = None
    sync_error: str | None = None
    healthy: bool


class ExplainRequest(BaseModel):
    subject_type: SubjectType
    subject_id: str = Field(max_length=200)
    detailed: bool = False
    # Forces a fresh call past the cache. Rate limited, because it is the one
    # request shape that can spend money on repeat.
    refresh: bool = False


class ExplanationOut(BaseModel):
    """An explanation, always labelled as one.

    `provider` and `model_id` are required rather than optional. A reader must
    always be able to see which vendor produced this, both because fallback
    can change it and because an AI explanation and a verified finding must
    never be presentable as the same kind of claim.
    """

    summary: str
    detail: str | None = None
    provider: str
    model_id: str
    cached: bool = False
    created_at: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    model_config = {"extra": "allow"}


class ExplanationUnavailableOut(BaseModel):
    """The failure shape, which is a normal 200 rather than an error.

    An unavailable explanation is not a failed request: the finding it would
    have described is intact and is what the page is actually about. Returning
    a 500 here would let an AI outage look like a scanner outage.
    """

    available: Literal[False] = False
    reason: str


class SyncReportOut(BaseModel):
    ok: bool
    providers: list[dict[str, Any]] = Field(default_factory=list)
    started_at: str | None = None
