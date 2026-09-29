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

PriceType = Literal["free", "freemium", "paid", "open_source", "commercial", "unknown"]
# Mirrors ITEM_TYPES in services/marketplace/items.py and the check in 0048.
ItemType = Literal[
    "mcp_server", "skill", "prompt", "tool", "agent", "component", "template",
    "workflow", "library", "cli", "backend", "frontend", "infrastructure",
    "product", "repository", "integration", "dataset", "documentation", "other",
]
Visibility = Literal["public", "private", "unlisted"]


class ListingSummary(BaseModel):
    """One catalogue card.

    Carries no scan result or grade: the registry is discovery only.
    `popularity` is its own object, each metric named for what it measures.
    """

    id: str
    slug: str
    title: str
    description: str = ""
    item_type: str = "mcp_server"
    author: str | None = None
    publisher: str | None = None
    repository_url: str | None = None
    homepage_url: str | None = None
    registry_url: str | None = None
    source: str
    license: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    price_type: PriceType = "unknown"
    pricing_url: str | None = None
    install_targets: list[str] = Field(default_factory=list)
    featured: bool = False
    latest_version: str | None = None
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


class TypeCount(BaseModel):
    type: str
    count: int


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


class AdminListingPatch(BaseModel):
    """Everything an admin may edit.

    There is no `status`: that changes only through the status endpoint,
    which runs the publish gate.

    `content` and `installation` are validated in full by
    services/marketplace/items.py; they are typed loosely here so the service
    can report every problem at once rather than FastAPI reporting the first.
    """

    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    item_type: ItemType | None = None
    author: str | None = Field(default=None, max_length=200)
    publisher: str | None = Field(default=None, max_length=200)
    categories: list[str] | None = None
    tags: list[str] | None = None
    technologies: list[str] | None = None
    capabilities: list[str] | None = None
    use_cases: list[str] | None = None
    content: dict[str, Any] | None = None
    repository_url: str | None = Field(default=None, max_length=500)
    repository_ref: str | None = Field(default=None, max_length=200)
    installation: dict[str, Any] | None = None
    latest_version: str | None = Field(default=None, max_length=100)
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
    # Restoring an archived item is a move to "draft".
    status: Literal["draft", "review", "approved", "rejected", "published", "suspended", "archived"]
    reason: str | None = Field(default=None, max_length=1000)


class AdminCreateListingRequest(BaseModel):
    """Add an item: from a URL (derived like a suggestion), or by hand.

    A prompt or a skill often has no repository at all, so the URL is
    optional; without one, a title is required.
    """

    item_type: ItemType = "mcp_server"
    source_url: str | None = Field(default=None, min_length=8, max_length=500)
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    visibility: Visibility = "public"
    # Set only for a private, organisation-owned item.
    org_id: str | None = None


class AdminDeleteRequest(BaseModel):
    # The item's slug, typed back. A stray click cannot delete anything.
    confirm_slug: str = Field(min_length=1, max_length=200)


class LinkIn(BaseModel):
    related_id: str = Field(min_length=1, max_length=64)
    relation: Literal["uses", "related"] = "related"


class AdminLinksRequest(BaseModel):
    links: list[LinkIn] = Field(default_factory=list, max_length=50)


class CategoryRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = Field(default=100, ge=0, le=10000)


class SubmissionDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


class ReportDecisionRequest(BaseModel):
    status: Literal["reviewing", "dismissed", "actioned"]
    note: str | None = Field(default=None, max_length=2000)


class BulkPublishSkipped(BaseModel):
    """Candidates left as drafts, each counted once, for the first reason
    that applies, in this order."""

    already_published_repository: int
    failed_gate: int
    duplicate_repository: int


class BulkPublishReason(BaseModel):
    reason: str
    count: int


class BulkPublishFailure(BaseModel):
    id: str
    slug: str | None = None
    reason: str


class BulkPublishSample(BaseModel):
    id: str
    slug: str | None = None
    title: str | None = None
    repository_url: str | None = None
    github_stars: int | None = None
    npm_downloads_last_month: int | None = None


class BulkPublishResult(BaseModel):
    """What "Publish qualifying drafts" would do (a preview) or did.

    A fixed shape, unlike the decorated rows above: the admin UI reads every
    field, and the confirm dialog states the counts and the criteria verbatim.
    """

    dry_run: bool
    criteria: dict[str, Any]
    # Drafts that met the filters and the popularity bar.
    considered: int
    # Of those, how many pass everything: the total to publish over all calls.
    qualifying: int
    # How many this call acts on (at most `criteria.max_per_call`).
    batch: int
    # Published by this call; always 0 for a preview.
    published: int
    failed: list[BulkPublishFailure]
    # Qualifying drafts beyond this call's batch. Call again to continue.
    remaining: int
    skipped: BulkPublishSkipped
    # The most common publish-gate refusals, most frequent first.
    gate_reasons: list[BulkPublishReason]
    sample: list[BulkPublishSample]
