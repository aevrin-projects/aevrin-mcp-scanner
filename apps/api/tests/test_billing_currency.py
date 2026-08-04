from aevrin_api.routers.billing import (
    _AUTOFIX_ADDON_BONUS_PRS,
    _AUTOFIX_ADDON_CENTS,
    _CURRENCY,
    _PRICE_CENTS,
    _byok_addon_cents,
)


def test_public_usd_prices_match_checkout_minor_units() -> None:
    assert _CURRENCY == "USD"
    assert _PRICE_CENTS == {
        ("hobby", "monthly"): 900,
        ("hobby", "annual"): 8_400,
        ("pro", "monthly"): 3_400,
        ("pro", "annual"): 34_800,
        ("team", "monthly"): 4_000,
        ("team", "annual"): 39_600,
    }


def test_byok_addon_is_flat_three_dollars_per_month() -> None:
    assert _byok_addon_cents("monthly") == 300
    assert _byok_addon_cents("annual") == 3_600


def test_autofix_addon_is_flat_four_dollars_for_ten_prs() -> None:
    assert _AUTOFIX_ADDON_CENTS == 400
    assert _AUTOFIX_ADDON_BONUS_PRS == 10
