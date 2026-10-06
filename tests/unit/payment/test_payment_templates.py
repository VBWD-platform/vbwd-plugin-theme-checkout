"""S152-07 C — the ``/pay/*`` markup keeps the SPA views' classes and copy (D2).

``StripePaymentView`` / ``PayPalPaymentView`` (``<p>-payment__loading|error|no-invoice``),
``StripeSuccessView`` (``__verifying|done|error``), ``PayPalSuccessView``
(``__verifying|confirmed|error``) and the cancel views; the auth-required shell
(``data-auth="pending"`` + ``data-vbwd-auth-required``, content hidden until the
session is confirmed) and the htmx chain of the create / poll / capture steps.
"""
import json
import re

import pytest
from flask import Flask

from plugins.theme import ThemePlugin
from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest
from plugins.theme_checkout.tests.unit.payment.fakes import FakeProviderApi
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    PAYPAL_FLOW,
    STRIPE_FLOW,
)
from plugins.theme_checkout.theme_checkout.payment.flow_pages import PaymentFlowPages
from plugins.theme_checkout.theme_checkout.plugin_paths import (
    TEMPLATES_DIRECTORY,
    TRANSLATIONS_DIRECTORY,
)


@pytest.fixture(scope="module")
def plugin():
    theme_plugin = ThemePlugin()
    theme_plugin.on_enable()
    theme_plugin.theme_registry.add_contributed_template_path(TEMPLATES_DIRECTORY)
    theme_plugin.theme_registry.add_contributed_translation_path(TRANSLATIONS_DIRECTORY)
    return theme_plugin


@pytest.fixture(autouse=True)
def isolated_var_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))


def _render(plugin, template, context):
    app = Flask(__name__)
    app.testing = True
    with app.app_context():
        return plugin.renderer.render(
            template, {"language": "en", "default_language": "en", **context}
        )


def _pages(descriptor=STRIPE_FLOW, **answers):
    return PaymentFlowPages(descriptor, api_factory=FakeProviderApi(**answers).factory)


def _hx_vals(element):
    return json.loads(re.search(r"hx-vals='([^']*)'", element).group(1))


def test_pay_page_is_an_auth_required_shell_that_creates_the_session(plugin):
    html = _render(
        plugin,
        "payment/pay.html.j2",
        _pages().pay_context(FakeThemeRequest({"invoice": "inv-1"})),
    )

    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert re.search(r'<body data-auth="pending" data-vbwd-auth-required>', html)
    assert '<div class="vbwd-private-chrome">' in html
    loading = re.search(r'<div class="stripe-payment__loading"[^>]*>', html).group(0)
    assert 'hx-post="/_render/_fragment/pay/stripe/create"' in loading
    assert 'hx-trigger="load"' in loading
    assert _hx_vals(loading) == {"invoice_id": "inv-1"}
    assert "<p>Redirecting to Stripe...</p>" in html


def test_pay_page_without_an_invoice(plugin):
    html = _render(
        plugin,
        "payment/pay.html.j2",
        _pages(PAYPAL_FLOW).pay_context(FakeThemeRequest()),
    )

    assert re.search(
        r'<div class="paypal-payment__no-invoice"><p>No invoice specified\. Please complete checkout first\.</p>',
        html,
    )
    assert "hx-post" not in html


def test_create_error_offers_try_again(plugin):
    context = _pages(create_session={"session_id": "x"}).create_context(
        FakeThemeRequest({"invoice_id": "inv-1"})
    )

    html = _render(plugin, "payment/_create.html.j2", context)

    assert '<div class="stripe-payment__error">' in html
    assert "<p>No redirect URL received</p>" in html
    retry = re.search(r"<button[^>]*>Try Again</button>", html).group(0)
    assert 'hx-post="/_render/_fragment/pay/stripe/create"' in retry
    assert _hx_vals(retry) == {"invoice_id": "inv-1"}


def test_stripe_success_page_starts_polling_immediately(plugin):
    html = _render(
        plugin,
        "payment/success.html.j2",
        _pages().success_context(FakeThemeRequest({"session_id": "cs_1"})),
    )

    verifying = re.search(r'<div class="stripe-success__verifying"[^>]*>', html).group(
        0
    )
    assert 'hx-get="/_render/_fragment/pay/stripe/status"' in verifying
    assert 'hx-trigger="load"' in verifying
    assert _hx_vals(verifying) == {"session_id": "cs_1", "attempt": 0, "invoice_id": ""}
    assert "<p>Verifying payment...</p>" in html
    assert "data-vbwd-auth-required" in html


def test_the_next_poll_waits_two_seconds(plugin):
    context = _pages(
        session_status={"status": "unpaid", "invoice_id": "inv-1"}
    ).status_context(FakeThemeRequest({"session_id": "cs_1", "attempt": "0"}))

    html = _render(plugin, "payment/_status.html.j2", context)

    verifying = re.search(r'<div class="stripe-success__verifying"[^>]*>', html).group(
        0
    )
    assert 'hx-trigger="load delay:2s"' in verifying
    assert _hx_vals(verifying) == {
        "session_id": "cs_1",
        "attempt": 1,
        "invoice_id": "inv-1",
    }


def test_timed_out_shows_processing_and_the_order_link(plugin):
    context = _pages().status_context(
        FakeThemeRequest({"session_id": "cs_1", "attempt": "15", "invoice_id": "inv-1"})
    )

    html = _render(plugin, "payment/_status.html.j2", context)

    assert "Your payment is being processed. This may take a moment." in html
    assert (
        '<a href="/checkout/confirmation?invoice_id=inv-1" class="btn btn-primary">View order</a>'
        in html
    )
    assert 'hx-trigger="load delay:2s"' in html


def test_status_error_links_to_the_invoices(plugin):
    html = _render(
        plugin,
        "payment/success.html.j2",
        _pages().success_context(FakeThemeRequest()),
    )

    assert '<div class="stripe-success__error">' in html
    assert "<p>No session ID</p>" in html
    assert (
        '<a href="/dashboard/invoices" class="btn btn-primary">View Invoices</a>'
        in html
    )


def test_paypal_capture_states(plugin):
    pages = _pages(PAYPAL_FLOW, capture_order={"status": "COMPLETED"})
    capturing = _render(
        plugin,
        "payment/success.html.j2",
        pages.success_context(FakeThemeRequest({"token": "O-1"})),
    )
    confirmed = _render(
        plugin,
        "payment/_capture.html.j2",
        pages.capture_context(FakeThemeRequest({"order_id": "O-1"})),
    )

    step = re.search(r'<div class="paypal-success__verifying"[^>]*>', capturing).group(
        0
    )
    assert 'hx-post="/_render/_fragment/pay/paypal/capture"' in step
    assert _hx_vals(step) == {"order_id": "O-1"}
    assert "<p>Completing your PayPal payment...</p>" in capturing
    assert '<div class="paypal-success__confirmed">' in confirmed
    assert "<h2>Payment Successful</h2>" in confirmed
    assert (
        "Your PayPal payment has been processed. Your subscription is now active."
        in confirmed
    )


def test_paypal_capture_error(plugin):
    context = _pages(PAYPAL_FLOW).success_context(FakeThemeRequest())

    html = _render(plugin, "payment/success.html.j2", context)

    assert (
        '<div class="paypal-success__error">' in html
        and "<p>No order token found</p>" in html
    )


def test_cancel_page_goes_back_to_the_checkout(plugin):
    html = _render(
        plugin, "payment/cancel.html.j2", _pages().cancel_context(FakeThemeRequest())
    )

    assert '<div class="stripe-cancel">' in html
    assert "<h2>Payment Cancelled</h2>" in html
    assert "Your payment was cancelled. Your invoice is still pending." in html
    assert '<a href="/checkout" class="btn btn-primary">Try Again</a>' in html
