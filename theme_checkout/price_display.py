"""The server twin of fe-user ``PriceDisplay.vue`` / ``utils/priceDisplay.ts`` (S152-08).

Every themed sellable price (shop products and cart lines, plan cards, the
checkout summaries) picks its side here: ``netto`` shows the net amount,
``brutto`` (the default) the gross one, and the "netto price" tag marks a net
amount under a brutto global. Themed pages render anonymously (D4), so the
business-viewer overlay (S74) and the display-currency switch (S99.4) — both
viewer state the SPA reads client-side — do not apply.
"""
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from plugins.theme_cms.theme_cms.components.pricing import format_money

NETTO = "netto"
BRUTTO = "brutto"
DEFAULT_DISPLAY_MODE = BRUTTO


@dataclass(frozen=True)
class PriceDisplayView:
    """What ``checkout/_price_display.html.j2`` renders."""

    label: str
    show_netto_tag: bool


def resolve_price_display(
    net_amount: Any,
    gross_amount: Any,
    effective_display_mode: Optional[str] = None,
    global_mode: Optional[str] = None,
) -> Tuple[Any, bool]:
    """``resolvePriceDisplay``: ``(amount to show, show the netto tag)``."""
    side = effective_display_mode or global_mode or DEFAULT_DISPLAY_MODE
    amount = net_amount if side == NETTO else gross_amount
    return amount, side == NETTO and global_mode == BRUTTO


def price_display_view(
    net_amount: Any,
    gross_amount: Any,
    currency: Optional[str],
    effective_display_mode: Optional[str] = None,
    global_mode: Optional[str] = None,
) -> PriceDisplayView:
    amount, show_netto_tag = resolve_price_display(
        net_amount, gross_amount, effective_display_mode, global_mode
    )
    return PriceDisplayView(format_money(amount, currency), show_netto_tag)
