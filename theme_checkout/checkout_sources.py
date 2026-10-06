"""``CheckoutSourceRegistry`` — the twin of fe-user ``registries/checkoutSourceRegistry.ts``.

Keeps the themed checkout agnostic of WHAT is bought. Each adapter that sells
something (theme_subscription plans, the theme_shop cart, theme_dataset, …)
registers a :class:`CheckoutSource` from ``on_enable``: whether it handles the
route context, how to price its items into a :class:`CheckoutSummary` (through
the same public API the SPA source calls), how to submit, and the template that
renders its order-summary lines. The checkout names no source.

Server-side the summary is stateless: the applied coupon travels in the route
context and the source prices with it (the SPA's ``applyCoupon`` +
``getOrderTotal`` + ``getDiscountAmount`` in one call).
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from flask import current_app

from plugins.theme.theme.theme_request import ThemeRequest

THEME_CHECKOUT_PLUGIN_NAME = "theme_checkout"
SOURCE_PARAMETER = "source"
PLAN_SLUG_PARAMETER = "tarif_plan_id"
DRAFT_CART_TYPE = "subscription"
# The fe-core cart (``vbwd_cart``) — what a source checks out unless it names its own.
CORE_CART_KEY = "vbwd_cart"
ZERO = Decimal("0")


@dataclass(frozen=True)
class CheckoutRouteContext:
    """What the checkout is for (``CheckoutRouteContext`` in the SPA).

    ``cart_items`` is the fe-core cart (``vbwd_cart``) the runtime posts with each
    checkout fragment request; ``coupon_code`` the coupon the buyer applied.
    """

    source: Optional[str] = None
    plan_slug: Optional[str] = None
    cart_type: Optional[str] = None
    is_cart: bool = False
    cart_items: Tuple[Mapping[str, Any], ...] = field(default=(), compare=False)
    coupon_code: Optional[str] = field(default=None, compare=False)

    @classmethod
    def from_query(cls, query_args: Mapping[str, Any]) -> "CheckoutRouteContext":
        """``PublicCheckoutView``: ``?source=…`` and ``?tarif_plan_id=…``."""
        return cls(
            source=query_args.get(SOURCE_PARAMETER) or None,
            plan_slug=query_args.get(PLAN_SLUG_PARAMETER) or None,
        )

    @classmethod
    def for_draft(cls) -> "CheckoutRouteContext":
        """A bot draft checks out as the subscription cart."""
        return cls(cart_type=DRAFT_CART_TYPE, is_cart=True)


@dataclass(frozen=True)
class CheckoutSummary:
    """A source's priced order: lines, the NET total (after any discount), currency.

    ``template_context`` is handed to the source's ``summary_template``.
    ``applied_coupon_code`` / ``coupon_error`` report the context's coupon; a
    source without coupon support leaves both ``None`` (the SPA's no-op).
    """

    line_items: Tuple[Mapping[str, Any], ...]
    order_total: Decimal
    currency: str
    discount_amount: Decimal = ZERO
    applied_coupon_code: Optional[str] = None
    coupon_error: Optional[str] = None
    template_context: Mapping[str, Any] = field(default_factory=dict)


SummaryLoader = Callable[[ThemeRequest, CheckoutRouteContext], CheckoutSummary]
# (theme_request, context, payment method code) -> the checkout result ({"invoice": {"id": …}})
CheckoutSubmitter = Callable[
    [ThemeRequest, CheckoutRouteContext, Optional[str]], Mapping[str, Any]
]


@dataclass(frozen=True)
class CheckoutSource:
    """One purchasable domain. ``load_summary`` / ``submit`` raise ``ThemeApiError``
    on an API refusal; its message is what the buyer sees (``checkout-error`` /
    ``checkout-form-error``). ``cart_key`` is the browser cart the island posts
    (and empties after a successful submit); ``None`` for a source with no cart.
    """

    id: str
    matches: Callable[[CheckoutRouteContext], bool]
    load_summary: SummaryLoader
    submit: CheckoutSubmitter
    summary_template: str
    priority: int = 0
    cart_key: Optional[str] = CORE_CART_KEY


class CheckoutSourceRegistry:
    """Source id → :class:`CheckoutSource`; a re-registration of an id replaces it."""

    def __init__(self) -> None:
        self._sources_by_id: Dict[str, CheckoutSource] = {}

    def register(self, source: CheckoutSource) -> None:
        self._sources_by_id[source.id] = source

    def get(self, source_id: str) -> Optional[CheckoutSource]:
        return self._sources_by_id.get(source_id)

    def find(self, context: CheckoutRouteContext) -> Optional[CheckoutSource]:
        """The highest-priority matching source; on a tie the first registered."""
        best: Optional[CheckoutSource] = None
        for source in self._sources_by_id.values():
            if source.matches(context) and (
                best is None or source.priority > best.priority
            ):
                best = source
        return best


def running_theme_checkout_plugin() -> Any:
    """The running app's theme_checkout plugin (raises ``LookupError`` when absent)."""
    plugin_manager = getattr(current_app, "plugin_manager")
    theme_checkout_plugin = plugin_manager.get_plugin(THEME_CHECKOUT_PLUGIN_NAME)
    if theme_checkout_plugin is None:
        raise LookupError("theme_checkout plugin is not installed")
    return theme_checkout_plugin


def resolve_checkout_source_registry() -> CheckoutSourceRegistry:
    """The running app's registry; selling adapters register their sources here."""
    registry: CheckoutSourceRegistry = running_theme_checkout_plugin().source_registry
    return registry
