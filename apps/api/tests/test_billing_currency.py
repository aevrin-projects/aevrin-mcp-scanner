from aevrin_api.routers.billing import _CURRENCY, _PRICE_CENTS, _byok_addon_cents


def test_public_usd_prices_match_checkout_minor_units() -> None:
    assert _CURRENCY == "USD"
    assert _PRICE_CENTS == {
        ("hobby", "monthly"): 900,
        ("hobby", "annual"): 8_400,
        ("pro", "monthly"): 2_900,
        ("pro", "annual"): 28_800,
        ("team", "monthly"): 3_500,
        ("team", "annual"): 33_600,
    }


def test_byok_addon_is_flat_three_dollars_per_month() -> None:
    assert _byok_addon_cents("monthly") == 300
    assert _byok_addon_cents("annual") == 3_600
