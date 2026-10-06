"""S152-07 B — the themed checkout on a real ``create_app`` (theme mode).

Pages answer with the render marker; the island, email-block and confirm
fragments dispatch to the real core API (auth, settings, user details) through
C2 with the browser's bearer; a selling adapter (test-only) prices the posted
fe-core cart and submits; the confirm fragment answers ``HX-Redirect`` per the
dispatch table. ``/checkout/confirmation`` is the ``checkout-confirmation`` CMS
page whose CheckoutConfirmation widget re-renders with the invoice for its owner.
"""
import json
import re
from decimal import Decimal

import pytest

from vbwd.security.route_audit import find_unprotected_routes

from plugins.theme_checkout.tests.integration import fake_checkout_adapter

RENDER = {"X-VBWD-Render": "1"}
FORM_FRAGMENT = "/_render/_fragment/checkout/form"
CART = [
    {"type": "PLAN", "id": "p-1", "name": "Pro Plan", "price": 20, "quantity": 1},
    {
        "type": "TOKEN_BUNDLE",
        "id": "b-1",
        "name": "1000 Tokens",
        "price": 5,
        "quantity": 2,
    },
]


def _testid(html, testid):
    return re.search(rf'<[^>]*data-testid="{re.escape(testid)}"[^>]*>', html)


def _island(client, headers=None, **fields):
    response = client.post(
        FORM_FRAGMENT,
        data={"source": "fake", "cart": json.dumps(CART), **fields},
        headers=headers or {},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"
    return response.get_data(as_text=True)


# ── /checkout page ───────────────────────────────────────────────────────────


def test_checkout_without_a_matching_source_is_the_no_plan_state(client):
    response = client.get("/checkout?source=shop", headers=RENDER)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<meta name="vbwd-frontend" content="theme">' in html
    assert _testid(html, "checkout-no-plan")


def test_checkout_with_a_matching_source_renders_the_island_placeholder(client):
    html = client.get("/checkout?source=fake", headers=RENDER).get_data(as_text=True)

    assert 'data-vbwd-cart="vbwd_cart"' in html
    assert 'hx-post="/_render/_fragment/checkout/form"' in html
    assert _testid(html, "checkout-loading")


def test_an_unknown_draft_token_is_the_expired_link_state(client):
    html = client.get("/checkout?draft=not-a-token", headers=RENDER).get_data(
        as_text=True
    )

    assert _testid(html, "checkout-draft-expired")
    assert not _testid(html, "order-summary")


def test_checkout_without_the_render_marker_falls_back_to_the_spa(client):
    assert client.get("/checkout?source=fake").status_code == 404


# ── the island ───────────────────────────────────────────────────────────────


def test_the_island_prices_the_posted_cart_through_the_source(client):
    html = _island(client)

    assert _testid(html, "order-summary") and _testid(html, "email-block")
    assert _testid(html, "line-item-p-1") and _testid(html, "line-item-b-1")
    assert re.search(r'data-testid="order-total-amount">Total: €30\.00<', html)
    assert _testid(html, "billing-address-block") and _testid(html, "terms-checkbox")
    assert _testid(html, "payment-methods-block")
    assert _testid(html, "coupon-input")


def test_a_valid_coupon_reduces_the_total_and_a_bogus_one_shows_its_error(client):
    discounted = _island(client, coupon_action="apply", coupon_input="TENOFF")
    bogus = _island(client, coupon_action="apply", coupon_input="NOTACODE123")

    assert re.search(
        r'data-testid="order-total-amount">Final price with coupon: €27\.00<',
        discounted,
    )
    assert re.search(
        r'data-testid="order-discount">You have saved: €3\.00<', discounted
    )
    assert re.search(r'data-testid="coupon-error">Invalid coupon<', bogus)
    assert re.search(r'data-testid="order-total-amount">Total: €30\.00<', bogus)


def test_the_logged_in_buyer_is_recognised_through_the_forwarded_bearer(client, bearer):
    html = _island(client, headers=bearer)

    assert _testid(html, "email-block-success")
    assert "test@example.com" in html
    assert 'data-authenticated="1"' in html
    assert not re.search(r'data-requirement="signIn">', html)


def test_the_payment_methods_come_from_the_settings_api(client, app):
    html = _island(client)

    with app.app_context():
        methods = client.get(
            "/api/v1/settings/payment-methods?currency=EUR"
        ).get_json()["methods"]
    for method in methods:
        assert _testid(html, f"payment-method-{method['code']}"), method["code"]
    if not methods:
        assert "No payment methods available" in html


# ── email block ──────────────────────────────────────────────────────────────


def test_email_check_asks_the_auth_api(client):
    existing = client.get(
        "/_render/_fragment/checkout/email-check",
        query_string={"email": "TEST@example.com"},
    ).get_data(as_text=True)
    new = client.get(
        "/_render/_fragment/checkout/email-check",
        query_string={"email": "nobody-s152@example.com"},
    ).get_data(as_text=True)

    assert _testid(existing, "email-existing-user")
    assert _testid(new, "email-new-user")


def test_inline_login_answers_the_session_directive_with_the_email_block_keys(client):
    response = client.post(
        "/_render/_fragment/checkout/login",
        data={"email": "test@example.com", "password": "TestPass123@"},
    )

    match = re.search(
        r"data-vbwd-session>(.*?)</script>", response.get_data(as_text=True)
    )
    session = json.loads(match.group(1))
    assert session["user_email"] == "test@example.com"
    assert session["token"].count(".") == 2 and session["user_id"]
    assert "redirect" not in session


def test_inline_login_with_a_wrong_password_shows_the_retry_copy(client):
    html = client.post(
        "/_render/_fragment/checkout/login",
        data={"email": "test@example.com", "password": "wrong"},
    ).get_data(as_text=True)

    assert "Login failed. Please try again." in html
    assert "data-vbwd-session" not in html


# ── confirm + dispatch ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payment_method, location",
    [
        ("fakepay", "/pay/fake?invoice=inv-42"),
        ("fakeinstant", "/checkout/confirmation?invoice_id=inv-42"),
        ("unregistered", "/checkout/confirmation?invoice_id=inv-42"),
    ],
)
def test_confirm_redirects_per_the_dispatch_table(
    client, payment_method, location, monkeypatch
):
    monkeypatch.setitem(
        fake_checkout_adapter.FAKE_SUBMIT_RESULT, "invoice", {"id": "inv-42"}
    )
    fake_checkout_adapter.instant_paid_invoice_ids.clear()

    response = client.post(
        "/_render/_fragment/checkout/submit",
        data={
            "source": "fake",
            "cart": json.dumps(CART),
            "payment_method": payment_method,
        },
    )

    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == location
    assert response.get_data(as_text=True) == ""
    expected_instant = ["inv-42"] if payment_method == "fakeinstant" else []
    assert fake_checkout_adapter.instant_paid_invoice_ids == expected_instant


def test_confirm_without_a_source_shows_no_items_selected(client):
    html = client.post(
        "/_render/_fragment/checkout/submit", data={"source": "nothing"}
    ).get_data(as_text=True)

    assert re.search(r'data-testid="checkout-form-error"[^>]*>No items selected<', html)


# ── /checkout/confirmation ───────────────────────────────────────────────────


def _confirmation_page(cms, client):
    existing = client.get("/api/v1/cms/posts/checkout-confirmation")
    if existing.status_code == 200:
        return existing.get_json()
    widget = cms.vue_widget("CheckoutConfirmation")
    return cms.page_with_widgets([widget], slug="checkout-confirmation")


def _pending_invoice_of_the_test_user(app):
    from vbwd.extensions import db
    from vbwd.models.enums import InvoiceStatus
    from vbwd.models.invoice import UserInvoice

    user = app.container.user_repository().find_by_email("test@example.com")
    invoice = UserInvoice(
        user_id=user.id,
        invoice_number="INV-S152-07",
        amount=Decimal("30.00"),
        total_amount=Decimal("30.00"),
        currency="EUR",
        status=InvoiceStatus.PENDING,
    )
    db.session.add(invoice)
    db.session.flush()
    return invoice


def test_confirmation_renders_the_cms_page_with_the_pending_banner(client, cms):
    _confirmation_page(cms, client)

    response = client.get(
        "/checkout/confirmation?invoice_id=00000000-0000-0000-0000-000000000000",
        headers=RENDER,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert _testid(html, "checkout-confirmation")
    assert _testid(html, "confirmation-banner")
    assert "<h1>Payment Processing</h1>" in html
    assert "cms-page__not-found" not in html


def test_the_confirmation_region_shows_the_invoice_to_its_owner(
    client, cms, bearer, app
):
    _confirmation_page(cms, client)
    invoice = _pending_invoice_of_the_test_user(app)

    response = client.get(
        "/_render/_fragment/regions",
        query_string={"path": f"/checkout/confirmation?invoice_id={invoice.id}"},
        headers=bearer,
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    regions_html = "".join(response.get_json()["regions"].values())
    assert _testid(regions_html, "invoice-details")
    assert "INV-S152-07" in regions_html
    assert 'data-vbwd-cart-clear="vbwd_shop_cart"' in regions_html


def test_checkout_fragments_pass_the_route_exposure_audit(app):
    offenders = [
        str(route.path)
        for route in find_unprotected_routes(app)
        if "/_render/_fragment/checkout" in str(route.path)
    ]

    assert offenders == []
