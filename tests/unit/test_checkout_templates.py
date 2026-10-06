"""S152-07 B — the themed checkout markup keeps the SPA's DOM contract (D2).

Same ``data-testid``s, classes and English copy as ``PublicCheckoutView``,
``EmailBlock``, ``BillingAddressBlock``, ``PaymentMethodsBlock``,
``TermsCheckbox``, fe-core ``CouponInput``, ``CheckoutConfirmationView`` and
``TokenBundleCollection``; plus the runtime hooks (``data-vbwd-cart``,
``data-vbwd-cart-write``, ``data-vbwd-session``, ``data-vbwd-logout``,
``data-vbwd-cart-add``) and the htmx wiring of the island.
"""
import json
import re
from decimal import Decimal

import pytest

from plugins.theme.theme.theme_api import ThemeApiError
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
from plugins.theme_checkout.theme_checkout.checkout_form import CheckoutForm
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutSourceRegistry,
    CheckoutSummary,
)

ISLAND = "checkout/_island.html.j2"


@pytest.fixture(scope="module")
def plugin():
    return theme_plugin()


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


def _island_context(summary=None, query=None, **answers):
    registry = CheckoutSourceRegistry()
    registry.register(fake_source(summary=summary)[0])
    api = FakeCheckoutApi(**answers)
    return CheckoutForm(registry, api_factory=api.factory).context(
        FakeThemeRequest({"source": "fake", **(query or {})})
    )


def _testid(html, testid):
    return re.search(rf'<[^>]*data-testid="{re.escape(testid)}"[^>]*>', html)


# ── /checkout page states ────────────────────────────────────────────────────


def test_no_plan_state_has_the_spa_copy_and_link(plugin):
    html = render(
        plugin, "checkout/page.html.j2", {"state": "no_plan", "cart_write": None}
    )

    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert re.search(r'data-testid="checkout-title">\s*Checkout\s*<', html)
    assert _testid(html, "checkout-no-plan")
    assert "No plan selected. Please choose a plan first." in html
    assert '<a href="/landing1" class="btn primary">Browse Plans</a>' in html
    assert "data-vbwd-cart-write" not in html


def test_draft_expired_state(plugin):
    html = render(
        plugin, "checkout/page.html.j2", {"state": "draft_expired", "cart_write": None}
    )

    assert _testid(html, "checkout-draft-expired")
    assert "This checkout link has expired or has already been used." in html
    assert not _testid(html, "order-summary")


def test_load_error_state_shows_the_message(plugin):
    html = render(
        plugin,
        "checkout/page.html.j2",
        {"state": "error", "load_error": "Plan <x>", "cart_write": None},
    )

    assert _testid(html, "checkout-error")
    assert "Plan &lt;x&gt;" in html
    assert ">Back to Plans</a>" in html


def test_island_placeholder_posts_the_cart_on_load_and_on_session_changes(plugin):
    html = render(
        plugin,
        "checkout/page.html.j2",
        {
            "state": "island",
            "route_fields": {
                "source": "fake",
                "tarif_plan_id": "",
                "cart_type": "",
                "is_cart": "",
            },
            "cart_key": "vbwd_cart",
            "cart_write": [
                {
                    "type": "PLAN",
                    "id": "p",
                    "name": "</script>",
                    "price": 1,
                    "quantity": 1,
                }
            ],
        },
    )

    island = re.search(r'<div class="checkout-island"[^>]*>', html).group(0)
    assert 'data-vbwd-cart="vbwd_cart"' in island
    assert 'hx-post="/_render/_fragment/checkout/form"' in island
    assert (
        'hx-trigger="load, vbwd:session-started from:body, vbwd:session-ended from:body"'
        in island
    )
    assert (
        json.loads(re.search(r"hx-vals='([^']*)'", island).group(1))["source"] == "fake"
    )
    assert _testid(html, "checkout-loading")
    directive = re.search(
        r'<script type="application/json" data-vbwd-cart-write="vbwd_cart">(.*?)</script>',
        html,
    )
    assert json.loads(directive.group(1))[0]["name"] == "</script>"
    assert "window.VbwdCheckout" in html


# ── the island ───────────────────────────────────────────────────────────────


def test_anonymous_island_keeps_the_spa_testids(plugin):
    html = render(plugin, ISLAND, _island_context())

    for testid in (
        "email-block",
        "email-input",
        "order-summary",
        "checkout-order-summary",
        "plan-name",
        "coupon-input",
        "coupon-apply",
        "order-total",
        "order-total-amount",
        "billing-address-block",
        "billing-first-name",
        "billing-last-name",
        "billing-company",
        "billing-street",
        "billing-city",
        "billing-zip",
        "billing-state",
        "billing-country",
        "payment-methods-block",
        "payment-method-stripe",
        "payment-method-stripe-description",
        "payment-method-invoice",
        "terms-checkbox",
        "terms-link",
        "terms-popup",
        "terms-content",
        "checkout-requirements",
        "confirm-checkout",
    ):
        assert _testid(html, testid), testid
    assert not _testid(html, "email-block-success")
    assert not _testid(html, "order-discount")


def test_island_copy_matches_the_spa(plugin):
    html = render(plugin, ISLAND, _island_context())

    assert "<h3>Customer Email</h3>" in html
    assert 'placeholder="Enter your email"' in html
    assert "<h2>Order Summary</h2>" in html
    assert re.search(r'data-testid="order-total-amount">Total: €10\.00</strong>', html)
    assert "<h3>Billing Address</h3>" in html
    assert '<label for="firstName">First Name *</label>' in html
    assert '<label for="street">Street Address *</label>' in html
    assert "<h3>Payment Method</h3>" in html
    assert ">Pay with Stripe</label>" in html
    assert "I agree to the" in html and ">Terms and Conditions</a>" in html
    assert "<strong>To complete checkout:</strong>" in html
    assert re.search(r'data-testid="confirm-checkout"[^>]*>Pay €10\.00</button>', html)
    assert '<a href="/landing1" class="btn secondary">Back to Plans</a>' in html


def test_island_htmx_wiring_and_hidden_state(plugin):
    html = render(plugin, ISLAND, _island_context())

    form = re.search(r"<form[^>]*>", html).group(0)
    assert "data-vbwd-checkout-form" in form and 'data-authenticated="0"' in form
    assert '<input type="hidden" name="source" value="fake">' in html
    assert '<input type="hidden" name="coupon_code" value="">' in html
    email_input = _testid(html, "email-input").group(0)
    assert 'hx-get="/_render/_fragment/checkout/email-check"' in email_input
    assert 'hx-trigger="input changed delay:500ms"' in email_input
    apply_button = _testid(html, "coupon-apply").group(0)
    assert (
        'name="coupon_action" value="apply"' in apply_button
        and "disabled" in apply_button
    )
    assert 'hx-target="#checkout-island"' in apply_button
    confirm = _testid(html, "confirm-checkout").group(0)
    assert 'hx-post="/_render/_fragment/checkout/submit"' in confirm
    assert 'hx-include="closest form"' in confirm and "disabled" in confirm


def test_auto_selected_method_is_checked_and_its_instructions_toggle(plugin):
    html = render(plugin, ISLAND, _island_context(query={"payment_method": "invoice"}))

    assert re.search(
        r'id="method-invoice" type="radio" name="payment_method" value="invoice" checked',
        html,
    )
    assert not re.search(r'value="stripe" checked', html)
    instructions = re.search(
        r'<div class="method-instructions" data-testid="payment-method-instructions"[^>]*>\s*<p>([^<]*)</p>',
        html,
    )
    assert instructions.group(1) == "Pay within 14 days"
    assert 'data-instructions="Pay within 14 days"' in html


def test_requirements_list_shows_only_the_missing_items(plugin):
    html = render(plugin, ISLAND, _island_context())

    assert re.search(
        r'<li data-requirement="signIn">Sign in or create account</li>', html
    )
    assert re.search(r'<li data-requirement="paymentMethod" hidden>', html)


def test_a_discount_shows_the_final_price_and_saved_amount(plugin):
    summary = CheckoutSummary(
        line_items=(),
        order_total=Decimal("8"),
        currency="EUR",
        discount_amount=Decimal("2"),
        applied_coupon_code="SUMMER2026",
    )

    html = render(plugin, ISLAND, _island_context(summary=summary))

    assert re.search(
        r'data-testid="order-total-amount">Final price with coupon: €8\.00<', html
    )
    assert re.search(r'data-testid="order-discount">You have saved: €2\.00<', html)
    assert "Coupon applied: SUMMER2026" in html
    assert _testid(html, "coupon-clear")
    assert not _testid(html, "coupon-input")
    assert '<input type="hidden" name="coupon_code" value="SUMMER2026">' in html


def test_a_coupon_error_is_shown(plugin):
    summary = CheckoutSummary(
        line_items=(),
        order_total=Decimal("10"),
        currency="EUR",
        coupon_error="Invalid coupon",
    )

    html = render(plugin, ISLAND, _island_context(summary=summary))

    assert re.search(r'data-testid="coupon-error">Invalid coupon</p>', html)


def test_a_free_order_activates_for_free_without_payment_or_billing(plugin):
    summary = CheckoutSummary(line_items=(), order_total=Decimal("0"), currency="EUR")

    html = render(plugin, ISLAND, _island_context(summary=summary))

    assert re.search(
        r'data-testid="confirm-checkout"[^>]*>Activate for Free</button>', html
    )
    assert not _testid(html, "payment-methods-block")
    assert not _testid(html, "billing-address-block")
    assert not _testid(html, "coupon-input")


def test_logged_in_buyer_sees_the_logged_in_state(plugin):
    profile = {
        "user": {"email": "b@example.com"},
        "details": {"first_name": "Ada", "last_name": "L"},
    }

    html = render(plugin, ISLAND, _island_context(profile=profile))

    assert _testid(html, "email-block-success") and _testid(html, "logged-in-state")
    assert re.search(
        r'Logged in as <strong data-testid="logged-in-name">Ada L</strong>, email '
        r'<span data-testid="logged-in-email">b@example\.com</span>',
        html,
    )
    assert re.search(
        r'data-testid="logout-button" data-vbwd-logout>Logout</button>', html
    )
    assert 'data-authenticated="1"' in html


def test_logged_in_buyer_without_a_name(plugin):
    html = render(
        plugin, ISLAND, _island_context(profile={"user": {"email": "b@example.com"}})
    )

    assert re.search(
        r'data-testid="logged-in-email">Logged in as b@example\.com</span>', html
    )


def test_payment_methods_error_and_empty_copy(plugin):
    failed = render(
        plugin, ISLAND, _island_context(payment_methods=ThemeApiError(500, "x"))
    )
    empty = render(plugin, ISLAND, _island_context(payment_methods={"methods": []}))

    assert re.search(
        r'data-testid="payment-methods-error">Failed to load payment methods</div>',
        failed,
    )
    assert '<div class="empty">No payment methods available</div>' in empty


def test_island_no_plan_and_error_states(plugin):
    assert _testid(render(plugin, ISLAND, {"state": "no_plan"}), "checkout-no-plan")
    error_html = render(plugin, ISLAND, {"state": "error", "load_error": "Nope"})
    assert _testid(error_html, "checkout-error") and "Nope" in error_html


# ── email block fragments ────────────────────────────────────────────────────


def test_new_user_form_keeps_the_email_block_testids_and_copy(plugin):
    html = render(
        plugin, "checkout/_email_auth.html.j2", {"state": "new_user", "email": "a@b.co"}
    )

    for testid in (
        "email-new-user",
        "password-input",
        "password-strength",
        "password-confirm-input",
        "password-mismatch",
        "signup-button",
    ):
        assert _testid(html, testid), testid
    assert "Create a password to continue" in html
    assert re.search(r'data-testid="signup-button"[^>]*disabled', html)
    assert 'hx-post="/_render/_fragment/checkout/register"' in html
    assert ">Sign Up &amp; Continue</button>" in html


def test_existing_user_form(plugin):
    html = render(
        plugin,
        "checkout/_email_auth.html.j2",
        {"state": "existing_user", "email": "a@b.co"},
    )

    for testid in (
        "email-existing-user",
        "login-hint",
        "password-input",
        "forgot-password-link",
        "login-button",
    ):
        assert _testid(html, testid), testid
    assert "Account exists. Enter password to login." in html
    assert 'hx-post="/_render/_fragment/checkout/login"' in html


def test_idle_email_check_renders_nothing(plugin):
    assert (
        render(
            plugin, "checkout/_email_auth.html.j2", {"state": "idle", "email": ""}
        ).strip()
        == ""
    )


def test_auth_result_session_directive_and_error(plugin):
    session = {"token": "t", "user_id": "u", "user_email": "a@b.co"}
    ok_html = render(plugin, "checkout/_auth_result.html.j2", {"session": session})
    error_html = render(
        plugin,
        "checkout/_auth_result.html.j2",
        {
            "session": None,
            "error_message": None,
            "error_key": "common.errors.loginFailedRetry",
        },
    )

    directive = re.search(
        r'<script type="application/json" data-vbwd-session>(.*?)</script>', ok_html
    )
    assert json.loads(directive.group(1)) == session
    assert "redirect" not in json.loads(directive.group(1))
    assert '<p class="error-message">Login failed. Please try again.</p>' in error_html


def test_submit_error_is_the_checkout_form_error(plugin):
    html = render(
        plugin,
        "checkout/_submit_result.html.j2",
        {"error_message": None, "error_key": "checkout.errors.noItemsSelected"},
    )

    assert re.search(
        r'data-testid="checkout-form-error" class="error-message">No items selected<',
        html,
    )
    assert (
        render(
            plugin,
            "checkout/_submit_result.html.j2",
            {"error_message": None, "error_key": None},
        ).strip()
        == ""
    )


# ── CMS widgets ──────────────────────────────────────────────────────────────


def test_confirmation_widget_pending_banner(plugin):
    html = render_component(
        plugin,
        "checkout/components/checkout_confirmation.html.j2",
        {
            "status": "pending",
            "title": "Payment Processing",
            "message": "Your payment is being processed. This may take a moment.",
            "invoice": None,
            "clear_shop_cart": False,
            "content_html": "",
            "sections": [],
        },
    )

    assert _testid(html, "checkout-confirmation")
    assert re.search(
        r'class="confirmation-banner confirmation-banner--pending" data-testid="confirmation-banner"',
        html,
    )
    assert "<h1>Payment Processing</h1>" in html
    assert not _testid(html, "invoice-details")
    assert "data-vbwd-cart-clear" not in html


def test_confirmation_widget_with_an_invoice(plugin):
    html = render_component(
        plugin,
        "checkout/components/checkout_confirmation.html.j2",
        {
            "status": "paid",
            "title": "Payment Successful",
            "message": "m",
            "invoice": {
                "number": "INV-1",
                "amount": "$9.00",
                "date": "1/2/2026, 1:02:03 PM",
                "payment_method": "stripe",
                "line_items": [
                    {
                        "description": "Pro",
                        "quantity": 1,
                        "unit_price": "$9.00",
                        "amount": "$9.00",
                    }
                ],
            },
            "clear_shop_cart": True,
            "content_html": "",
            "sections": [],
        },
    )

    assert _testid(html, "invoice-details") and _testid(html, "line-item-row")
    assert "<h2>Payment Details</h2>" in html and "INV-1" in html
    assert '<template data-vbwd-cart-clear="vbwd_shop_cart"></template>' in html


def test_confirmation_sections_render_as_cards_between_the_invoice_and_the_cms_content(
    plugin,
):
    """``<component :is v-for="plugin in confirmationPlugins" class="card">`` sits
    after the invoice card and before ``.cms-content``; each section's template
    reads ``section.context``. ``data-confirmation-section`` is additive (scopes
    the section's ported CSS; the SPA's scoped styles need no hook)."""
    html = render_component(
        plugin,
        "checkout/components/checkout_confirmation.html.j2",
        {
            "status": "paid",
            "title": "Payment Successful",
            "message": "m",
            "invoice": {
                "number": "INV-1",
                "amount": "",
                "date": "",
                "payment_method": "",
                "line_items": [],
            },
            "clear_shop_cart": True,
            "content_html": "<p>Thanks</p>",
            "sections": [
                {
                    "name": "first",
                    "template": "fake/confirmation_section.html.j2",
                    "context": {"title": "First <b>"},
                },
                {
                    "name": "booking",
                    "template": "fake/confirmation_section.html.j2",
                    "context": {"title": "Booking"},
                },
            ],
        },
    )

    first = html.index('<div class="card" data-confirmation-section="first">')
    second = html.index('<div class="card" data-confirmation-section="booking">')
    assert html.index('data-testid="invoice-details"') < first < second
    assert second < html.index('<div class="cms-content">')
    assert '<h2 class="fake-section">First &lt;b&gt;</h2>' in html
    assert '<h2 class="fake-section">Booking</h2>' in html


def test_confirmation_without_sections_renders_no_section_card(plugin):
    html = render_component(
        plugin,
        "checkout/components/checkout_confirmation.html.j2",
        {
            "status": "pending",
            "title": "t",
            "message": "m",
            "invoice": None,
            "clear_shop_cart": False,
            "content_html": "",
            "sections": [],
        },
    )

    assert "data-confirmation-section" not in html


def test_token_bundle_widget_cards_carry_the_cart_item(plugin):
    item = {
        "type": "TOKEN_BUNDLE",
        "id": "b-1",
        "name": "1,000 Tokens",
        "price": 10.0,
        "metadata": {},
    }
    html = render_component(
        plugin,
        "checkout/components/token_bundle_collection.html.j2",
        {
            "heading": "Top up",
            "state": "cards",
            "bundles": [
                {
                    "id": "b-1",
                    "token_amount": "1,000",
                    "price": "€11.90",
                    "description": "",
                    "cart_item": item,
                }
            ],
        },
    )

    assert _testid(html, "token-bundle-grid") and _testid(html, "token-bundle-card-b-1")
    assert '<div class="token-bundle-card__amount">1,000 Tokens</div>' in html
    button = _testid(html, "add-to-cart-b-1").group(0)
    assert (
        json.loads(re.search(r"data-vbwd-cart-add='([^']*)'", button).group(1)) == item
    )
    assert 'data-vbwd-navigate="/checkout?source=subscription"' in button
    assert ">Add to Cart</button>" in html


def test_token_bundle_widget_empty_and_error(plugin):
    empty = render_component(
        plugin,
        "checkout/components/token_bundle_collection.html.j2",
        {"heading": None, "state": "empty", "bundles": []},
    )
    failed = render_component(
        plugin,
        "checkout/components/token_bundle_collection.html.j2",
        {"heading": None, "state": "error", "bundles": []},
    )

    assert (
        _testid(empty, "token-bundle-empty")
        and "No token bundles available at this time." in empty
    )
    assert (
        _testid(failed, "token-bundle-error")
        and "Failed to load token bundles" in failed
    )


def test_checkout_form_widget_renders_the_page_body(plugin):
    html = render_component(
        plugin,
        "checkout/components/checkout_form.html.j2",
        {
            "state": "no_plan",
            "cart_write": None,
            "route_fields": None,
            "load_error": None,
        },
    )

    assert _testid(html, "checkout-no-plan")


def test_the_coupon_block_posts_to_the_island_that_includes_it(plugin):
    """S152-09: the booking pay island reuses the block with its own island."""
    applied = {"coupon": {"applied_code": "SAVE10", "error": None}}
    default = render(plugin, "checkout/_coupon.html.j2", applied)
    booking = render(
        plugin,
        "checkout/_coupon.html.j2",
        {
            **applied,
            "island_form_url": "/_render/_fragment/booking/pay-form",
            "island_target": "#booking-pay-island",
        },
    )

    assert 'hx-post="/_render/_fragment/checkout/form"' in default
    assert 'hx-target="#checkout-island"' in default
    assert 'hx-post="/_render/_fragment/booking/pay-form"' in booking
    assert 'hx-target="#booking-pay-island"' in booking
    assert "/checkout/form" not in booking
