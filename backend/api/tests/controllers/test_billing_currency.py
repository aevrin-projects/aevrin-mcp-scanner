"""Prices, and which currency a caller is charged in.

The currency decision is the security-sensitive part: Pro is $34 against
Rs 1,499, so a client able to name its own currency would be choosing to pay
roughly half price.

`resolve_currency` takes the caller's country rather than a Request, so these
assert the rule directly instead of mocking a geolocation lookup to reach it.
The route is what turns a request into a country.
"""

import pytest

from aevrin_api.controllers.billing_controller import (
    _AUTOFIX_ADDON_BONUS_PRS,
    _AUTOFIX_ADDON_CENTS,
    _AUTOFIX_ADDON_PAISE_INR,
    _DEFAULT_CURRENCY,
    _PRICE_CENTS,
    _PRICE_PAISE_INR,
    _autofix_addon_amount,
    _byok_addon_amount,
    _byok_addon_cents,
    _tier_amount,
    resolve_currency,
)


def test_public_usd_prices_match_checkout_minor_units() -> None:
    assert _DEFAULT_CURRENCY == "USD"
    assert _PRICE_CENTS == {
        ("hobby", "monthly"): 900,
        ("hobby", "annual"): 8_400,
        ("pro", "monthly"): 3_400,
        ("pro", "annual"): 34_800,
        ("team", "monthly"): 4_000,
        ("team", "annual"): 39_600,
    }


def test_public_inr_prices_match_checkout_minor_units() -> None:
    """Paise, not rupees. A rupee value here would undercharge by 100x."""
    assert _PRICE_PAISE_INR == {
        ("hobby", "monthly"): 49_900,
        ("hobby", "annual"): 479_900,
        ("pro", "monthly"): 149_900,
        ("pro", "annual"): 1_499_900,
        ("team", "monthly"): 199_900,
        ("team", "annual"): 1_999_900,
    }


def test_every_tier_and_cycle_is_priced_in_both_currencies() -> None:
    """A missing INR entry would raise KeyError inside checkout, which the
    user would see as a failed payment attempt."""
    assert set(_PRICE_PAISE_INR) == set(_PRICE_CENTS)


def test_annual_is_cheaper_than_twelve_months_in_both_currencies() -> None:
    for tier in ("hobby", "pro", "team"):
        for table in (_PRICE_CENTS, _PRICE_PAISE_INR):
            assert table[(tier, "annual")] < table[(tier, "monthly")] * 12


def test_byok_addon_is_flat_three_dollars_per_month() -> None:
    assert _byok_addon_cents("monthly") == 300
    assert _byok_addon_cents("annual") == 3_600


def test_autofix_addon_is_flat_four_dollars_for_ten_prs() -> None:
    assert _AUTOFIX_ADDON_CENTS == 400
    assert _AUTOFIX_ADDON_BONUS_PRS == 10


def test_addon_amounts_follow_the_resolved_currency() -> None:
    assert _byok_addon_amount("monthly", "USD") == 300
    assert _byok_addon_amount("annual", "USD") == 3_600
    assert _byok_addon_amount("monthly", "INR") == 19_900
    assert _byok_addon_amount("annual", "INR") == 238_800
    assert _autofix_addon_amount("USD") == 400
    assert _autofix_addon_amount("INR") == _AUTOFIX_ADDON_PAISE_INR


def test_tier_amount_selects_the_right_table() -> None:
    assert _tier_amount("pro", "monthly", "USD") == 3_400
    assert _tier_amount("pro", "monthly", "INR") == 149_900


@pytest.mark.parametrize(
    ("country", "expected"),
    [
        ("IN", "INR"),
        ("US", "USD"),
        ("GB", "USD"),
        ("AE", "USD"),
        (None, "USD"),
    ],
)
def test_currency_follows_the_detected_country(country, expected) -> None:
    assert resolve_currency(country) == expected


def test_an_unknown_country_resolves_to_the_more_expensive_currency() -> None:
    """The failure direction is the whole point: if a failed lookup produced
    INR, breaking the lookup would be a 50% discount anyone could trigger."""
    assert resolve_currency(None) == "USD"
    # And USD really is the dearer of the two at a realistic exchange rate.
    assert (
        _tier_amount("pro", "monthly", "USD") / 100 * 88
        > _tier_amount("pro", "monthly", "INR") / 100
    )


def test_anyone_may_choose_to_pay_in_usd() -> None:
    """The dearer currency is always allowed: nobody gains by it, and it
    serves an Indian customer who would rather be billed in dollars."""
    assert resolve_currency("IN", "USD") == "USD"


def test_inr_cannot_be_requested_from_outside_india() -> None:
    """The whole reason currency is server-derived. Pro is $34 against
    Rs 1,499, so honouring this would be handing out a half-price
    subscription to anyone who flips a toggle."""
    assert resolve_currency("US", "INR") == "USD"


def test_an_indian_caller_keeps_inr_when_requesting_it() -> None:
    assert resolve_currency("IN", "INR") == "INR"


def test_a_nonsense_currency_falls_back_to_detection() -> None:
    assert resolve_currency("IN", "XYZ") == "INR"
    assert resolve_currency(None, "'; DROP TABLE--") == "USD"
