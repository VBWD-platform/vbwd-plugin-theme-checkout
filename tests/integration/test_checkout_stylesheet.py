"""S152-07c — the served theme.css carries theme_checkout's ported checkout CSS.

On a real app in theme mode the order is: basic → theme_cms → theme_checkout
(contributed stylesheets in registration = dependency order) → the ``:root``
token block. The themed ``/checkout`` page and its island render classes the
served stylesheet styles (the walkthrough found them in browser defaults).
"""
import json
import re

from plugins.theme.tests.css_inventory import rule_classes

STYLESHEET_PATH = "/_render/_theme/public/theme.css"
RENDER = {"X-VBWD-Render": "1"}
FORM_FRAGMENT = "/_render/_fragment/checkout/form"
CART = [{"type": "PLAN", "id": "p-1", "name": "Pro Plan", "price": 20, "quantity": 1}]
CMS_RULE = ".cms-post-hero {"
CHECKOUT_RULE = ".public-checkout {"
ISLAND_STYLED_CLASSES = (
    "checkout-content",
    "email-block",
    "card",
    "order-total",
    "vbwd-coupon",
    "billing-address-block",
    "form-row",
    "terms-checkbox",
    "checkbox-label",
    "popup-overlay",
    "requirements",
    "checkout-actions",
    "btn",
    "pay-button",
)


def _has_class(html, class_name):
    return re.search(rf'class="(?:[^"]* )?{re.escape(class_name)}(?: [^"]*)?"', html)


def _served_css(client):
    response = client.get(STYLESHEET_PATH)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_theme_css_serves_the_checkout_rules_after_theme_cms_and_before_tokens(
    client,
):
    css_text = _served_css(client)

    cms_position = css_text.index(CMS_RULE)
    tokens_position = css_text.rindex(":root")
    for checkout_rule in (
        CHECKOUT_RULE,
        ".email-block {",
        ".payment-methods-block .method-option {",
        ".checkout-confirmation {",
        ".token-bundle-card {",
    ):
        assert cms_position < css_text.index(checkout_rule) < tokens_position


def test_the_checkout_page_renders_classes_the_served_css_styles(client):
    styled = rule_classes(_served_css(client))
    page = client.get("/checkout?source=fake", headers=RENDER).get_data(as_text=True)

    for class_name in ("public-checkout", "loading-state", "spinner"):
        assert _has_class(page, class_name), class_name
        assert class_name in styled, class_name


def test_the_checkout_island_renders_classes_the_served_css_styles(client):
    styled = rule_classes(_served_css(client))
    island = client.post(
        FORM_FRAGMENT, data={"source": "fake", "cart": json.dumps(CART)}
    ).get_data(as_text=True)

    for class_name in ISLAND_STYLED_CLASSES:
        assert _has_class(island, class_name), class_name
        assert class_name in styled, class_name
