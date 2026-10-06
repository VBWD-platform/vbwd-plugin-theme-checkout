"""S152-08 — one home for the sources' coupon pricing (shop + subscription, DRY).

The twin of the SPA sources' ``applyCoupon``: ``POST /api/v1/coupons/validate``
``{code, cart_total, scope}``; a valid answer grants ``discount_amount``, an
invalid one reports its ``error`` and grants nothing. A refused call (e.g. the
discount plugin is absent) reports the API message, as the SPA's catch does.
"""
from decimal import Decimal

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest, ScriptedApi
from plugins.theme_checkout.theme_checkout import checkout_api
from plugins.theme_checkout.theme_checkout.checkout_api import CheckoutApi
from plugins.theme_checkout.theme_checkout.coupon import (
    NO_COUPON,
    CouponOutcome,
    price_coupon,
)

VALIDATE_PATH = "/api/v1/coupons/validate"


def _api(monkeypatch, answer):
    scripted = ScriptedApi({("POST", VALIDATE_PATH): answer})
    monkeypatch.setattr(checkout_api, "call_api", scripted)
    return CheckoutApi(FakeThemeRequest()), scripted


def test_no_code_prices_nothing_and_calls_nothing(monkeypatch):
    api, scripted = _api(monkeypatch, {"valid": True})

    assert price_coupon(api, None, Decimal("30"), "ECOMMERCE") is NO_COUPON
    assert NO_COUPON == CouponOutcome(Decimal("0"), None, None)
    assert scripted.calls == []


def test_a_valid_code_grants_its_discount(monkeypatch):
    api, scripted = _api(monkeypatch, {"valid": True, "discount_amount": "6.00"})

    outcome = price_coupon(api, "SUMMER", Decimal("30.00"), "SUBSCRIPTION")

    assert outcome == CouponOutcome(Decimal("6.00"), "SUMMER", None)
    assert scripted.calls == [
        (
            "POST",
            VALIDATE_PATH,
            {"json": {"code": "SUMMER", "cart_total": 30.0, "scope": "SUBSCRIPTION"}},
        )
    ]


def test_an_invalid_code_reports_its_error_and_grants_nothing(monkeypatch):
    api, _scripted = _api(monkeypatch, {"valid": False, "error": "Coupon expired"})

    assert price_coupon(api, "OLD", Decimal("30"), "ECOMMERCE") == CouponOutcome(
        Decimal("0"), None, "Coupon expired"
    )


def test_a_refused_validation_reports_the_api_message(monkeypatch):
    api, _scripted = _api(monkeypatch, ThemeApiError(404, "Not found"))

    assert price_coupon(api, "X", Decimal("30"), "ECOMMERCE") == CouponOutcome(
        Decimal("0"), None, "Not found"
    )
