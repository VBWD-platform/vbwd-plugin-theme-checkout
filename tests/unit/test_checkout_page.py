"""S152-07 B — the ``/checkout`` page's state (``PublicCheckoutView`` template branches).

The source match needs only the query (``?source`` / ``?tarif_plan_id``), so the
page decides server-side: no matching source → ``checkout-no-plan``; a 404
draft → ``checkout-draft-expired``; another draft failure → ``checkout-error``;
otherwise the island placeholder the runtime fills. A resolved draft hands its
cart to the runtime (``data-vbwd-cart-write``) and checks out as the
subscription cart, exactly like ``hydrateCartFromDraft`` + ``loadForContext``.
"""
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import (
    FakeCheckoutApi,
    FakeThemeRequest,
    ScriptedApi,
    fake_source,
)
from plugins.theme_checkout.theme_checkout import draft
from plugins.theme_checkout.theme_checkout.checkout_page import CheckoutPage
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutSourceRegistry,
)

DRAFT_PATH = "/api/v1/subscription/public/checkout-draft/tok"
DRAFT_LINE = {
    "item_type": "SUBSCRIPTION",
    "item_id": "p-1",
    "quantity": 1,
    "name": "Pro Plan",
    "unit_price": "19.00",
    "currency": None,
}


def _page(*sources, api=None):
    registry = CheckoutSourceRegistry()
    for source in sources:
        registry.register(source)
    api = api or FakeCheckoutApi(default_currency="USD")
    return CheckoutPage(registry, api_factory=api.factory)


def _subscription_cart_source():
    return fake_source(
        "subscription",
        matches=lambda context: context.cart_type == "subscription"
        or bool(context.plan_slug),
    )[0]


def test_no_matching_source_is_the_no_plan_state():
    assert _page().context(FakeThemeRequest({"source": "shop"})) == {
        "page_title": "Checkout",
        "state": "no_plan",
        "cart_write": None,
    }


def test_a_matching_source_renders_the_island_with_its_route_fields():
    context = _page(fake_source()[0]).context(FakeThemeRequest({"source": "fake"}))

    assert context["state"] == "island"
    assert context["route_fields"] == {
        "source": "fake",
        "tarif_plan_id": "",
        "cart_type": "",
        "is_cart": "",
    }
    assert context["cart_write"] is None


def test_an_expired_draft_is_the_draft_expired_state(monkeypatch):
    monkeypatch.setattr(
        draft,
        "call_api",
        ScriptedApi({("GET", DRAFT_PATH): ThemeApiError(404, "gone")}),
    )

    context = _page(_subscription_cart_source()).context(
        FakeThemeRequest({"draft": "tok"})
    )

    assert context["state"] == "draft_expired"
    assert context["cart_write"] is None


def test_a_resolved_draft_seeds_the_cart_and_checks_out_the_subscription_cart(
    monkeypatch,
):
    monkeypatch.setattr(
        draft,
        "call_api",
        ScriptedApi({("GET", DRAFT_PATH): {"line_items": [DRAFT_LINE]}}),
    )

    context = _page(_subscription_cart_source()).context(
        FakeThemeRequest({"draft": "tok", "source": "ignored"})
    )

    assert context["state"] == "island"
    assert context["route_fields"]["cart_type"] == "subscription"
    assert context["route_fields"]["is_cart"] == "1"
    assert context["cart_write"] == [
        {
            "type": "PLAN",
            "id": "p-1",
            "name": "Pro Plan",
            "price": 19.0,
            "metadata": {"plan_id": "p-1", "currency": "USD"},
            "quantity": 1,
        }
    ]


def test_a_resolved_draft_without_a_subscription_source_still_seeds_the_cart(
    monkeypatch,
):
    monkeypatch.setattr(
        draft,
        "call_api",
        ScriptedApi({("GET", DRAFT_PATH): {"line_items": [DRAFT_LINE]}}),
    )

    context = _page().context(FakeThemeRequest({"draft": "tok"}))

    assert context["state"] == "no_plan"
    assert len(context["cart_write"]) == 1


def test_another_draft_failure_is_the_checkout_error(monkeypatch):
    monkeypatch.setattr(
        draft,
        "call_api",
        ScriptedApi({("GET", DRAFT_PATH): ThemeApiError(500, "boom")}),
    )

    context = _page(_subscription_cart_source()).context(
        FakeThemeRequest({"draft": "tok"})
    )

    assert context["state"] == "error"
    assert context["load_error"] == "boom"
