"""How the marketplace decides what "Recommended" means.

Deterministic arithmetic over signals we already hold. No model, no learned
weights, nothing that cannot be explained to the publisher whose listing
ranked third.

The one rule this exists to enforce: popularity is not security. Stars are a
measure of how many people liked a README, and a server with twenty-five
thousand of them can still ship a command-injection hole. Security is
therefore the single heaviest component, and -- more importantly -- the two
are reported separately everywhere they are shown, so a reader never has to
reverse-engineer which one moved the number.

Weights live here as named constants, in one dictionary, because the brief
they answer to is "the exact weights should be easy to change".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Component weights, summing to 100. Changing the marketplace's priorities
# means editing this dictionary and nothing else.
WEIGHTS: dict[str, int] = {
    "security": 45,
    "popularity": 20,
    "maintenance": 15,
    "community": 10,
    "documentation": 10,
}

# A grade's contribution to the security component, 0-100.
#
# Unscanned scores 0, not "average". The alternative -- treating no evidence
# as a middling result -- would let a server rank above a scanned C simply by
# never having been examined, which is an incentive pointing the wrong way.
_GRADE_POINTS: dict[str, float] = {"A": 100.0, "B": 78.0, "C": 45.0, "D": 8.0}

# Stars at which the popularity component saturates. Logarithmic below it, so
# the gap between 10 and 100 stars counts for more than the gap between 10,000
# and 100,000 -- which matches how much either actually tells you.
_STAR_SATURATION = 20_000


@dataclass(frozen=True)
class RankingBreakdown:
    """The score, and every component that produced it.

    Returned alongside the number rather than derived later, so the detail
    page can show its working. "Recommended" that cannot be interrogated is
    just an editorial opinion with a percentage sign on it.
    """

    total: float
    components: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 2),
            "weights": dict(WEIGHTS),
            "components": {k: round(v, 1) for k, v in self.components.items()},
        }


def _security_points(grade: str | None, coverage_complete: bool | None) -> float:
    if grade not in _GRADE_POINTS:
        return 0.0
    points = _GRADE_POINTS[grade]
    # A grade earned under partial coverage is a weaker claim than the same
    # grade earned under full coverage, and ranking should say so.
    if coverage_complete is False:
        points *= 0.6
    return points


def _popularity_points(stars: int | None, downloads: int | None) -> float:
    """Stars and downloads, each on its own log curve, best signal wins.

    Not summed: a package with a million downloads and no stars is exactly as
    popular as one with a million downloads, and adding the two would reward
    breadth of *signal availability* rather than of use.
    """
    scores = []
    if stars is not None and stars > 0:
        scores.append(min(1.0, math.log10(stars + 1) / math.log10(_STAR_SATURATION)) * 100)
    if downloads is not None and downloads > 0:
        scores.append(min(1.0, math.log10(downloads + 1) / math.log10(1_000_000)) * 100)
    return max(scores) if scores else 0.0


def _maintenance_points(last_commit: datetime | None, latest_release: str | None) -> float:
    """How recently anyone touched it.

    Null is 0, not a penalty-free pass: "we could not tell when this was last
    maintained" is a genuinely worse position for a prospective user than
    "maintained last week", and the ranking should reflect that without
    pretending to know it is abandoned.
    """
    if last_commit is None:
        return 0.0
    days = (datetime.now(UTC) - last_commit).days
    if days <= 30:
        points = 100.0
    elif days <= 90:
        points = 80.0
    elif days <= 180:
        points = 60.0
    elif days <= 365:
        points = 35.0
    elif days <= 730:
        points = 15.0
    else:
        points = 5.0
    # A tagged release is evidence of deliberate maintenance rather than
    # incidental commits.
    if latest_release:
        points = min(100.0, points + 8.0)
    return points


def _community_points(forks: int | None, favorites: int) -> float:
    scores = []
    if forks is not None and forks > 0:
        scores.append(min(1.0, math.log10(forks + 1) / math.log10(2_000)) * 100)
    if favorites > 0:
        scores.append(min(1.0, math.log10(favorites + 1) / math.log10(500)) * 100)
    return max(scores) if scores else 0.0


def _documentation_points(listing: dict[str, Any]) -> float:
    """Presence of the things a person needs before installing.

    Crude on purpose: this measures whether documentation exists, not whether
    it is any good. Judging quality would require reading it, and a scoring
    function that quietly rates prose is a scoring function nobody can audit.
    """
    points = 0.0
    description = (listing.get("description") or "").strip()
    if len(description) >= 40:
        points += 30.0
    elif description:
        points += 10.0
    if listing.get("readme"):
        points += 30.0
    if listing.get("homepage_url"):
        points += 15.0
    if listing.get("repository_url"):
        points += 15.0
    if listing.get("license"):
        points += 10.0
    return min(100.0, points)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def compute_ranking(
    listing: dict[str, Any],
    *,
    trust_grade: str | None = None,
    coverage_complete: bool | None = None,
) -> RankingBreakdown:
    """The 0-100 "Recommended" score for one listing.

    Takes the grade as an argument rather than reading it off the listing,
    because a grade belongs to a *version* and the caller is the one that
    knows which version is current. Passing it in makes it impossible to rank
    a listing against a grade that has since been superseded.
    """
    components = {
        "security": _security_points(trust_grade, coverage_complete),
        "popularity": _popularity_points(
            listing.get("github_stars"),
            listing.get("npm_downloads_last_month") or listing.get("pypi_downloads_last_month"),
        ),
        "maintenance": _maintenance_points(
            _parse_timestamp(listing.get("github_last_commit_at")),
            listing.get("github_latest_release"),
        ),
        "community": _community_points(
            listing.get("github_forks"), int(listing.get("favorite_count") or 0)
        ),
        "documentation": _documentation_points(listing),
    }
    total = sum(components[name] * WEIGHTS[name] / 100 for name in WEIGHTS)
    return RankingBreakdown(total=total, components=components)


# Sort modes offered in the UI, mapped to PostgREST order clauses. Kept here
# beside the ranking so "Recommended" and its ordering cannot drift apart.
SORT_ORDERS: dict[str, str] = {
    "recommended": "ranking_score.desc,github_stars.desc.nullslast",
    # By the letter, then by the number behind it. `nullsfirst` on an
    # ascending grade puts A first and unscanned last: sorting on the letter
    # alone would rank D above A, since 'D' < 'A' is false but 'A' < 'D' is
    # true only in the direction nobody wants for "most secure first".
    "security": "current_trust_grade.asc.nullslast,current_security_score.desc.nullslast",
    "popular": "github_stars.desc.nullslast",
    "recently_updated": "registry_updated_at.desc.nullslast",
    "recently_added": "created_at.desc",
    "az": "title.asc",
}
DEFAULT_SORT = "recommended"
