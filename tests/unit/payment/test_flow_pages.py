"""S152-07 C — the generic ``/pay/<provider>`` page contexts, mirrored from the SPA views.

* pay page (``StripePaymentView`` / ``PayPalPaymentView`` + ``usePaymentRedirect``):
  ``?invoice=`` → the create island; none → "no invoice". The create fragment
  POSTs ``<api_prefix>/create-session`` and answers ``HX-Redirect`` to the
  session URL; no URL → "No redirect URL received"; a refusal → its message
  (else "Payment session failed"); a 401 stays 401 (the runtime ends the session).
* stripe success (``StripeSuccessView`` + ``usePaymentStatus``): poll
  ``session-status/<session_id>`` every 2 s, at most 15 times; complete / paid /
  succeeded → ``/checkout/confirmation?invoice_id=``; time-out → the
  "processing" state, then the confirmation 2 s later; a failure → its message.
* paypal success (``PayPalSuccessView``): ``?subscription_id`` → confirmed;
  no ``?token`` → "No order token found"; ``capture-order`` → confirmed, an
  "already"/"completed" refusal → confirmed, else its message.
"""
import pytest

from plugins.theme.theme.fragment_registry import ThemeFragmentRedirect
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest
from plugins.theme_checkout.tests.unit.payment.fakes import FakeProviderApi
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    PAYPAL_FLOW,
    STRIPE_FLOW,
)
from plugins.theme_checkout.theme_checkout.payment.flow_pages import (
    MAXIMUM_STATUS_ATTEMPTS,
    STATUS_POLL_DELAY,
    PaymentFlowPages,
)


def _pages(descriptor=STRIPE_FLOW, **answers):
    api = FakeProviderApi(**answers)
    return PaymentFlowPages(descriptor, api_factory=api.factory), api


# ── pay page + create fragment ───────────────────────────────────────────────


def test_pay_page_with_an_invoice_starts_the_create_island():
    pages, api = _pages()

    context = pages.pay_context(FakeThemeRequest({"invoice": "inv-1"}))

    assert context["invoice_id"] == "inv-1"
    assert context["provider"] == "stripe"
    assert context["create_url"] == "/_render/_fragment/pay/stripe/create"
    assert api.calls == []


def test_pay_page_without_an_invoice_is_the_no_invoice_state():
    pages, _api = _pages()

    assert pages.pay_context(FakeThemeRequest())["invoice_id"] == ""


def test_create_redirects_to_the_provider_session_url():
    pages, api = _pages(
        create_session={"session_id": "cs_1", "session_url": "https://pay.example/cs_1"}
    )

    with pytest.raises(ThemeFragmentRedirect) as redirect:
        pages.create_context(FakeThemeRequest({"invoice_id": "inv-1"}))

    assert redirect.value.location == "https://pay.example/cs_1"
    assert api.calls == [("create_session", "inv-1")]


def test_create_without_a_url_shows_no_redirect_url_received():
    pages, _api = _pages(create_session={"session_id": "cs_1"})

    context = pages.create_context(FakeThemeRequest({"invoice_id": "inv-1"}))

    assert context["error_key"] == "payment.errors.noRedirectUrl"
    assert context["invoice_id"] == "inv-1"


def test_a_refused_create_shows_the_api_message_or_the_default():
    with_message, _ = _pages(
        create_session=ThemeApiError(400, "Invoice is not pending")
    )
    without_message, _ = _pages(create_session=ThemeApiError(500, ""))
    request = FakeThemeRequest({"invoice_id": "inv-1"})

    assert (
        with_message.create_context(request)["error_message"]
        == "Invoice is not pending"
    )
    assert (
        without_message.create_context(request)["error_key"]
        == "payment.errors.sessionFailed"
    )


def test_an_unauthorized_create_stays_401_for_the_runtime():
    pages, _api = _pages(create_session=ThemeApiError(401, "expired"))

    with pytest.raises(ThemeApiError) as refusal:
        pages.create_context(FakeThemeRequest({"invoice_id": "inv-1"}))

    assert refusal.value.status == 401


# ── stripe success: status polling ───────────────────────────────────────────


def test_success_page_with_a_session_starts_polling_at_attempt_zero():
    pages, _api = _pages()

    context = pages.success_context(FakeThemeRequest({"session_id": "cs_1"}))

    assert context["state"] == "verifying"
    assert context["poll"] == {
        "url": "/_render/_fragment/pay/stripe/status",
        "session_id": "cs_1",
        "attempt": 0,
        "invoice_id": "",
        "delay": None,
    }


def test_success_page_without_a_session_is_the_no_session_error():
    pages, _api = _pages()

    context = pages.success_context(FakeThemeRequest())

    assert context["state"] == "error"
    assert context["error_key"] == "payment.errors.noSession"


@pytest.mark.parametrize("status", ["paid", "complete", "SUCCEEDED"])
def test_a_confirmed_status_redirects_to_the_confirmation(status):
    pages, api = _pages(session_status={"status": status, "invoice_id": "inv-1"})

    with pytest.raises(ThemeFragmentRedirect) as redirect:
        pages.status_context(FakeThemeRequest({"session_id": "cs_1", "attempt": "3"}))

    assert redirect.value.location == "/checkout/confirmation?invoice_id=inv-1"
    assert api.calls == [("session_status", "cs_1")]


def test_an_unpaid_status_polls_again_after_two_seconds_carrying_the_invoice():
    pages, _api = _pages(session_status={"status": "unpaid", "invoice_id": "inv-1"})

    context = pages.status_context(
        FakeThemeRequest({"session_id": "cs_1", "attempt": "0"})
    )

    assert context["state"] == "verifying"
    assert context["poll"]["attempt"] == 1
    assert context["poll"]["invoice_id"] == "inv-1"
    assert context["poll"]["delay"] == STATUS_POLL_DELAY == "2s"


def test_after_the_last_attempt_the_processing_state_then_the_confirmation():
    pages, api = _pages()

    timed_out = pages.status_context(
        FakeThemeRequest(
            {
                "session_id": "cs_1",
                "attempt": str(MAXIMUM_STATUS_ATTEMPTS),
                "invoice_id": "inv-1",
            }
        )
    )
    with pytest.raises(ThemeFragmentRedirect) as redirect:
        pages.status_context(
            FakeThemeRequest(
                {
                    "session_id": "cs_1",
                    "attempt": str(MAXIMUM_STATUS_ATTEMPTS + 1),
                    "invoice_id": "",
                }
            )
        )

    assert MAXIMUM_STATUS_ATTEMPTS == 15
    assert timed_out["state"] == "timed_out"
    assert timed_out["confirmation_url"] == "/checkout/confirmation?invoice_id=inv-1"
    assert timed_out["poll"]["attempt"] == MAXIMUM_STATUS_ATTEMPTS + 1
    assert timed_out["poll"]["delay"] == "2s"
    assert redirect.value.location == "/checkout/confirmation"
    assert api.calls == []


def test_a_failed_status_check_shows_its_message_or_the_default():
    with_message, _ = _pages(session_status=ThemeApiError(500, "Stripe is down"))
    without_message, _ = _pages(session_status=ThemeApiError(500, ""))
    request = FakeThemeRequest({"session_id": "cs_1", "attempt": "0"})

    context = with_message.status_context(request)
    assert (context["state"], context["error_message"], context["error_key"]) == (
        "error",
        "Stripe is down",
        None,
    )
    assert (
        without_message.status_context(request)["error_key"]
        == "payment.errors.statusFailed"
    )


def test_an_unauthorized_status_check_stays_401():
    pages, _api = _pages(session_status=ThemeApiError(401, "expired"))

    with pytest.raises(ThemeApiError):
        pages.status_context(FakeThemeRequest({"session_id": "cs_1", "attempt": "0"}))


def test_a_garbled_attempt_starts_from_zero():
    pages, _api = _pages(session_status={"status": "open"})

    context = pages.status_context(
        FakeThemeRequest({"session_id": "cs_1", "attempt": "x"})
    )

    assert context["poll"]["attempt"] == 1


# ── paypal success: capture ──────────────────────────────────────────────────


def test_paypal_subscription_return_is_confirmed_without_a_capture():
    pages, api = _pages(PAYPAL_FLOW)

    context = pages.success_context(FakeThemeRequest({"subscription_id": "I-SUB"}))

    assert context["state"] == "confirmed"
    assert api.calls == []


def test_paypal_return_without_a_token_is_an_error():
    pages, _api = _pages(PAYPAL_FLOW)

    assert (
        pages.success_context(FakeThemeRequest())["error_key"]
        == "payment.errors.noOrderToken"
    )


def test_paypal_return_with_a_token_starts_the_capture_island():
    pages, _api = _pages(PAYPAL_FLOW)

    context = pages.success_context(FakeThemeRequest({"token": "ORDER-1"}))

    assert context["state"] == "capturing"
    assert context["capture"] == {
        "url": "/_render/_fragment/pay/paypal/capture",
        "order_id": "ORDER-1",
    }


@pytest.mark.parametrize(
    "answer, expected",
    [
        (
            {"status": "COMPLETED"},
            {"state": "confirmed", "error_message": None, "error_key": None},
        ),
        (
            ThemeApiError(500, "Order already captured"),
            {"state": "confirmed", "error_message": None, "error_key": None},
        ),
        (
            ThemeApiError(500, "ORDER COMPLETED earlier"),
            {"state": "confirmed", "error_message": None, "error_key": None},
        ),
        (
            ThemeApiError(500, "Instrument declined"),
            {
                "state": "error",
                "error_message": "Instrument declined",
                "error_key": None,
            },
        ),
        (
            ThemeApiError(500, ""),
            {
                "state": "error",
                "error_message": None,
                "error_key": "payment.errors.captureFailed",
            },
        ),
    ],
)
def test_capture_outcomes_match_the_spa(answer, expected):
    pages, api = _pages(PAYPAL_FLOW, capture_order=answer)

    context = pages.capture_context(FakeThemeRequest({"order_id": "ORDER-1"}))
    assert {key: context[key] for key in expected} == expected
    assert context["provider"] == "paypal"
    assert api.calls == [("capture_order", "ORDER-1")]


def test_cancel_context_names_the_provider():
    pages, _api = _pages(PAYPAL_FLOW)

    assert pages.cancel_context(FakeThemeRequest()) == {
        "provider": "paypal",
        "translation_namespace": "paypal",
        "page_title": "",
        "success_handling": "capture_order",
    }
