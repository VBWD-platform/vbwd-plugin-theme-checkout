"""The checkout island — the body of fe-user ``PublicCheckoutView`` as an htmx fragment.

The page cannot know the browser's cart, so the form is an island: the runtime
POSTs it with the fe-core cart (``data-vbwd-cart``) and, when logged in, the
bearer. Every interaction (coupon apply/clear, an inline login) re-posts the
whole form and the island re-renders from the posted state. The active
:class:`CheckoutSource` prices the order; this module only orchestrates.
"""
import json
from decimal import Decimal
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from markupsafe import Markup

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme_cms.theme_cms.components.pricing import format_money

from .checkout_api import CheckoutApi
from .checkout_blocks import (
    is_billing_complete,
    load_billing,
    load_buyer,
    load_payment_methods,
    load_terms,
)
from .checkout_sources import (
    PLAN_SLUG_PARAMETER,
    SOURCE_PARAMETER,
    CheckoutRouteContext,
    CheckoutSource,
    CheckoutSourceRegistry,
    CheckoutSummary,
)

CART_FIELD = "cart"
CART_TYPE_FIELD = "cart_type"
IS_CART_FIELD = "is_cart"
COUPON_CODE_FIELD = "coupon_code"
COUPON_INPUT_FIELD = "coupon_input"
COUPON_ACTION_FIELD = "coupon_action"
APPLY_COUPON = "apply"
CLEAR_COUPON = "clear"
ZERO = Decimal("0")

ApiFactory = Callable[[ThemeRequest], Any]


def _cart_items(raw_cart: Optional[str]) -> Tuple[Mapping[str, Any], ...]:
    """The posted ``vbwd_cart`` (a bare JSON array, like the SPA store); else empty."""
    try:
        items = json.loads(raw_cart or "[]")
    except ValueError:
        return ()
    return (
        tuple(item for item in items if isinstance(item, dict))
        if isinstance(items, list)
        else ()
    )


def _coupon_code(form: Mapping[str, Any]) -> Optional[str]:
    action = form.get(COUPON_ACTION_FIELD)
    if action == CLEAR_COUPON:
        return None
    if action == APPLY_COUPON:
        return (form.get(COUPON_INPUT_FIELD) or "").strip() or None
    return form.get(COUPON_CODE_FIELD) or None


def posted_route_context(form: Mapping[str, Any]) -> CheckoutRouteContext:
    """The route context the page put in hidden fields, plus the cart and coupon."""
    return CheckoutRouteContext(
        source=form.get(SOURCE_PARAMETER) or None,
        plan_slug=form.get(PLAN_SLUG_PARAMETER) or None,
        cart_type=form.get(CART_TYPE_FIELD) or None,
        is_cart=bool(form.get(IS_CART_FIELD)),
        cart_items=_cart_items(form.get(CART_FIELD)),
        coupon_code=_coupon_code(form),
    )


def route_fields(route_context: CheckoutRouteContext) -> Dict[str, str]:
    """Hidden fields that carry the route context through every island re-post."""
    return {
        SOURCE_PARAMETER: route_context.source or "",
        PLAN_SLUG_PARAMETER: route_context.plan_slug or "",
        CART_TYPE_FIELD: route_context.cart_type or "",
        IS_CART_FIELD: "1" if route_context.is_cart else "",
    }


def missing_requirements(
    buyer: Optional[Mapping[str, Any]],
    summary_flags: Mapping[str, bool],
    billing_values: Mapping[str, str],
    payment: Mapping[str, Any],
    terms_accepted: bool,
) -> List[str]:
    """``missingRequirements`` — the keys of ``checkout.requirements.*``."""
    missing = []
    if buyer is None:
        missing.append("signIn")
    if summary_flags["has_payable_total"] and not is_billing_complete(billing_values):
        missing.append("billingAddress")
    if not summary_flags["is_pay_zero"] and not payment.get("selected_code"):
        missing.append("paymentMethod")
    if not terms_accepted:
        missing.append("acceptTerms")
    return missing


class CheckoutForm:
    """Builds the island context for one posted checkout form."""

    def __init__(
        self,
        source_registry: CheckoutSourceRegistry,
        api_factory: ApiFactory = CheckoutApi,
    ) -> None:
        self._source_registry = source_registry
        self._api_factory = api_factory

    def context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        route_context = posted_route_context(theme_request.query_args)
        source = self._source_registry.find(route_context)
        if source is None:
            return {"state": "no_plan"}
        try:
            summary = source.load_summary(theme_request, route_context)
        except ThemeApiError as load_error:
            return {"state": "error", "load_error": load_error.message}
        return self._form_context(theme_request, route_context, source, summary)

    def _form_context(
        self,
        theme_request: ThemeRequest,
        route_context: CheckoutRouteContext,
        source: CheckoutSource,
        summary: CheckoutSummary,
    ) -> Dict[str, Any]:
        form = theme_request.query_args
        api = self._api_factory(theme_request)
        flags = {
            "has_payable_total": summary.order_total + summary.discount_amount > ZERO,
            "is_pay_zero": summary.order_total == ZERO,
        }
        buyer = load_buyer(api)
        billing = load_billing(api, form, is_logged_in=buyer is not None)
        payment = (
            load_payment_methods(api, summary.currency, form)
            if not flags["is_pay_zero"]
            else {
                "methods": [],
                "selected_code": None,
                "error": False,
                "instructions": None,
            }
        )
        terms = load_terms(api, form)
        if terms["content_html"] is not None:
            terms["content_html"] = Markup(terms["content_html"])
        return {
            "state": "form",
            **flags,
            "route_fields": route_fields(route_context),
            "summary_template": source.summary_template,
            "summary": {"line_items": summary.line_items, **summary.template_context},
            "currency": summary.currency,
            "order_total": format_money(summary.order_total, summary.currency),
            "discount": (
                format_money(summary.discount_amount, summary.currency)
                if summary.discount_amount > ZERO
                else None
            ),
            "coupon": {
                "applied_code": summary.applied_coupon_code,
                "error": summary.coupon_error,
            },
            "buyer": buyer,
            "billing": billing,
            "payment": payment,
            "terms": terms,
            "requirements": missing_requirements(
                buyer, flags, billing["values"], payment, terms["accepted"]
            ),
        }
