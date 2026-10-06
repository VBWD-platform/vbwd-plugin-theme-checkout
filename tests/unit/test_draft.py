"""S152-07 B — bot checkout-draft hydration, the twin of fe-user ``checkout/draftCheckout.ts``.

``GET /api/v1/subscription/public/checkout-draft/<token>`` through ``call_api``:
404 (unknown / expired / redeemed) → :class:`DraftExpiredError`; any other
failure propagates. The draft's line items become the fe-core cart exactly as
``hydrateCartFromDraft`` builds it: cleared first, ``SUBSCRIPTION → PLAN``,
unknown item types skipped, one ``addItem`` per unit (so repeats merge into
``quantity``), prices parsed (invalid → 0), currency falling back to the default.
"""
import pytest

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest, ScriptedApi
from plugins.theme_checkout.theme_checkout import draft
from plugins.theme_checkout.theme_checkout.draft import (
    DraftExpiredError,
    cart_items_from_draft,
    resolve_draft_cart,
)

DRAFT_PATH = "/api/v1/subscription/public/checkout-draft/tok-1"


def _line(item_type="SUBSCRIPTION", item_id="p-1", quantity=1, **fields):
    return {
        "item_type": item_type,
        "item_id": item_id,
        "quantity": quantity,
        "name": fields.get("name", "Pro Plan"),
        "unit_price": fields.get("unit_price", "19.00"),
        "currency": fields.get("currency", "USD"),
    }


def test_a_subscription_line_becomes_a_plan_cart_item():
    assert cart_items_from_draft([_line()], default_currency="EUR") == [
        {
            "type": "PLAN",
            "id": "p-1",
            "name": "Pro Plan",
            "price": 19.0,
            "metadata": {"plan_id": "p-1", "currency": "USD"},
            "quantity": 1,
        }
    ]


def test_add_ons_and_bundles_keep_their_type_and_unknown_types_are_skipped():
    items = cart_items_from_draft(
        [
            _line("ADD_ON", "a-1"),
            _line("SHOP_ITEM", "s-1"),
            _line("TOKEN_BUNDLE", "b-1"),
        ],
        default_currency="EUR",
    )

    assert [(item["type"], item["id"]) for item in items] == [
        ("ADD_ON", "a-1"),
        ("TOKEN_BUNDLE", "b-1"),
    ]


def test_units_merge_into_quantity_like_repeated_add_item():
    items = cart_items_from_draft(
        [
            _line("TOKEN_BUNDLE", "b-1", quantity=2),
            _line("TOKEN_BUNDLE", "b-1", quantity=1),
        ],
        default_currency="EUR",
    )

    assert [(item["id"], item["quantity"]) for item in items] == [("b-1", 3)]


@pytest.mark.parametrize(
    "raw_quantity, expected", [(0, 1), (-3, 1), (2.9, 2), (None, 1)]
)
def test_quantity_is_at_least_one_and_truncated(raw_quantity, expected):
    items = cart_items_from_draft(
        [_line(quantity=raw_quantity)], default_currency="EUR"
    )

    assert items[0]["quantity"] == expected


@pytest.mark.parametrize("raw_price, expected", [(None, 0), ("abc", 0), ("7.5", 7.5)])
def test_price_is_parsed_and_invalid_is_zero(raw_price, expected):
    items = cart_items_from_draft([_line(unit_price=raw_price)], default_currency="EUR")

    assert items[0]["price"] == expected


def test_a_line_without_currency_takes_the_default_currency():
    items = cart_items_from_draft([_line(currency=None)], default_currency="EUR")

    assert items[0]["metadata"]["currency"] == "EUR"


def test_resolving_a_draft_reads_the_public_endpoint(monkeypatch):
    api = ScriptedApi({("GET", DRAFT_PATH): {"line_items": [_line()]}})
    monkeypatch.setattr(draft, "call_api", api)

    items = resolve_draft_cart(FakeThemeRequest(), "tok-1", default_currency="EUR")

    assert api.paths() == [("GET", DRAFT_PATH)]
    assert [item["id"] for item in items] == ["p-1"]


def test_a_404_draft_is_expired(monkeypatch):
    monkeypatch.setattr(
        draft,
        "call_api",
        ScriptedApi({("GET", DRAFT_PATH): ThemeApiError(404, "gone")}),
    )

    with pytest.raises(DraftExpiredError):
        resolve_draft_cart(FakeThemeRequest(), "tok-1", default_currency="EUR")


def test_another_draft_failure_propagates(monkeypatch):
    monkeypatch.setattr(
        draft,
        "call_api",
        ScriptedApi({("GET", DRAFT_PATH): ThemeApiError(500, "boom")}),
    )

    with pytest.raises(ThemeApiError):
        resolve_draft_cart(FakeThemeRequest(), "tok-1", default_currency="EUR")


def test_the_token_is_path_encoded(monkeypatch):
    api = ScriptedApi(
        {
            ("GET", "/api/v1/subscription/public/checkout-draft/a%2Fb%3F"): {
                "line_items": []
            }
        }
    )
    monkeypatch.setattr(draft, "call_api", api)

    assert resolve_draft_cart(FakeThemeRequest(), "a/b?", default_currency="EUR") == []
