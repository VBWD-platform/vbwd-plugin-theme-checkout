"""S152-07c — the SPA's structural CSS for everything theme_checkout renders.

S152-06c rules (theme ``tests/css_inventory`` helpers): every class a theme_checkout
template or runtime uses that a mirrored Vue component styles has a ported rule,
and no rule is invented. S152-06d colour tokens (theme ``tests/colour_tokens``): a
literal colour appears only as the fallback of a ``var(--vbwd-…, <literal>)`` token;
every SPA colour of a used rule is ported with its exact literal (minus the
justified :data:`EXCLUDED_DECLARATIONS`); every ``--vbwd-checkout-*`` token is
documented in the theme guide. The SPA-comparing half skips without fe-user.

The checkout-wide rules (``.card``, ``.btn``, ``.public-checkout``, the states and
the spinner) live here, not in a selling adapter: theme_booking's pay page reuses
them (it loads after theme_checkout, a declared dependency).
"""
import re
from pathlib import Path

import pytest

from plugins.theme.theme.theme_registry import TOKEN_NAME_PATTERN
from plugins.theme.tests.colour_tokens import (
    adapter_token_fallbacks,
    documented_colour_tokens,
    token_fallback_mismatches,
    unported_spa_colours,
)
from plugins.theme.tests.css_inventory import (
    CLASS_ATTRIBUTE,
    hard_coded_colours,
    is_used,
    rule_classes,
    template_class_usage,
    vue_style_text,
)
from plugins.theme_checkout.theme_checkout.confirmation import STATUS_COPY
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    BUILT_IN_FLOWS,
)
from plugins.theme_checkout.theme_checkout.plugin_paths import (
    STYLESHEETS_DIRECTORY,
    TEMPLATES_DIRECTORY,
)

BACKEND_ROOT = Path(__file__).resolve().parents[4]
FE_USER_ROOT = BACKEND_ROOT.parent / "vbwd-fe-user"
FE_USER_PLUGINS = FE_USER_ROOT / "plugins"
FE_USER_COMPONENTS = FE_USER_ROOT / "vue" / "src" / "components"
CHECKOUT_WIDGETS = FE_USER_PLUGINS / "checkout" / "components" / "widgets"
FE_CORE_COMPONENTS = FE_USER_ROOT / "vbwd-fe-core" / "src" / "components"
SOURCE_STYLE_FILES = (
    FE_USER_COMPONENTS / "checkout" / "EmailBlock.vue",
    FE_USER_COMPONENTS / "checkout" / "BillingAddressBlock.vue",
    FE_USER_COMPONENTS / "checkout" / "PaymentMethodsBlock.vue",
    FE_USER_COMPONENTS / "checkout" / "TermsCheckbox.vue",
    FE_CORE_COMPONENTS / "ui" / "CouponInput.vue",
    FE_USER_COMPONENTS / "PriceDisplay.vue",
    FE_USER_PLUGINS / "checkout" / "PublicCheckoutView.vue",
    FE_USER_PLUGINS / "checkout" / "CheckoutConfirmationView.vue",
    CHECKOUT_WIDGETS / "TokenBundleCollection.vue",
    FE_USER_PLUGINS / "stripe-payment" / "StripeSuccessView.vue",
)
# SPA colour declarations deliberately NOT ported (each with its reason).
EXCLUDED_DECLARATIONS = {
    "TermsCheckbox.vue | .popup-body.loading | color: #666": (
        "the theme renders the terms with the island (no extra round trip), so the "
        "popup never shows a loading state and no template uses `.loading`"
    ),
}
ADAPTER = "checkout"

# checkout_confirmation.html.j2 renders ``status-badge {{ confirmation.status }}``
# (CheckoutConfirmationView.vue ``:class="status"``): every status it has copy for.
CONFIRMATION_STATUS_CLASSES = set(STATUS_COPY)
# checkout_runtime.js sets ``'strength-bar ' + state.strength`` (EmailBlock's meter).
RUNTIME_STRENGTH_CLASSES = {"weak", "medium", "strong"}
# ... and toggles ``'selected'`` on the chosen payment method.
RUNTIME_TOGGLED_CLASSES = RUNTIME_STRENGTH_CLASSES | {"selected"}
RUNTIME_SCRIPT = TEMPLATES_DIRECTORY / "checkout" / "partials" / "checkout_runtime.js"
PAYMENT_TEMPLATES_DIRECTORY = TEMPLATES_DIRECTORY / "payment"
PROVIDER_EXPRESSION = re.compile(r"\{\{\s*provider\s*\}\}")
JINJA_MARKUP = re.compile(r"\{[{%].*?[}%]\}")

needs_spa_checkouts = pytest.mark.skipif(
    not FE_USER_PLUGINS.is_dir(),
    reason="the fe-user checkout is not next to vbwd-backend",
)


def _ported_css():
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(STYLESHEETS_DIRECTORY.rglob("*.css"))
    )


def _payment_page_classes():
    """``{{ provider }}-success`` etc. with each built-in flow's provider filled in."""
    classes = set()
    for template in PAYMENT_TEMPLATES_DIRECTORY.glob("*.j2"):
        source = template.read_text(encoding="utf-8")
        for descriptor in BUILT_IN_FLOWS:
            filled = PROVIDER_EXPRESSION.sub(descriptor.provider, source)
            for attribute in CLASS_ATTRIBUTE.findall(filled):
                classes.update(JINJA_MARKUP.sub(" ", attribute).split())
    return classes


def _used_classes():
    static_classes, prefixes = template_class_usage(TEMPLATES_DIRECTORY.rglob("*.j2"))
    static_classes |= _payment_page_classes()
    static_classes |= CONFIRMATION_STATUS_CLASSES
    static_classes |= RUNTIME_TOGGLED_CLASSES
    return static_classes, prefixes


def _used_styled_classes():
    static_classes, prefixes = _used_classes()
    source_classes = set()
    for source in SOURCE_STYLE_FILES:
        source_classes |= rule_classes(
            vue_style_text(source.read_text(encoding="utf-8"))
        )
    return {name for name in source_classes if is_used(name, static_classes, prefixes)}


def test_the_runtime_sets_the_classes_the_test_counts_as_used():
    runtime = RUNTIME_SCRIPT.read_text(encoding="utf-8")

    assert "'strength-bar ' + state.strength" in runtime
    for class_name in RUNTIME_TOGGLED_CLASSES:
        assert f"'{class_name}'" in runtime, class_name


def test_the_payment_pages_are_counted_per_provider():
    classes = _payment_page_classes()

    assert {"stripe-success", "paypal-success", "stripe-payment"} <= classes


@needs_spa_checkouts
def test_all_source_style_files_exist():
    assert [str(path) for path in SOURCE_STYLE_FILES if not path.is_file()] == []


@needs_spa_checkouts
def test_every_used_styled_class_has_a_ported_rule():
    assert _used_styled_classes() - rule_classes(_ported_css()) == set()


@needs_spa_checkouts
def test_every_ported_class_is_used_and_styled_in_the_spa():
    assert rule_classes(_ported_css()) - _used_styled_classes() == set()


def test_the_ported_css_styles_the_checkout_pages():
    ported = rule_classes(_ported_css())

    for class_name in (
        "public-checkout",
        "card",
        "btn",
        "spinner",
        "email-block",
        "billing-address-block",
        "payment-methods-block",
        "method-option",
        "terms-checkbox",
        "popup-overlay",
        "vbwd-coupon",
        "order-total",
        "checkout-confirmation",
        "confirmation-banner",
        "line-items-table",
        "token-bundle-card",
        "stripe-success",
    ):
        assert class_name in ported, class_name


def test_the_ported_css_carries_no_hard_coded_colour():
    assert hard_coded_colours(_ported_css()) == []


@needs_spa_checkouts
def test_every_spa_colour_of_a_used_rule_is_ported_with_its_literal():
    unported = unported_spa_colours(
        SOURCE_STYLE_FILES, _ported_css(), _used_styled_classes()
    )

    assert sorted(set(unported) - set(EXCLUDED_DECLARATIONS)) == []


@needs_spa_checkouts
def test_every_declaration_exclusion_is_still_an_unported_spa_colour():
    unported = unported_spa_colours(
        SOURCE_STYLE_FILES, _ported_css(), _used_styled_classes()
    )

    assert set(EXCLUDED_DECLARATIONS) <= set(unported)


@needs_spa_checkouts
def test_every_checkout_token_fallback_is_the_spa_literal():
    assert token_fallback_mismatches(SOURCE_STYLE_FILES, _ported_css(), ADAPTER) == []


def test_every_checkout_token_is_documented_with_its_default_and_vice_versa():
    used = {
        token: sorted(fallbacks)
        for token, fallbacks in adapter_token_fallbacks(_ported_css(), ADAPTER).items()
    }
    documented = {
        token: [default] for token, default in documented_colour_tokens(ADAPTER).items()
    }

    assert used and used == documented


def test_every_checkout_token_is_a_tokens_json_name():
    tokens = adapter_token_fallbacks(_ported_css(), ADAPTER)

    assert [name for name in tokens if not TOKEN_NAME_PATTERN.match(name)] == []
