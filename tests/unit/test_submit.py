"""S152-07 B — the confirm fragment: ``checkoutStore.submitCheckout`` + the dispatch watcher.

The active source submits (same API as its SPA source) with the selected
payment method; success ends the htmx flow with ``HX-Redirect`` to wherever
:func:`dispatch_after_submit` sends the buyer; a refusal shows its message in
``checkout-form-error`` (``err.message || 'Checkout failed'``); no active source
→ "No items selected".
"""
import pytest

from plugins.theme.theme.fragment_registry import ThemeFragmentRedirect
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest, fake_source
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutSourceRegistry,
)
from plugins.theme_checkout.theme_checkout.payment_methods import (
    CheckoutPaymentMethod,
    CheckoutPaymentMethodRegistry,
)
from plugins.theme_checkout.theme_checkout.submit import CheckoutSubmit


def _submit(source=None):
    sources = CheckoutSourceRegistry()
    if source is not None:
        sources.register(source)
    methods = CheckoutPaymentMethodRegistry(lambda plugin_name: True)
    methods.register(
        CheckoutPaymentMethod(
            code="stripe",
            owner_fe_user_plugin="stripe-payment",
            redirect_path=lambda invoice_id: f"/pay/stripe?invoice={invoice_id}",
        )
    )
    return CheckoutSubmit(sources, methods)


def test_a_successful_submit_redirects_through_the_dispatch_table():
    source, received = fake_source(submit_result={"invoice": {"id": "inv-7"}})

    with pytest.raises(ThemeFragmentRedirect) as redirect:
        _submit(source).context(
            FakeThemeRequest(
                {"source": "fake", "payment_method": "stripe", "coupon_code": "C"}
            )
        )

    assert redirect.value.location == "/pay/stripe?invoice=inv-7"
    submitted_context, payment_method_code = received["submit"][0]
    assert payment_method_code == "stripe"
    assert submitted_context.coupon_code == "C"


def test_a_submit_without_a_payment_method_goes_to_confirmation():
    source, received = fake_source(submit_result={"invoice": {"id": "inv-8"}})

    with pytest.raises(ThemeFragmentRedirect) as redirect:
        _submit(source).context(FakeThemeRequest({"source": "fake"}))

    assert redirect.value.location == "/checkout/confirmation?invoice_id=inv-8"
    assert received["submit"][0][1] is None


def test_a_refused_submit_shows_the_api_message():
    source, _ = fake_source(submit_result=ThemeApiError(400, "Plan is not active"))

    context = _submit(source).context(FakeThemeRequest({"source": "fake"}))

    assert context == {"error_message": "Plan is not active", "error_key": None}


def test_a_refusal_without_a_message_shows_checkout_failed():
    source, _ = fake_source(submit_result=ThemeApiError(500, ""))

    context = _submit(source).context(FakeThemeRequest({"source": "fake"}))

    assert context == {
        "error_message": None,
        "error_key": "checkout.errors.checkoutFailed",
    }


def test_no_active_source_shows_no_items_selected():
    context = _submit().context(FakeThemeRequest({"source": "fake"}))

    assert context == {
        "error_message": None,
        "error_key": "checkout.errors.noItemsSelected",
    }


def test_a_result_without_an_invoice_stays_silently():
    source, _ = fake_source(submit_result={"message": "queued"})

    assert _submit(source).context(FakeThemeRequest({"source": "fake"})) == {
        "error_message": None,
        "error_key": None,
    }
