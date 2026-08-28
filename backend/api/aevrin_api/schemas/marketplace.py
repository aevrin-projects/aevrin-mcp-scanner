"""Request and response models for the marketplace.

Response models are deliberately loose where the payload is a decorated
database row (`dict[str, Any]`), and strict where a client sends something.
The asymmetry is intentional: an over-specified response model turns adding a
column into a breaking change, whereas an under-specified request model turns
a typo into a database error.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Sort = Literal["recommended", "security", "popular", "recently_updated", "recently_added", "az"]
PriceType = Literal["free", "freemium", "paid", "open_source", "commercial", "unknown"]
Grade = Literal["A", "B", "C", "D"]
Visibility = Literal["public", "private", "unlisted"]
PolicyAction = Literal["allow", "require_approval", "block"]


class ListingSummary(BaseModel):
    """One catalogue card.

    `security` and `popularity` are separate objects rather than flattened
    fields, and that separation is load-bearing rather than cosmetic: it makes
    it structurally awkward for a client to read a star count as though it
    were a safety signal.
    """

    id: str
    slug: str
    title: str
    description: str = ""
    publisher: str | None = None
    repository_url: str | None = None
    homepage_url: str | None = None
    registry_url: str | None = None
    source: str
    license: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    price_type: PriceType = "unknown"
    pricing_url: str | None = None
    install_targets: list[str] = Field(default_factory=list)
    featured: bool = False
    latest_version: str | None = None
    security: dict[str, Any]
    popularity: dict[str, Any]
    ranking_score: float = 0
    is_favorited: bool = False

    model_config = {"extra": "allow"}


class ListingPage(BaseModel):
    items: list[ListingSummary]
    page: int
    page_size: int
    has_more: bool
    sort: str


class CategoryOut(BaseModel):
    slug: str
    name: str
    description: str | None = None
    count: int = 0


class SubmitListingRequest(BaseModel):
    """A submission is a URL and, optionally, a sentence.

    Nothing else is accepted. Every other field is derived from the source,
    because a submitter typing their own metadata is a submitter who can claim
    whatever they like about somebody else's software.
    """

    source_url: str = Field(min_length=8, max_length=500)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("source_url")
    @classmethod
    def must_be_https(cls, value: str) -> str:
        if not value.strip().lower().startswith("https://"):
            raise ValueError("Only HTTPS URLs can be submitted.")
        return value.strip()


class ReportRequest(BaseModel):
    kind: Literal["listing", "security"]
    reason: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=4000)


class FavoriteRequest(BaseModel):
    favorite: bool = True


class InstallPlanRequest(BaseModel):
    agent: Literal["claude-code", "codex", "cursor", "generic"]
    scope: Literal["global", "project"] = "global"


class InstallPlanResponse(BaseModel):
    """What installing this would actually do, before anything is done.

    Returned so a person can read the capabilities and the grade *before*
    committing, which is the entire point of putting a security scanner in
    front of a marketplace. `policy_action` reflects the organisation's rules,
    so a blocked install is refused with a reason rather than silently offered.
    """

    listing: ListingSummary
    agent: str
    scope: str
    config: dict[str, Any]
    capabilities: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    policy_action: PolicyAction = "allow"
    policy_reason: str | None = None


class AdminListingPatch(BaseModel):
    """Everything an admin may edit.

    There is no field here that touches a grade, a score, or coverage. That is
    not an oversight: those are written from scan evidence and an admin who
    could type a better letter would be able to make an unsafe server look
    safe.
    """

    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    categories: list[str] | None = None
    tags: list[str] | None = None
    price_type: PriceType | None = None
    price_amount: float | None = None
    price_currency: str | None = Field(default=None, max_length=3)
    billing_period: Literal["month", "year", "once", "usage"] | None = None
    pricing_url: str | None = Field(default=None, max_length=500)
    homepage_url: str | None = Field(default=None, max_length=500)
    license: str | None = Field(default=None, max_length=60)
    featured: bool | None = None
    visibility: Visibility | None = None
    install_targets: list[str] | None = None
    # Required for anything audited, and shown on the public timeline.
    reason: str | None = Field(default=None, max_length=1000)


class AdminStatusRequest(BaseModel):
    status: Literal["draft", "review", "approved", "rejected", "published", "suspended"]
    reason: str | None = Field(default=None, max_length=1000)


class AdminCreateListingRequest(BaseModel):
    source_url: str = Field(min_length=8, max_length=500)
    visibility: Visibility = "public"
    # Set only for a private, organisation-owned server.
    org_id: str | None = None


class SubmissionDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


class ReportDecisionRequest(BaseModel):
    status: Literal["reviewing", "dismissed", "actioned"]
    note: str | None = Field(default=None, max_length=2000)


class PolicyRequest(BaseModel):
    """An organisation's install policy.

    All four grades are required. A partial policy leaves a grade undefined,
    and an undefined grade has to fall back to something -- a decision the
    organisation should make deliberately rather than inherit.
    """

    grade_actions: dict[Grade, PolicyAction]
    unscanned_action: PolicyAction = "require_approval"

    @field_validator("grade_actions")
    @classmethod
    def all_grades_present(cls, value: dict[str, str]) -> dict[str, str]:
        missing = {"A", "B", "C", "D"} - set(value)
        if missing:
            raise ValueError(f"An action is required for every grade; missing {sorted(missing)}.")
        return value


class ScanRequest(BaseModel):
    version_id: str | None = None
    force: bool = False
