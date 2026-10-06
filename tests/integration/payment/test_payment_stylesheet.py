"""S152-07c — the themed payment pages render classes the served theme.css styles.

StripeSuccessView is the only payment view with a ``<style>`` (``.stripe-success``,
its spinner and ``.btn-primary``); the walkthrough found ``/pay/*`` unstyled.
"""
from plugins.theme.tests.css_inventory import rule_classes

STYLESHEET_PATH = "/_render/_theme/public/theme.css"
RENDER = {"X-VBWD-Render": "1"}


def _styled_classes(client):
    response = client.get(STYLESHEET_PATH)
    assert response.status_code == 200
    return rule_classes(response.get_data(as_text=True))


def test_the_stripe_success_page_renders_classes_the_served_css_styles(client):
    styled = _styled_classes(client)
    html = client.get(
        "/pay/stripe/success?session_id=cs_test_1", headers=RENDER
    ).get_data(as_text=True)

    for class_name in ("stripe-success", "spinner"):
        assert f'class="{class_name}"' in html, class_name
        assert class_name in styled, class_name


def test_the_pay_and_cancel_pages_use_the_styled_button(client, pending_invoice):
    styled = _styled_classes(client)
    pay = client.get(
        f"/pay/stripe?invoice={pending_invoice.id}", headers=RENDER
    ).get_data(as_text=True)
    cancel = client.get("/pay/stripe/cancel", headers=RENDER).get_data(as_text=True)

    assert 'class="stripe-payment"' in pay
    assert 'class="btn btn-primary"' in cancel
    assert {"btn", "btn-primary"} <= styled
