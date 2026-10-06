"""S152-07 C — declarative payment flows (sprint "Payment providers are declarative").

A :class:`PaymentFlowDescriptor` says everything the generic ``/pay/<provider>``
pages need: the fe-user plugin whose toggle governs it, the payment-method code
the checkout dispatches on, the provider API prefix, the create endpoint and its
redirect-URL field, and how the success page confirms (stripe polls
``session-status``; paypal POSTs ``capture-order``). Only the ``redirect`` kind is
built in S152; ``poll`` / ``custom`` arrive with their providers in S153 and are
refused until then. token-payment has no page (its SPA plugin registers none):
it is an ``instantPay`` checkout method only.
"""
import pytest

from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest
from plugins.theme_checkout.theme_checkout.payment import flow_descriptors
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    BUILT_IN_FLOWS,
    PAYPAL_FLOW,
    STRIPE_FLOW,
    TOKEN_BALANCE_METHOD,
    FlowKind,
    PaymentFlowDescriptor,
    PaymentFlowRegistrationError,
    PaymentFlowRegistry,
    SuccessHandling,
)


def test_stripe_is_a_redirect_flow_confirmed_by_polling_its_session_status():
    assert STRIPE_FLOW.provider == "stripe"
    assert STRIPE_FLOW.fe_user_plugin == "stripe-payment"
    assert STRIPE_FLOW.payment_method_code == "stripe"
    assert STRIPE_FLOW.kind is FlowKind.REDIRECT
    assert STRIPE_FLOW.api_prefix == "/api/v1/plugins/stripe"
    assert STRIPE_FLOW.create_path == "/create-session"
    assert STRIPE_FLOW.session_url_field == "session_url"
    assert STRIPE_FLOW.success_handling is SuccessHandling.POLL_SESSION_STATUS


def test_paypal_is_a_redirect_flow_confirmed_by_capturing_the_order():
    assert PAYPAL_FLOW.provider == "paypal"
    assert PAYPAL_FLOW.fe_user_plugin == "paypal-payment"
    assert PAYPAL_FLOW.payment_method_code == "paypal"
    assert PAYPAL_FLOW.api_prefix == "/api/v1/plugins/paypal"
    assert PAYPAL_FLOW.success_handling is SuccessHandling.CAPTURE_ORDER


def test_the_built_in_flows_are_stripe_and_paypal():
    assert BUILT_IN_FLOWS == (STRIPE_FLOW, PAYPAL_FLOW)


def test_the_flow_kinds_of_the_sprint_exist():
    assert {kind.value for kind in FlowKind} == {"redirect", "poll", "custom"}


@pytest.mark.parametrize("kind", [FlowKind.POLL, FlowKind.CUSTOM])
def test_kinds_not_built_yet_are_refused_at_registration(kind):
    registry = PaymentFlowRegistry()
    descriptor = PaymentFlowDescriptor(
        provider="promptpay",
        fe_user_plugin="promptpay-payment",
        payment_method_code="promptpay",
        kind=kind,
        api_prefix="/api/v1/plugins/promptpay",
        success_handling=SuccessHandling.POLL_SESSION_STATUS,
    )

    with pytest.raises(PaymentFlowRegistrationError, match="S153"):
        registry.register(descriptor)


def test_registry_lists_and_finds_flows_and_refuses_a_duplicate_provider():
    registry = PaymentFlowRegistry()
    registry.register(STRIPE_FLOW)
    registry.register(PAYPAL_FLOW)

    assert registry.descriptors() == [STRIPE_FLOW, PAYPAL_FLOW]
    assert registry.get("paypal") is PAYPAL_FLOW
    assert registry.get("crypto") is None
    with pytest.raises(PaymentFlowRegistrationError, match="already"):
        registry.register(STRIPE_FLOW)


def test_a_provider_must_be_a_url_segment():
    with pytest.raises(PaymentFlowRegistrationError, match="provider"):
        PaymentFlowRegistry().register(
            PaymentFlowDescriptor(
                provider="../evil",
                fe_user_plugin="x",
                payment_method_code="x",
                kind=FlowKind.REDIRECT,
                api_prefix="/api/v1/plugins/x",
                success_handling=SuccessHandling.CAPTURE_ORDER,
            )
        )


def test_the_checkout_redirect_path_is_the_spa_one():
    assert STRIPE_FLOW.checkout_redirect_path("inv-1") == "/pay/stripe?invoice=inv-1"
    assert PAYPAL_FLOW.checkout_redirect_path("a b") == "/pay/paypal?invoice=a%20b"


def test_token_balance_pays_in_band_through_the_token_payment_api(monkeypatch):
    calls = []

    def fake_call_api(theme_request, method, path, **options):
        calls.append((method, path, options))
        return {"status": "PAID"}

    monkeypatch.setattr(flow_descriptors, "call_api", fake_call_api)

    assert TOKEN_BALANCE_METHOD.code == "token_balance"
    assert TOKEN_BALANCE_METHOD.owner_fe_user_plugin == "token-payment"
    assert TOKEN_BALANCE_METHOD.redirect_path is None
    TOKEN_BALANCE_METHOD.instant_pay(FakeThemeRequest(), "inv-9")
    assert calls == [
        ("POST", "/api/v1/plugins/token-payment/invoices/inv-9/pay", {"json": {}})
    ]
