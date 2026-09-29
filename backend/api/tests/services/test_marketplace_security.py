"""The rules that keep the registry honest: ranking, the admin boundary, and
the absence of any security claim.

The registry is discovery only (DECISIONS.md). These pin that it ranks on
signals it can measure, that an edit cannot reach a column it should not, and
that no response carries a scan result, a grade, or a scan state for any item
type.
"""

from __future__ import annotations

from typing import Any

import pytest

from aevrin_api.schemas.marketplace import ListingPage, ListingSummary
from aevrin_api.services.marketplace import catalog, items
from aevrin_api.services.marketplace.admin import EDITABLE_FIELDS
from aevrin_api.services.marketplace.ranking import SORT_ORDERS, WEIGHTS, compute_ranking

# Keys that would put a security claim on a registry item. None may appear in
# a browse card, a detail response or a related-item card.
_SCAN_KEYS = {
    "security", "grade", "trust_grade", "risk_score", "scan_id", "scan_status",
    "scanned_at", "scanned_version", "coverage_complete", "grade_rationale",
    "current_version", "current_trust_grade", "current_risk_score",
    "current_coverage_complete", "current_scanned_at",
}


# --------------------------------------------------------------------------
# Ranking


def test_the_weights_sum_to_100_and_have_no_security_component() -> None:
    assert sum(WEIGHTS.values()) == 100
    assert set(WEIGHTS) == {"popularity", "maintenance", "community", "documentation"}


def test_there_is_no_security_sort() -> None:
    assert "security" not in SORT_ORDERS
    assert not any("grade" in order or "risk" in order for order in SORT_ORDERS.values())


def test_missing_metadata_does_not_become_zero_confidence() -> None:
    """A listing with no GitHub data should score 0 on popularity because we
    know nothing, not because we decided it was unpopular."""
    result = compute_ranking({"github_stars": None, "github_forks": None})
    assert result.components["popularity"] == 0.0
    assert result.components["maintenance"] == 0.0


def test_ranking_shows_its_working() -> None:
    breakdown = compute_ranking({"github_stars": 10}).as_dict()
    assert set(breakdown["components"]) == set(WEIGHTS)
    assert breakdown["weights"] == WEIGHTS


# --------------------------------------------------------------------------
# Admin boundary


def test_an_admin_cannot_edit_status_or_ranking() -> None:
    """Status goes through the publish gate; the ranking is computed."""
    assert {"status", "ranking_score", "favorite_count", "marketplace_views"}.isdisjoint(
        EDITABLE_FIELDS
    )


# --------------------------------------------------------------------------
# No security claim, for any item type


def _row(item_type: str) -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "slug": f"a-{item_type}",
        "title": "An item",
        "description": "Does a thing.",
        "item_type": item_type,
        "source": "admin",
        "status": "published",
        "visibility": "public",
        "latest_version": "1.0.0",
        "install_targets": ["claude-code"],
        "installation": {"packages": [{"registry_type": "npm", "identifier": "acme", "version": "1.0.0"}]},
    }


@pytest.mark.parametrize("item_type", items.ITEM_TYPES)
def test_a_decorated_item_carries_no_scan_state(item_type: str) -> None:
    decorated = catalog.decorate(_row(item_type))
    assert _SCAN_KEYS.isdisjoint(decorated), _SCAN_KEYS & set(decorated)


@pytest.mark.parametrize("item_type", items.ITEM_TYPES)
def test_the_browse_response_model_accepts_an_item_with_no_security_block(item_type: str) -> None:
    """`security` used to be a required field of `ListingSummary`; removing it
    from `decorate` without the schema would fail every browse response."""
    card = ListingSummary.model_validate(catalog.decorate(_row(item_type)))
    page = ListingPage(items=[card], page=1, page_size=24, has_more=False, sort="recommended")
    dumped = page.model_dump()["items"][0]
    assert _SCAN_KEYS.isdisjoint(dumped)


def test_the_detail_carries_no_scan_state_and_keeps_install_warnings() -> None:
    """The install dialog reads `install_configs` from the detail, so the
    builder's warnings travel there - with nothing about a scan in them."""

    class Db:
        async def select(self, table: str, filters: Any = None, **kwargs: Any) -> list[dict[str, Any]]:
            if table == "mcp_listings":
                return [{**_row("mcp_server"), "installation": {
                    "packages": [{"registry_type": "npm", "identifier": "acme"}]}}]
            if table == "mcp_listing_versions":
                assert kwargs.get("columns") == catalog.VERSION_COLUMNS, "no select *"
                return [{"id": "v1", "listing_id": "x", "version": "1.0.0", "first_seen_at": "2026-09-29"}]
            return []

        async def rpc(self, *args: Any, **kwargs: Any) -> None:
            return None

    import asyncio

    detail = asyncio.run(catalog.get_listing(Db(), slug="a-mcp_server"))  # type: ignore[arg-type]
    assert detail is not None
    assert _SCAN_KEYS.isdisjoint(detail)
    for version in detail["versions"]:
        assert _SCAN_KEYS.isdisjoint(version)
    warnings = detail["install_configs"]["claude-code"]["warnings"]
    assert any("no pinned version" in w for w in warnings)
    assert not any("scan" in w.lower() or "grade" in w.lower() for w in warnings)
