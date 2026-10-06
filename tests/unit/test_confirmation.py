"""S152-07 B — the ``CheckoutConfirmation`` component (``CheckoutConfirmationView.vue``).

It sits in the ``checkout-confirmation`` CMS page's layout, so it renders inside a
personalised region: anonymously it shows the pending banner (no API call); the
region re-render for a logged-in viewer reads ``GET /user/invoices/<id>`` with
the bearer. A failure keeps the pending state. A loaded invoice clears
``vbwd_shop_cart`` (the SPA does) and fills the CMS page's ``{{variables}}``.
"""
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeCheckoutApi, FakeThemeRequest
from plugins.theme_checkout.theme_checkout.confirmation import (
    locale_datetime,
    CheckoutConfirmation,
    status_copy,
)
from plugins.theme_checkout.theme_checkout.confirmation_sections import (
    ConfirmationSectionRegistry,
)

INVOICE = {
    "invoice_number": "INV-0042",
    "status": "PAID",
    "total_amount": "119.00",
    "subtotal": "100.00",
    "tax_amount": "19.00",
    "currency": "USD",
    "payment_method": "stripe",
    "paid_at": "2026-10-03T09:05:07",
    "line_items": [
        {
            "description": "Pro <b>Plan</b>",
            "quantity": 1,
            "unit_price": "100.00",
            "amount": "100.00",
        }
    ],
}


def _component(**answers):
    api = FakeCheckoutApi(**answers)
    sections = ConfirmationSectionRegistry(lambda fe_user_plugin: True)
    return CheckoutConfirmation(sections, api_factory=api.factory), api


def _context(component, query, user_id=None, page=None):
    return component.build_context(
        {}, page or {}, {}, FakeThemeRequest(query, user_id=user_id)
    )


def test_anonymous_render_is_the_pending_banner_without_an_api_call():
    component, api = _component()

    context = _context(component, {"invoice_id": "inv-1"})

    assert api.calls == []
    assert context["status"] == "pending"
    assert context["title"] == "Payment Processing"
    assert context["invoice"] is None
    assert context["clear_shop_cart"] is False


def test_a_logged_in_viewer_sees_the_invoice_details():
    component, api = _component(invoice={"invoice": INVOICE})

    context = _context(component, {"invoice_id": "inv-1"}, user_id="u-1")

    assert api.called("invoice") == [("invoice", "inv-1")]
    assert context["status"] == "paid"
    assert context["title"] == "Payment Successful"
    assert context["invoice"]["number"] == "INV-0042"
    assert context["invoice"]["amount"] == "$119.00"
    assert context["invoice"]["payment_method"] == "stripe"
    assert context["invoice"]["date"] == "10/3/2026, 9:05:07 AM"
    assert context["invoice"]["line_items"] == [
        {
            "description": "Pro <b>Plan</b>",
            "quantity": 1,
            "unit_price": "$100.00",
            "amount": "$100.00",
        }
    ]
    assert context["clear_shop_cart"] is True


def test_the_legacy_invoice_query_parameter_is_read_too():
    component, api = _component(invoice=INVOICE)

    _context(component, {"invoice": "inv-2"}, user_id="u-1")

    assert api.called("invoice") == [("invoice", "inv-2")]


def test_an_unreadable_invoice_keeps_the_pending_state():
    component, _api = _component(invoice=ThemeApiError(403, "Access denied"))

    context = _context(component, {"invoice_id": "inv-1"}, user_id="u-1")

    assert context["status"] == "pending"
    assert context["invoice"] is None
    assert context["clear_shop_cart"] is False


def test_no_invoice_id_makes_no_call():
    component, api = _component()

    _context(component, {}, user_id="u-1")

    assert api.calls == []


def test_status_copy_matches_the_spa_banner():
    assert status_copy("paid")[0] == "Payment Successful"
    assert status_copy("pending")[0] == "Payment Processing"
    assert status_copy("authorized")[0] == "Payment Authorized"
    assert status_copy("failed")[0] == "Payment Failed"
    assert status_copy("cancelled") == (
        "Payment Cancelled",
        "Your payment was cancelled.",
    )
    assert status_copy("refunded") == (
        "Order Received",
        "Your order has been received.",
    )


def test_the_cms_page_variables_are_filled_and_escaped():
    component, _api = _component(invoice={"invoice": INVOICE})
    page = {
        "content_html": "<p>Thanks! {{ invoice_number }} · {{total_amount}} · {{status}}"
        " · {{ unknown }}</p>{{line_items_html}}"
    }

    context = _context(component, {"invoice_id": "inv-1"}, user_id="u-1", page=page)

    html = str(context["content_html"])
    assert "<p>Thanks! INV-0042 · $119.00 · paid · {{ unknown }}</p>" in html
    assert "<td>Pro &lt;b&gt;Plan&lt;/b&gt;</td><td>1</td><td>$100.00</td>" in html


def test_an_anonymous_render_leaves_the_variables_empty():
    component, _api = _component()

    context = _context(
        component,
        {"invoice_id": "inv-1"},
        page={"content_html": "<p>#{{invoice_number}}#</p>"},
    )

    assert str(context["content_html"]) == "<p>##</p>"


def test_locale_datetime_is_the_spas_en_us_to_locale_string():
    """Shared with the booking pages (BookingCheckout / BookingSuccess, S152-09)."""
    assert locale_datetime("2026-11-02T09:05:07") == "11/2/2026, 9:05:07 AM"
    assert locale_datetime("2026-11-02T13:00:00") == "11/2/2026, 1:00:00 PM"
    assert locale_datetime("2026-11-02T00:30:00") == "11/2/2026, 12:30:00 AM"
    assert locale_datetime("") == "" and locale_datetime(None) == ""
    assert locale_datetime("not-a-date") == "not-a-date"
