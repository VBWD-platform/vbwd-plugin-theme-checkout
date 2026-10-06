"""S152-08 — each checkout source names the browser cart it checks out.

The SPA sources read their own store: subscription the fe-core cart
(``vbwd_cart``), shop its own (``vbwd_shop_cart``), dataset none. The themed
island posts the cart named by the matched source (``data-vbwd-cart``), and a
source without a cart gets no cart attribute at all.
"""
import re

import pytest

from plugins.theme_checkout.tests.unit.fakes import (
    FakeCheckoutApi,
    FakeThemeRequest,
    fake_source,
)
from plugins.theme_checkout.tests.unit.template_harness import (
    render,
    render_component,
    theme_plugin,
)
from plugins.theme_checkout.theme_checkout.checkout_page import CheckoutPage
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CORE_CART_KEY,
    CheckoutSourceRegistry,
)

SHOP_CART_KEY = "vbwd_shop_cart"
ISLAND_ROUTE_FIELDS = {
    "source": "fake",
    "tarif_plan_id": "",
    "cart_type": "",
    "is_cart": "",
}


@pytest.fixture(scope="module")
def plugin():
    return theme_plugin()


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


def _page_context(source):
    registry = CheckoutSourceRegistry()
    registry.register(source)
    page = CheckoutPage(registry, api_factory=FakeCheckoutApi().factory)
    return page.context(FakeThemeRequest({"source": "fake"}))


def _island_holder(html):
    return re.search(r'<div class="checkout-island"[^>]*>', html).group(0)


def test_a_source_checks_out_the_core_cart_by_default():
    assert fake_source()[0].cart_key == CORE_CART_KEY == "vbwd_cart"


def test_the_island_state_carries_the_matched_sources_cart_key():
    source = fake_source(cart_key=SHOP_CART_KEY)[0]

    assert _page_context(source)["cart_key"] == SHOP_CART_KEY


def test_a_source_without_a_cart_has_no_cart_key():
    assert _page_context(fake_source(cart_key=None)[0])["cart_key"] is None


def test_the_island_posts_the_cart_the_source_names(plugin):
    html = render(
        plugin,
        "checkout/page.html.j2",
        {
            "state": "island",
            "cart_write": None,
            "route_fields": ISLAND_ROUTE_FIELDS,
            "cart_key": SHOP_CART_KEY,
        },
    )

    assert 'data-vbwd-cart="vbwd_shop_cart"' in _island_holder(html)


def test_an_island_without_a_cart_key_posts_no_cart(plugin):
    html = render(
        plugin,
        "checkout/page.html.j2",
        {
            "state": "island",
            "cart_write": None,
            "route_fields": ISLAND_ROUTE_FIELDS,
            "cart_key": None,
        },
    )

    assert "data-vbwd-cart=" not in _island_holder(html)


def test_the_checkout_form_widget_posts_the_sources_cart(plugin):
    html = render_component(
        plugin,
        "checkout/components/checkout_form.html.j2",
        {
            "state": "island",
            "cart_write": None,
            "route_fields": ISLAND_ROUTE_FIELDS,
            "load_error": None,
            "cart_key": SHOP_CART_KEY,
        },
    )

    assert 'data-vbwd-cart="vbwd_shop_cart"' in _island_holder(html)
