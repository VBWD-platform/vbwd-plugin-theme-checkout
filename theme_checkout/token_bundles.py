"""The ``TokenBundleCollection`` CMS component (cards view) — ``TokenBundleCollection.vue``.

Each card's "Add to Cart" carries the exact fe-core cart item the SPA's
``addToCart`` builds; the checkout runtime adds it to ``vbwd_cart`` and goes to
``/checkout?source=subscription``.
"""
from typing import Any, Callable, Dict, List, Mapping, Optional

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme_cms.theme_cms.components.pricing import format_money

from .checkout_api import CheckoutApi

TOKEN_BUNDLE_CART_TYPE = "TOKEN_BUNDLE"
NETTO = "netto"
BRUTTO = "brutto"
DEFAULT_DISPLAY_MODE = BRUTTO


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _price_vo(bundle: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    return (bundle.get("price_info") or {}).get("price")


def _net_price(bundle: Mapping[str, Any]) -> float:
    price_vo = _price_vo(bundle)
    if price_vo and price_vo.get("netto") is not None:
        return _number(price_vo["netto"])
    return _number(bundle.get("price"))


def _display_price(bundle: Mapping[str, Any]) -> str:
    """``formatBundlePrice`` → ``resolvePriceDisplay`` (no account type server-side)."""
    price_vo = _price_vo(bundle)
    if not price_vo:
        return format_money(_number(bundle.get("price")), bundle.get("currency"))
    side = (
        bundle.get("effective_display_mode")
        or bundle.get("prices_display_mode")
        or DEFAULT_DISPLAY_MODE
    )
    amount = price_vo.get("netto") if side == NETTO else price_vo.get("brutto")
    return format_money(amount, price_vo.get("currency") or bundle.get("currency"))


def _card(bundle: Mapping[str, Any]) -> Dict[str, Any]:
    token_amount = f"{int(_number(bundle.get('token_amount'))):,}"
    price_vo = _price_vo(bundle)
    return {
        "id": bundle.get("id"),
        "token_amount": token_amount,
        "price": _display_price(bundle),
        "description": bundle.get("description") or "",
        "cart_item": {
            "type": TOKEN_BUNDLE_CART_TYPE,
            "id": bundle.get("id"),
            "name": f"{token_amount} Tokens",
            "price": _net_price(bundle),
            "metadata": {
                "token_amount": bundle.get("token_amount"),
                "currency": (price_vo or {}).get("currency") or bundle.get("currency"),
                "price_obj": price_vo,
            },
        },
    }


class TokenBundleCollection:
    """``build_context(widget_config, page, route_params, theme_request)`` of the component."""

    def __init__(
        self, api_factory: Callable[[ThemeRequest], Any] = CheckoutApi
    ) -> None:
        self._api_factory = api_factory

    def build_context(
        self,
        widget_config: Mapping[str, Any],
        page: Mapping[str, Any],
        route_params: Mapping[str, Any],
        theme_request: ThemeRequest,
    ) -> Dict[str, Any]:
        heading = widget_config.get("heading")
        try:
            bundles: List[Mapping[str, Any]] = (
                self._api_factory(theme_request).token_bundles().get("bundles") or []
            )
        except ThemeApiError:
            return {"heading": heading, "state": "error", "bundles": []}
        wanted_ids = widget_config.get("bundle_ids") or []
        if wanted_ids:
            bundles = [bundle for bundle in bundles if bundle.get("id") in wanted_ids]
        cards = [_card(bundle) for bundle in bundles]
        return {
            "heading": heading,
            "state": "cards" if cards else "empty",
            "bundles": cards,
        }
