"""Coupon pricing for checkout sources — the SPA sources' ``applyCoupon`` (S152-08).

Shop and subscription validate the buyer's code the same way, each with its own
scope (``ECOMMERCE`` / ``SUBSCRIPTION``), so the call lives here once. The
result feeds a :class:`CheckoutSummary` (discount, applied code, error).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from plugins.theme.theme.theme_api import ThemeApiError

ZERO = Decimal("0")


@dataclass(frozen=True)
class CouponOutcome:
    """What a coupon code does to an order: discount, the code applied, the error shown."""

    discount_amount: Decimal
    applied_code: Optional[str]
    error: Optional[str]


NO_COUPON = CouponOutcome(ZERO, None, None)


def price_coupon(
    api: Any, coupon_code: Optional[str], gross_total: Decimal, scope: str
) -> CouponOutcome:
    """``POST /coupons/validate`` for ``coupon_code`` (no code → :data:`NO_COUPON`)."""
    if not coupon_code:
        return NO_COUPON
    try:
        response = api.validate_coupon(coupon_code, float(gross_total), scope)
    except ThemeApiError as refusal:
        return CouponOutcome(ZERO, None, refusal.message)
    if not response.get("valid"):
        return CouponOutcome(ZERO, None, response.get("error"))
    return CouponOutcome(
        Decimal(str(response.get("discount_amount") or ZERO)), coupon_code, None
    )
