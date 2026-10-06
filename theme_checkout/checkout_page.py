"""The ``/checkout`` page — the state branches of fe-user ``PublicCheckoutView``.

The source match needs only the query, so the page decides server-side between
``checkout-no-plan``, ``checkout-draft-expired``, ``checkout-error`` and the
island placeholder (filled by :class:`CheckoutForm` once the runtime posts the
cart). A resolved bot draft hands its cart to the runtime as a
``data-vbwd-cart-write`` directive.
"""
from typing import Any, Callable, Dict, List, Optional

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest

from .checkout_api import CheckoutApi
from .checkout_form import route_fields
from .checkout_sources import CheckoutRouteContext, CheckoutSourceRegistry
from .draft import DraftExpiredError, resolve_draft_cart

DRAFT_PARAMETER = "draft"
PAGE_TITLE = "Checkout"


class CheckoutPage:
    """Builds the ``/checkout`` page context."""

    def __init__(
        self,
        source_registry: CheckoutSourceRegistry,
        api_factory: Callable[[ThemeRequest], Any] = CheckoutApi,
    ) -> None:
        self._source_registry = source_registry
        self._api_factory = api_factory

    def context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        draft_token = theme_request.query_args.get(DRAFT_PARAMETER)
        if not draft_token:
            return self._state(
                CheckoutRouteContext.from_query(theme_request.query_args)
            )
        try:
            cart = resolve_draft_cart(
                theme_request,
                draft_token,
                self._api_factory(theme_request).default_currency(),
            )
        except DraftExpiredError:
            return {
                "page_title": PAGE_TITLE,
                "state": "draft_expired",
                "cart_write": None,
            }
        except ThemeApiError as draft_error:
            return {
                "page_title": PAGE_TITLE,
                "state": "error",
                "load_error": draft_error.message,
                "cart_write": None,
            }
        return self._state(CheckoutRouteContext.for_draft(), cart)

    def _state(
        self,
        route_context: CheckoutRouteContext,
        cart: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        source = self._source_registry.find(route_context)
        if source is None:
            return {"page_title": PAGE_TITLE, "state": "no_plan", "cart_write": cart}
        return {
            "page_title": PAGE_TITLE,
            "state": "island",
            "route_fields": route_fields(route_context),
            "cart_key": source.cart_key,
            "cart_write": cart,
        }
