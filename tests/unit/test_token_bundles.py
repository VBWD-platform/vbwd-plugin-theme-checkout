"""S152-07 B — the ``TokenBundleCollection`` CMS component (cards view).

``GET /api/v1/token-bundles``; ``config.bundle_ids`` filters; empty → the
``token-bundle-empty`` state; a failure → ``token-bundle-error``. Each card's
"Add to Cart" carries the fe-core cart item ``TokenBundleCollection.addToCart``
builds (net price, Price VO + currency in metadata); the runtime adds it and
goes to ``/checkout?source=subscription``. Prices follow ``resolvePriceDisplay``
(no account type is known server-side: the effective mode, else the global
mode, else brutto).
"""
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeCheckoutApi, FakeThemeRequest
from plugins.theme_checkout.theme_checkout.token_bundles import TokenBundleCollection

PRICE_VO = {"netto": 10.0, "brutto": 11.9, "currency": "EUR", "taxes": []}
BUNDLES = [
    {
        "id": "b-1",
        "name": "1000",
        "token_amount": 1000,
        "price": "10.00",
        "currency": None,
        "description": "Starter",
        "effective_display_mode": "brutto",
        "price_info": {"price": PRICE_VO},
    },
    {
        "id": "b-2",
        "name": "5000",
        "token_amount": 5000,
        "price": "40.00",
        "currency": "USD",
        "effective_display_mode": None,
        "prices_display_mode": "netto",
    },
]


def _context(config=None, **answers):
    api = FakeCheckoutApi(**{"token_bundles": {"bundles": BUNDLES}, **answers})
    component = TokenBundleCollection(api_factory=api.factory)
    return component.build_context(config or {}, {}, {}, FakeThemeRequest()), api


def test_cards_carry_the_amount_label_price_and_cart_item():
    context, api = _context({"heading": "Top up"})

    assert api.called("token_bundles") == [("token_bundles",)]
    assert context["heading"] == "Top up"
    assert context["state"] == "cards"
    first, second = context["bundles"]
    assert first["id"] == "b-1"
    assert first["token_amount"] == "1,000"
    assert first["price"] == "€11.90"
    assert first["description"] == "Starter"
    assert first["cart_item"] == {
        "type": "TOKEN_BUNDLE",
        "id": "b-1",
        "name": "1,000 Tokens",
        "price": 10.0,
        "metadata": {"token_amount": 1000, "currency": "EUR", "price_obj": PRICE_VO},
    }
    assert second["price"] == "$40.00"
    assert second["cart_item"]["price"] == 40.0
    assert second["cart_item"]["metadata"]["currency"] == "USD"


def test_bundle_ids_filter_the_collection():
    context, _api = _context({"bundle_ids": ["b-2"]})

    assert [bundle["id"] for bundle in context["bundles"]] == ["b-2"]


def test_no_bundles_is_the_empty_state():
    context, _api = _context({"bundle_ids": ["missing"]})

    assert context["state"] == "empty"


def test_a_failure_is_the_error_state():
    context, _api = _context(token_bundles=ThemeApiError(500, "down"))

    assert context["state"] == "error"
    assert context["bundles"] == []
