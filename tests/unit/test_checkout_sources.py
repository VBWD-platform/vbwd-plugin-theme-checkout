"""S152-07 B — ``CheckoutSourceRegistry``, the twin of fe-user
``vue/src/registries/checkoutSourceRegistry.ts``.

Same semantics: ``register`` keyed by id (a re-registration replaces),
``find(context)`` = the highest-priority source whose ``matches`` is true (ties:
the first registered), ``get(id)``. The route context is read from the same
query parameters ``PublicCheckoutView`` reads (``source``, ``tarif_plan_id``,
``draft``).
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.theme_checkout.tests.unit.fakes import fake_source
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutRouteContext,
    CheckoutSourceRegistry,
    resolve_checkout_source_registry,
)


def test_find_returns_none_without_a_matching_source():
    registry = CheckoutSourceRegistry()
    registry.register(fake_source()[0])

    assert registry.find(CheckoutRouteContext(source="shop")) is None


def test_find_returns_the_matching_source():
    registry = CheckoutSourceRegistry()
    source, _received = fake_source()
    registry.register(source)

    assert registry.find(CheckoutRouteContext(source="fake")) is source


def _always(context):
    return True


def test_the_highest_priority_match_wins_and_ties_keep_the_first():
    registry = CheckoutSourceRegistry()
    always = _always
    first, _ = fake_source("first", matches=always)
    second, _ = fake_source("second", matches=always)
    higher, _ = fake_source("higher", matches=always, priority=5)
    registry.register(first)
    registry.register(second)

    assert registry.find(CheckoutRouteContext()) is first

    registry.register(higher)

    assert registry.find(CheckoutRouteContext()) is higher


def test_registering_the_same_id_replaces_it():
    registry = CheckoutSourceRegistry()
    original, _ = fake_source("subscription")
    replacement, _ = fake_source("subscription")
    registry.register(original)
    registry.register(replacement)

    assert registry.get("subscription") is replacement
    assert registry.get("unknown") is None


def test_route_context_reads_the_public_checkout_query():
    context = CheckoutRouteContext.from_query(
        {"source": "shop", "tarif_plan_id": "pro", "draft": "tok"}
    )

    assert context == CheckoutRouteContext(source="shop", plan_slug="pro")


def test_route_context_treats_blank_values_as_absent():
    assert (
        CheckoutRouteContext.from_query({"source": "", "tarif_plan_id": ""})
        == CheckoutRouteContext()
    )


def test_the_draft_context_is_the_subscription_cart():
    """``PublicCheckoutView`` loads a draft as ``{cartType: 'subscription', isCart: true}``."""
    assert CheckoutRouteContext.for_draft() == CheckoutRouteContext(
        cart_type="subscription", is_cart=True
    )


def test_resolve_reads_the_running_theme_checkout_plugin():
    registry = CheckoutSourceRegistry()
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(
        get_plugin=lambda name: SimpleNamespace(source_registry=registry)
        if name == "theme_checkout"
        else None
    )

    with app.app_context():
        assert resolve_checkout_source_registry() is registry


def test_resolve_raises_when_theme_checkout_is_absent():
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(get_plugin=lambda name: None)

    with app.app_context(), pytest.raises(LookupError):
        resolve_checkout_source_registry()
