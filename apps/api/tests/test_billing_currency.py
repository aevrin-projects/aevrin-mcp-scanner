from aevrin_api.routers.billing import _CURRENCY, _PRICE_PAISE


def test_public_usd_prices_match_checkout_minor_units() -> None:
    assert _CURRENCY == "USD"
    assert _PRICE_PAISE == {
        ("hobby", "monthly"): 1_900,
        ("hobby", "annual"): 18_000,
        ("team", "monthly"): 7_900,
        ("team", "annual"): 70_800,
    }
