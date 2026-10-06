"""S152-08 — the server twin of fe-user ``PriceDisplay.vue`` / ``resolvePriceDisplay``.

One home for every themed sellable price (shop cards, product detail, cart
lines, plan cards, the checkout summaries). The parity table is copied from
``vue/tests/unit/utils/priceDisplay.spec.ts`` (anonymous viewer: no account
type — themed pages render anonymously, D4). The markup is the component's:
``span.price-display > span.price-display__amount[data-testid=price-amount]``
plus the localized "netto price" tag.
"""
import pytest

from plugins.theme_checkout.tests.unit.template_harness import render, theme_plugin
from plugins.theme_checkout.theme_checkout.price_display import (
    PriceDisplayView,
    price_display_view,
    resolve_price_display,
)

MACRO_TEST_TEMPLATE = "fake/price_display.html.j2"


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


@pytest.mark.parametrize(
    "effective_mode, global_mode, expected_amount, expected_tag",
    [
        ("netto", "brutto", 100, True),
        ("brutto", "brutto", 119, False),
        ("netto", "netto", 100, False),
        (None, "netto", 100, False),
        (None, None, 119, False),
        ("brutto", "netto", 119, False),
    ],
)
def test_resolution_matches_the_spa_parity_table(
    effective_mode, global_mode, expected_amount, expected_tag
):
    assert resolve_price_display(100, 119, effective_mode, global_mode) == (
        expected_amount,
        expected_tag,
    )


def test_the_view_formats_the_chosen_side_in_its_currency():
    assert price_display_view("100", "119.5", "EUR", "netto", "brutto") == (
        PriceDisplayView(label="€100.00", show_netto_tag=True)
    )
    assert price_display_view(10, 10, None) == PriceDisplayView("€10.00", False)


def test_unparsable_amounts_render_zero_like_number_nan_guard():
    assert price_display_view(None, "abc", "USD").label == "$0.00"


def _render_macro(price):
    return render(theme_plugin(), MACRO_TEST_TEMPLATE, {"price": price})


def test_the_macro_renders_the_component_markup():
    html = _render_macro(PriceDisplayView("€100.00", True))

    assert html == (
        '<span class="price-display"><span class="price-display__amount" '
        'data-testid="price-amount">€100.00</span><span class="price-display__netto-tag" '
        'data-testid="price-netto-tag">netto price</span></span>'
    )


def test_the_macro_omits_the_tag_on_the_brutto_side():
    html = _render_macro(PriceDisplayView("€119.00", False))

    assert "price-display__netto-tag" not in html
