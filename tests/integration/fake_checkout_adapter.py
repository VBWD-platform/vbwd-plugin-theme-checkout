"""A test-only selling adapter: a cart-backed checkout source plus two payment methods.

``source=fake`` prices the posted fe-core cart (sum of price × quantity);
coupon ``TENOFF`` takes 10 % off, any other code is "Invalid coupon"; submit
answers the invoice id the test put in ``FAKE_SUBMIT_RESULT``. ``fakepay`` is a
redirect method, ``fakeinstant`` an instant pay that records the invoice ids.
Nothing here ships in production code.
"""
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from vbwd.plugins.base import BasePlugin, PluginMetadata

from plugins.theme.theme.page_registry import resolve_theme_plugin
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutSource,
    CheckoutSummary,
    resolve_checkout_source_registry,
)
from plugins.theme_checkout.theme_checkout.payment_methods import (
    CheckoutPaymentMethod,
    resolve_checkout_payment_method_registry,
)

FAKE_CHECKOUT_ADAPTER_NAME = "fake_checkout_adapter"
FAKE_TEMPLATES_DIRECTORY = Path(__file__).parent / "fake_templates"
VALID_COUPON = "TENOFF"
COUPON_RATE = Decimal("0.10")
CENTS = Decimal("0.01")
FAKE_SUBMIT_RESULT: Dict[str, Any] = {"invoice": {"id": "fake-invoice"}}
instant_paid_invoice_ids: List[str] = []


def _load_summary(theme_request, route_context) -> CheckoutSummary:
    gross = sum(
        Decimal(str(item.get("price", 0))) * int(item.get("quantity", 1))
        for item in route_context.cart_items
    )
    lines = tuple(route_context.cart_items)
    if route_context.coupon_code == VALID_COUPON:
        discount = (gross * COUPON_RATE).quantize(CENTS)
        return CheckoutSummary(
            line_items=lines,
            order_total=gross - discount,
            currency="EUR",
            discount_amount=discount,
            applied_coupon_code=VALID_COUPON,
        )
    error = "Invalid coupon" if route_context.coupon_code else None
    return CheckoutSummary(
        line_items=lines, order_total=gross, currency="EUR", coupon_error=error
    )


def _submit(theme_request, route_context, payment_method_code) -> Dict[str, Any]:
    return FAKE_SUBMIT_RESULT


def _instant_pay(theme_request, invoice_id):
    instant_paid_invoice_ids.append(invoice_id)


FAKE_SOURCE = CheckoutSource(
    id="fake",
    matches=lambda route_context: route_context.source == "fake",
    load_summary=_load_summary,
    submit=_submit,
    summary_template="fake_checkout/summary.html.j2",
)


class FakeCheckoutAdapterPlugin(BasePlugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name=FAKE_CHECKOUT_ADAPTER_NAME,
            version="1.0.0",
            author="Test",
            description="Test-only selling adapter",
            dependencies=["theme_checkout"],
        )

    def on_enable(self) -> None:
        resolve_theme_plugin().theme_registry.add_contributed_template_path(
            FAKE_TEMPLATES_DIRECTORY
        )
        resolve_checkout_source_registry().register(FAKE_SOURCE)
        methods = resolve_checkout_payment_method_registry()
        methods.register(
            CheckoutPaymentMethod(
                code="fakepay",
                owner_fe_user_plugin="checkout",
                redirect_path=lambda invoice_id: f"/pay/fake?invoice={invoice_id}",
            )
        )
        methods.register(
            CheckoutPaymentMethod(
                code="fakeinstant",
                owner_fe_user_plugin="checkout",
                instant_pay=_instant_pay,
            )
        )
