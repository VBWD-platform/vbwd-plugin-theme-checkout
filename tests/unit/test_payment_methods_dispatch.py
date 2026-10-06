"""S152-07 B — the post-submit dispatch, mirrored from ``PublicCheckoutView.vue:343-369``
over the twin of fe-user ``registries/checkoutPaymentMethods.ts``.

    instantPay   → pay in-band (a failure is logged, not shown), then confirmation
    redirectPath → the plugin's /pay/<name> page
    nothing      → confirmation
    no invoice   → stay (the SPA's watcher returns without navigating)

An entry counts only while its fe-user plugin is enabled (same toggle as the SPA).
"""
import logging

import pytest

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest
from plugins.theme_checkout.theme_checkout.payment_methods import (
    CheckoutPaymentMethod,
    CheckoutPaymentMethodRegistry,
    confirmation_url,
    dispatch_after_submit,
)

INVOICE_ID = "11111111-2222-3333-4444-555555555555"
CONFIRMATION = f"/checkout/confirmation?invoice_id={INVOICE_ID}"


class InstantPayRecorder:
    def __init__(self, error=None):
        self.paid_invoice_ids = []
        self.error = error

    def __call__(self, theme_request, invoice_id):
        self.paid_invoice_ids.append(invoice_id)
        if self.error:
            raise self.error
        return {"status": "PAID"}


def _registry(*entries, disabled_plugins=()):
    registry = CheckoutPaymentMethodRegistry(
        lambda plugin_name: plugin_name not in disabled_plugins
    )
    for entry in entries:
        registry.register(entry)
    return registry


def _redirect(code="stripe"):
    return CheckoutPaymentMethod(
        code=code,
        owner_fe_user_plugin=f"{code}-payment",
        redirect_path=lambda invoice_id: f"/pay/{code}?invoice={invoice_id}",
    )


def _instant(recorder, code="token_balance"):
    return CheckoutPaymentMethod(
        code=code, owner_fe_user_plugin="token-payment", instant_pay=recorder
    )


def _dispatch(registry, method_code, result=None):
    return dispatch_after_submit(
        FakeThemeRequest(),
        result if result is not None else {"invoice": {"id": INVOICE_ID}},
        method_code,
        registry,
    )


def test_confirmation_url_encodes_the_invoice_id():
    assert confirmation_url("a b&c") == "/checkout/confirmation?invoice_id=a%20b%26c"


def test_dispatch_matrix_matches_spa():
    instant = InstantPayRecorder()
    registry = _registry(_redirect("stripe"), _redirect("paypal"), _instant(instant))

    matrix = {
        "stripe": f"/pay/stripe?invoice={INVOICE_ID}",
        "paypal": f"/pay/paypal?invoice={INVOICE_ID}",
        "token_balance": CONFIRMATION,
        "invoice": CONFIRMATION,
        None: CONFIRMATION,
    }

    assert {code: _dispatch(registry, code) for code in matrix} == matrix
    assert instant.paid_invoice_ids == [INVOICE_ID]


def test_instant_pay_wins_over_a_redirect_on_the_same_method():
    instant = InstantPayRecorder()
    both = CheckoutPaymentMethod(
        code="hybrid",
        owner_fe_user_plugin="hybrid-payment",
        redirect_path=lambda invoice_id: "/pay/hybrid",
        instant_pay=instant,
    )

    assert _dispatch(_registry(both), "hybrid") == CONFIRMATION
    assert instant.paid_invoice_ids == [INVOICE_ID]


def test_a_failed_instant_pay_still_lands_on_confirmation(caplog):
    instant = InstantPayRecorder(error=ThemeApiError(400, "Insufficient token balance"))

    with caplog.at_level(logging.WARNING):
        location = _dispatch(_registry(_instant(instant)), "token_balance")

    assert location == CONFIRMATION
    assert "token_balance" in caplog.text


def test_a_result_without_an_invoice_id_stays_on_the_page():
    registry = _registry(_redirect())

    assert _dispatch(registry, "stripe", result={"invoice": {}}) is None
    assert _dispatch(registry, "stripe", result={"message": "x"}) is None


def test_an_entry_of_a_disabled_fe_user_plugin_is_ignored():
    registry = _registry(_redirect("stripe"), disabled_plugins=("stripe-payment",))

    assert registry.get("stripe") is None
    assert _dispatch(registry, "stripe") == CONFIRMATION


def test_a_later_registration_of_a_code_replaces_the_earlier_one():
    registry = _registry(_redirect("stripe"))
    replacement = CheckoutPaymentMethod(
        code="stripe",
        owner_fe_user_plugin="stripe-payment",
        redirect_path=lambda invoice_id: "/pay/stripe-v2",
    )
    registry.register(replacement)

    assert registry.get("stripe") is replacement


def test_an_entry_needs_a_redirect_or_an_instant_pay():
    with pytest.raises(ValueError, match="redirect_path or instant_pay"):
        CheckoutPaymentMethod(code="empty", owner_fe_user_plugin="x")


def test_resolve_reads_the_running_theme_checkout_plugin():
    from types import SimpleNamespace

    from flask import Flask

    from plugins.theme_checkout.theme_checkout.payment_methods import (
        resolve_checkout_payment_method_registry,
    )

    registry = _registry()
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(
        get_plugin=lambda name: SimpleNamespace(payment_method_registry=registry)
        if name == "theme_checkout"
        else None
    )

    with app.app_context():
        assert resolve_checkout_payment_method_registry() is registry
