"""S152-07 B — the checkout island's context (the body of ``PublicCheckoutView``).

The runtime posts the island with the fe-core cart and, when logged in, the
bearer; the island re-renders the whole form from the posted state each time
(coupon apply/clear, inline login), so typed values survive. Rules mirrored:

* ``hasPayableTotal`` = net total + discount > 0 → coupon input + billing block;
* ``isPayZero`` = net total == 0 → no payment-method block;
* payment methods: ``GET /settings/payment-methods?currency=``; the first is
  auto-selected; failure → "Failed to load payment methods";
* billing: countries from ``/settings/countries`` (fallback list on failure),
  a logged-in buyer's saved address from ``/user/details``;
* requirements = ``missingRequirements`` (sign in, billing, payment, terms).
"""
import json
from decimal import Decimal

import pytest

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import (
    FakeCheckoutApi,
    FakeThemeRequest,
    fake_source,
)
from plugins.theme_checkout.theme_checkout.checkout_blocks import (
    FALLBACK_COUNTRIES,
    render_terms_html,
)
from plugins.theme_checkout.theme_checkout.checkout_form import CheckoutForm
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutSourceRegistry,
    CheckoutSummary,
)

PROFILE = {
    "user": {"id": "u-1", "email": "buyer@example.com"},
    "details": {"first_name": "Ada", "last_name": "Lovelace"},
}
SAVED_DETAILS = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "company": None,
    "address_line_1": "1 Analytical St",
    "city": "London",
    "state": None,
    "postal_code": "N1",
    "country": "GB",
}


def _form(source=None, api=None):
    registry = CheckoutSourceRegistry()
    registry.register(source or fake_source()[0])
    api = api or FakeCheckoutApi()
    return CheckoutForm(registry, api_factory=api.factory), api


def _post(**fields):
    return FakeThemeRequest({"source": "fake", **fields})


def test_no_matching_source_renders_the_no_plan_state():
    form, _api = _form()

    assert form.context(FakeThemeRequest({"source": "shop"}))["state"] == "no_plan"


def test_a_source_load_failure_renders_the_checkout_error_with_its_message():
    source, _ = fake_source(summary=ThemeApiError(404, "Plan not found"))
    form, _api = _form(source)

    context = form.context(_post())

    assert context["state"] == "error"
    assert context["load_error"] == "Plan not found"


def test_the_posted_cart_and_route_context_reach_the_source():
    source, received = fake_source()
    form, _api = _form(source)
    cart = [{"type": "PLAN", "id": "p", "name": "Pro", "price": 9, "quantity": 1}]

    form.context(_post(cart=json.dumps(cart), tarif_plan_id="pro"))

    loaded_context = received["load"][0]
    assert loaded_context.source == "fake"
    assert loaded_context.plan_slug == "pro"
    assert [dict(item) for item in loaded_context.cart_items] == cart


def test_a_corrupt_cart_is_an_empty_cart():
    source, received = fake_source()
    form, _api = _form(source)

    form.context(_post(cart="{not json"))

    assert received["load"][0].cart_items == ()


def test_anonymous_buyer_sees_the_sign_in_path_and_auto_selected_first_method():
    form, api = _form()

    context = form.context(_post())

    assert context["state"] == "form"
    assert context["buyer"] is None
    assert context["route_fields"] == {
        "source": "fake",
        "tarif_plan_id": "",
        "cart_type": "",
        "is_cart": "",
    }
    assert context["has_payable_total"] is True
    assert context["is_pay_zero"] is False
    assert context["order_total"] == "€10.00"
    assert context["payment"]["selected_code"] == "stripe"
    assert [method["code"] for method in context["payment"]["methods"]] == [
        "stripe",
        "invoice",
    ]
    assert api.called("payment_methods") == [("payment_methods", "EUR")]
    assert context["billing"]["countries"] == [{"code": "DE", "name": "Germany"}]
    assert context["requirements"] == ["signIn", "billingAddress", "acceptTerms"]
    assert api.called("profile") == []


def test_logged_in_buyer_gets_profile_email_name_and_saved_billing():
    api = FakeCheckoutApi(profile=PROFILE, user_details=SAVED_DETAILS)
    form, _ = _form(api=api)

    context = form.context(_post())

    assert context["buyer"] == {"email": "buyer@example.com", "name": "Ada Lovelace"}
    assert context["billing"]["values"]["street"] == "1 Analytical St"
    assert context["billing"]["values"]["zip"] == "N1"
    assert context["billing"]["values"]["country"] == "GB"
    assert context["requirements"] == ["acceptTerms"]


def test_a_refused_profile_is_an_anonymous_buyer():
    api = FakeCheckoutApi(profile=ThemeApiError(401, "expired"))
    api.has_bearer = lambda: True
    form, _ = _form(api=api)

    assert form.context(_post())["buyer"] is None


def test_posted_state_wins_over_the_defaults():
    api = FakeCheckoutApi(profile=PROFILE, user_details=SAVED_DETAILS)
    form, _ = _form(api=api)

    context = form.context(
        _post(
            billing_street="2 Posted Rd",
            billing_city="Paris",
            payment_method="invoice",
            terms="on",
        )
    )

    assert context["billing"]["values"]["street"] == "2 Posted Rd"
    assert context["billing"]["values"]["city"] == "Paris"
    assert context["payment"]["selected_code"] == "invoice"
    assert context["payment"]["instructions"] == "Pay within 14 days"
    assert context["terms"]["accepted"] is True
    assert context["requirements"] == []


def _discounting_source(valid_code="SUMMER2026"):
    def load_summary(theme_request, route_context):
        if route_context.coupon_code == valid_code:
            return CheckoutSummary(
                line_items=(),
                order_total=Decimal("8.00"),
                currency="EUR",
                discount_amount=Decimal("2.00"),
                applied_coupon_code=valid_code,
            )
        error = "Invalid coupon" if route_context.coupon_code else None
        return CheckoutSummary(
            line_items=(),
            order_total=Decimal("10.00"),
            currency="EUR",
            coupon_error=error,
        )

    source, received = fake_source()
    return (
        source.__class__(**{**source.__dict__, "load_summary": load_summary}),
        received,
    )


def test_applying_a_valid_coupon_shows_the_discount_and_the_final_price():
    source, _ = _discounting_source()
    form, _api = _form(source)

    context = form.context(
        _post(coupon_action="apply", coupon_input=" SUMMER2026 ", coupon_code="")
    )

    assert context["coupon"] == {"applied_code": "SUMMER2026", "error": None}
    assert context["order_total"] == "€8.00"
    assert context["discount"] == "€2.00"


def test_an_invalid_coupon_shows_its_error_and_keeps_the_total():
    source, _ = _discounting_source()
    form, _api = _form(source)

    context = form.context(_post(coupon_action="apply", coupon_input="NOTACODE123"))

    assert context["coupon"] == {"applied_code": None, "error": "Invalid coupon"}
    assert context["order_total"] == "€10.00"
    assert context["discount"] is None


def test_an_applied_coupon_survives_a_rerender_and_clear_removes_it():
    source, _ = _discounting_source()
    form, _api = _form(source)

    kept = form.context(_post(coupon_code="SUMMER2026"))
    cleared = form.context(_post(coupon_code="SUMMER2026", coupon_action="clear"))

    assert kept["coupon"]["applied_code"] == "SUMMER2026"
    assert cleared["coupon"] == {"applied_code": None, "error": None}


def _priced(total, discount="0"):
    return fake_source(
        summary=CheckoutSummary(
            line_items=(),
            order_total=Decimal(total),
            currency="EUR",
            discount_amount=Decimal(discount),
        )
    )[0]


def test_a_free_order_needs_neither_billing_nor_payment():
    form, api = _form(_priced("0"))

    context = form.context(_post())

    assert context["has_payable_total"] is False
    assert context["is_pay_zero"] is True
    assert api.called("payment_methods") == []
    assert context["requirements"] == ["signIn", "acceptTerms"]


def test_an_order_discounted_to_zero_still_collects_billing_but_no_payment():
    form, api = _form(_priced("0", discount="10"))

    context = form.context(_post())

    assert context["has_payable_total"] is True
    assert context["is_pay_zero"] is True
    assert api.called("payment_methods") == []
    assert "billingAddress" in context["requirements"]


def test_a_payment_methods_failure_shows_the_spa_error():
    form, _api = _form(api=FakeCheckoutApi(payment_methods=ThemeApiError(500, "x")))

    payment = form.context(_post())["payment"]

    assert payment["error"] is True
    assert payment["methods"] == []
    assert payment["selected_code"] is None


def test_no_payment_methods_means_the_payment_requirement_stays():
    form, _api = _form(api=FakeCheckoutApi(payment_methods={"methods": []}))

    assert "paymentMethod" in form.context(_post())["requirements"]


def test_a_countries_failure_falls_back_to_the_spa_list():
    form, _api = _form(api=FakeCheckoutApi(countries=ThemeApiError(500, "x")))

    countries = form.context(_post())["billing"]["countries"]

    assert countries == FALLBACK_COUNTRIES
    assert [country["code"] for country in countries] == ["DE", "AT", "CH", "US", "GB"]


@pytest.mark.parametrize(
    "markdown, expected_html",
    [
        ("plain", "<p>plain</p>"),
        ("## Title\n\nBody", "<p><h3>Title</h3></p><p>Body</p>"),
        ("### Sub", "<p><h4>Sub</h4></p>"),
        ("- one\n- two", "<p><li>one</li>\n<li>two</li></p>"),
        (
            "<script>x</script> & 'q'",
            "<p>&lt;script&gt;x&lt;/script&gt; &amp; &#039;q&#039;</p>",
        ),
    ],
)
def test_terms_render_like_the_spa_terms_checkbox(markdown, expected_html):
    assert render_terms_html(markdown) == expected_html


def test_a_terms_failure_shows_the_failed_to_load_copy_key():
    form, _api = _form(api=FakeCheckoutApi(terms=ThemeApiError(500, "x")))

    terms = form.context(_post())["terms"]

    assert terms["title"] is None
    assert terms["content_html"] is None
