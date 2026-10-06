"""The confirm fragment — ``checkoutStore.submitCheckout`` plus the post-submit dispatch.

Success ends the htmx flow with ``HX-Redirect`` (``ThemeFragmentRedirect``) to
wherever :func:`dispatch_after_submit` sends the buyer; a refusal renders the
``checkout-form-error`` message.
"""
from typing import Any, Dict, Optional

from plugins.theme.theme.fragment_registry import ThemeFragmentRedirect
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest

from .checkout_blocks import PAYMENT_METHOD_FIELD
from .checkout_form import posted_route_context
from .checkout_sources import CheckoutSourceRegistry
from .payment_methods import CheckoutPaymentMethodRegistry, dispatch_after_submit

NO_ITEMS_SELECTED_KEY = "checkout.errors.noItemsSelected"
CHECKOUT_FAILED_KEY = "checkout.errors.checkoutFailed"


def _error(message: Optional[str] = None, key: Optional[str] = None) -> Dict[str, Any]:
    return {"error_message": message, "error_key": key}


class CheckoutSubmit:
    """Submits through the active source, then redirects per the dispatch table."""

    def __init__(
        self,
        source_registry: CheckoutSourceRegistry,
        payment_method_registry: CheckoutPaymentMethodRegistry,
    ) -> None:
        self._source_registry = source_registry
        self._payment_method_registry = payment_method_registry

    def context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        route_context = posted_route_context(theme_request.query_args)
        source = self._source_registry.find(route_context)
        if source is None:
            return _error(key=NO_ITEMS_SELECTED_KEY)
        payment_method_code = theme_request.query_args.get(PAYMENT_METHOD_FIELD) or None
        try:
            result = source.submit(theme_request, route_context, payment_method_code)
        except ThemeApiError as refusal:
            if refusal.message:
                return _error(message=refusal.message)
            return _error(key=CHECKOUT_FAILED_KEY)
        location = dispatch_after_submit(
            theme_request, result, payment_method_code, self._payment_method_registry
        )
        if location is not None:
            raise ThemeFragmentRedirect(location)
        return _error()
