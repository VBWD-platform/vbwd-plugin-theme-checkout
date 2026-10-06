"""Bot checkout-draft hydration — the twin of fe-user ``plugins/checkout/draftCheckout.ts``.

The draft's server-recomputed line items become the fe-core cart; the page hands
them to the runtime as a ``data-vbwd-cart-write`` directive (the cart is the
browser's single source of truth). No prices are computed here.
"""
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import quote

from plugins.theme.theme.theme_api import NOT_FOUND, ThemeApiError, call_api
from plugins.theme.theme.theme_request import ThemeRequest

DRAFT_API_PATH = "/api/v1/subscription/public/checkout-draft/{token}"
# The core LineItemType a draft persists → the fe-core cart item type.
CART_ITEM_TYPE_BY_LINE_ITEM_TYPE = {
    "SUBSCRIPTION": "PLAN",
    "ADD_ON": "ADD_ON",
    "TOKEN_BUNDLE": "TOKEN_BUNDLE",
}
MINIMUM_QUANTITY = 1


class DraftExpiredError(Exception):
    """The draft token is unknown, expired or already redeemed (404)."""


def _parse_price(raw_price: Optional[str]) -> float:
    try:
        return float(raw_price) if raw_price is not None else 0.0
    except ValueError:
        return 0.0


def _quantity(raw_quantity: Any) -> int:
    try:
        return max(MINIMUM_QUANTITY, int(raw_quantity or 0))
    except (TypeError, ValueError):
        return MINIMUM_QUANTITY


def cart_items_from_draft(
    line_items: Sequence[Mapping[str, Any]], default_currency: str
) -> List[Dict[str, Any]]:
    """``hydrateCartFromDraft``: a cleared cart plus one ``addItem`` per unit."""
    cart: List[Dict[str, Any]] = []
    for line_item in line_items:
        cart_type = CART_ITEM_TYPE_BY_LINE_ITEM_TYPE.get(
            str(line_item.get("item_type") or "")
        )
        if cart_type is None:
            continue
        item_id = line_item.get("item_id")
        existing = next(
            (
                item
                for item in cart
                if item["id"] == item_id and item["type"] == cart_type
            ),
            None,
        )
        if existing is not None:
            existing["quantity"] += _quantity(line_item.get("quantity"))
            continue
        cart.append(
            {
                "type": cart_type,
                "id": item_id,
                "name": line_item.get("name"),
                "price": _parse_price(line_item.get("unit_price")),
                "metadata": {
                    "plan_id": item_id,
                    "currency": line_item.get("currency") or default_currency,
                },
                "quantity": _quantity(line_item.get("quantity")),
            }
        )
    return cart


def resolve_draft_cart(
    theme_request: ThemeRequest, token: str, default_currency: str
) -> List[Dict[str, Any]]:
    """The cart a draft token seeds; raises :class:`DraftExpiredError` on a 404."""
    try:
        body = call_api(
            theme_request, "GET", DRAFT_API_PATH.format(token=quote(token, safe=""))
        )
    except ThemeApiError as draft_error:
        if draft_error.status == NOT_FOUND:
            raise DraftExpiredError() from draft_error
        raise
    return cart_items_from_draft(body.get("line_items") or [], default_currency)
