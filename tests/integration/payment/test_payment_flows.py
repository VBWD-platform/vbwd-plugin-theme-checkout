"""S152-07 C — themed ``/pay/*`` flows against the REAL stripe / paypal / token-payment routes.

The fragments dispatch through core C2 to the payment plugins' own endpoints
(``require_auth``, invoice ownership + PENDING checks, success URLs built from
the forwarded ``Origin``). Only the provider SDK boundary is stubbed:
``stripe.checkout.Session`` and PayPal's ``requests`` calls.
"""
import json
import logging
import re
from types import SimpleNamespace

import pytest
import requests
import stripe

from plugins.theme_checkout.tests.integration.payment.conftest import (
    FE_USER_PLUGINS,
    write_manifest,
)
from plugins.theme_checkout.tests.integration import fake_checkout_adapter

RENDER = {"X-VBWD-Render": "1"}
ORIGIN = {"Origin": "https://shop.example"}
SESSION_URL = "https://checkout.stripe.test/c/pay/cs_test_1"


def _stripe_session(**fields):
    defaults = {
        "id": "cs_test_1",
        "url": SESSION_URL,
        "payment_status": "unpaid",
        "amount_total": 4900,
        "currency": "eur",
        "metadata": {},
        "payment_intent": "pi_test_1",
        "subscription": None,
    }
    return SimpleNamespace(**{**defaults, **fields})


@pytest.fixture
def stripe_sessions(monkeypatch):
    """Records ``Session.create`` kwargs; ``retrieve`` answers the queued sessions in order."""
    recorded = SimpleNamespace(created=[], retrieved=[], queue=[])

    def create(**kwargs):
        recorded.created.append(kwargs)
        return _stripe_session()

    def retrieve(session_id):
        recorded.retrieved.append(session_id)
        return recorded.queue.pop(0)

    monkeypatch.setattr(stripe.checkout.Session, "create", create)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve", retrieve)
    return recorded


def _testclass(html, css_class):
    return re.search(rf'<[^>]*class="{re.escape(css_class)}"[^>]*>', html)


# ── pages ────────────────────────────────────────────────────────────────────


def test_pay_page_is_the_auth_required_shell_with_the_create_island(
    client, pending_invoice
):
    response = client.get(f"/pay/stripe?invoice={pending_invoice.id}", headers=RENDER)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<body data-auth="pending" data-vbwd-auth-required>' in html
    loading = _testclass(html, "stripe-payment__loading").group(0)
    assert json.loads(re.search(r"hx-vals='([^']*)'", loading).group(1)) == {
        "invoice_id": str(pending_invoice.id)
    }


def test_cancel_and_success_pages_answer_for_both_providers(client):
    for path in (
        "/pay/stripe/cancel",
        "/pay/paypal/cancel",
        "/pay/stripe/success?session_id=cs_test_1",
        "/pay/paypal/success?token=ORDER-1",
    ):
        assert client.get(path, headers=RENDER).status_code == 200, path


def test_a_disabled_fe_user_payment_plugin_404s_its_pages_and_fragments(
    client, manifest_path
):
    write_manifest(
        manifest_path, [name for name in FE_USER_PLUGINS if name != "stripe-payment"]
    )
    try:
        assert client.get("/pay/stripe?invoice=x", headers=RENDER).status_code == 404
        assert client.post("/_render/_fragment/pay/stripe/create").status_code == 404
        assert client.get("/pay/paypal/cancel", headers=RENDER).status_code == 200
    finally:
        write_manifest(manifest_path, FE_USER_PLUGINS)


# ── stripe ───────────────────────────────────────────────────────────────────


def test_stripe_redirect_fragment_returns_hx_redirect_to_session_url(
    client, bearer, pending_invoice, stripe_sessions
):
    response = client.post(
        "/_render/_fragment/pay/stripe/create",
        data={"invoice_id": str(pending_invoice.id)},
        headers={**bearer, **ORIGIN},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.headers["HX-Redirect"] == SESSION_URL
    assert response.get_data(as_text=True) == ""
    created = stripe_sessions.created[0]
    # The real route built the return URLs from the Origin the fragment forwarded.
    assert created["success_url"] == (
        "https://shop.example/pay/stripe/success?session_id={CHECKOUT_SESSION_ID}"
    )
    assert created["cancel_url"] == "https://shop.example/pay/stripe/cancel"
    assert created["metadata"]["invoice_id"] == str(pending_invoice.id)


def test_stripe_create_without_a_session_is_a_401_for_the_runtime(
    client, pending_invoice
):
    response = client.post(
        "/_render/_fragment/pay/stripe/create",
        data={"invoice_id": str(pending_invoice.id)},
    )

    assert response.status_code == 401


def test_stripe_create_for_someone_elses_invoice_shows_the_api_refusal(
    client, pending_invoice, stripe_sessions
):
    admin = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "AdminPass123@"},
    ).get_json()

    response = client.post(
        "/_render/_fragment/pay/stripe/create",
        data={"invoice_id": str(pending_invoice.id)},
        headers={"Authorization": f"Bearer {admin['token']}", **ORIGIN},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "HX-Redirect" not in response.headers
    assert "Invoice does not belong to this user" in html
    assert ">Try Again</button>" in html
    assert stripe_sessions.created == []


def test_success_page_polls_then_redirects_to_confirmation(
    client, bearer, pending_invoice, stripe_sessions
):
    invoice_id = str(pending_invoice.id)
    stripe_sessions.queue.extend(
        [
            _stripe_session(
                payment_status="unpaid", metadata={"invoice_id": invoice_id}
            ),
            _stripe_session(payment_status="paid", metadata={"invoice_id": invoice_id}),
        ]
    )
    page = client.get(
        "/pay/stripe/success?session_id=cs_test_1", headers=RENDER
    ).get_data(as_text=True)
    first_step = _testclass(page, "stripe-success__verifying").group(0)
    first_vals = json.loads(re.search(r"hx-vals='([^']*)'", first_step).group(1))

    still_open = client.get(
        "/_render/_fragment/pay/stripe/status", query_string=first_vals, headers=bearer
    )
    next_step = _testclass(
        still_open.get_data(as_text=True), "stripe-success__verifying"
    ).group(0)
    next_vals = json.loads(re.search(r"hx-vals='([^']*)'", next_step).group(1))
    paid = client.get(
        "/_render/_fragment/pay/stripe/status", query_string=next_vals, headers=bearer
    )

    assert first_vals == {"session_id": "cs_test_1", "attempt": 0, "invoice_id": ""}
    assert 'hx-trigger="load delay:2s"' in next_step
    assert next_vals == {
        "session_id": "cs_test_1",
        "attempt": 1,
        "invoice_id": invoice_id,
    }
    assert paid.status_code == 200
    assert (
        paid.headers["HX-Redirect"] == f"/checkout/confirmation?invoice_id={invoice_id}"
    )
    assert stripe_sessions.retrieved == ["cs_test_1", "cs_test_1"]


# ── paypal ───────────────────────────────────────────────────────────────────


class FakePayPalResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body

    def raise_for_status(self):
        return None


@pytest.fixture
def paypal_http(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(("POST", url))
        if url.endswith("/v1/oauth2/token"):
            return FakePayPalResponse(
                200, {"access_token": "token", "expires_in": 3600}
            )
        if url.endswith("/capture"):
            return FakePayPalResponse(
                201, {"id": "ORDER-1", "status": "COMPLETED", "purchase_units": [{}]}
            )
        raise AssertionError(f"unexpected PayPal POST {url}")

    def fake_get(url, **kwargs):
        calls.append(("GET", url))
        return FakePayPalResponse(200, {"status": "COMPLETED", "purchase_units": [{}]})

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def test_paypal_success_captures_the_order_through_the_real_route(
    client, bearer, paypal_http
):
    page = client.get("/pay/paypal/success?token=ORDER-1", headers=RENDER).get_data(
        as_text=True
    )
    step = _testclass(page, "paypal-success__verifying").group(0)

    captured = client.post(
        "/_render/_fragment/pay/paypal/capture",
        data=json.loads(re.search(r"hx-vals='([^']*)'", step).group(1)),
        headers=bearer,
    )

    html = captured.get_data(as_text=True)
    assert captured.status_code == 200
    assert '<div class="paypal-success__confirmed">' in html
    assert (
        "POST",
        "https://api-m.sandbox.paypal.com/v2/checkout/orders/ORDER-1/capture",
    ) in paypal_http


# ── token-payment instant pay through the checkout dispatch ──────────────────


def test_token_balance_pays_in_band_then_lands_on_confirmation(
    client, bearer, pending_invoice, monkeypatch, caplog
):
    invoice_id = str(pending_invoice.id)
    monkeypatch.setitem(
        fake_checkout_adapter.FAKE_SUBMIT_RESULT, "invoice", {"id": invoice_id}
    )

    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/_render/_fragment/checkout/submit",
            data={"source": "fake", "cart": "[]", "payment_method": "token_balance"},
            headers=bearer,
        )

    assert (
        response.headers["HX-Redirect"]
        == f"/checkout/confirmation?invoice_id={invoice_id}"
    )
    # The test user has no token balance: the REAL token-payment route refused
    # (400/422, not a 404), the failure was logged, and the buyer still lands
    # on the confirmation — the SPA's instantPay contract.
    assert re.search(
        r"instant pay failed for token_balance: inner API answered 4(00|22)",
        caplog.text,
    )


def test_stripe_checkout_choice_redirects_to_the_themed_pay_page(
    client, bearer, pending_invoice, monkeypatch
):
    monkeypatch.setitem(
        fake_checkout_adapter.FAKE_SUBMIT_RESULT, "invoice", {"id": "inv-7"}
    )

    response = client.post(
        "/_render/_fragment/checkout/submit",
        data={"source": "fake", "cart": "[]", "payment_method": "stripe"},
        headers=bearer,
    )

    assert response.headers["HX-Redirect"] == "/pay/stripe?invoice=inv-7"
