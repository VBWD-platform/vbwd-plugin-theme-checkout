"""The post-submit dispatch table — the twin of fe-user ``registries/checkoutPaymentMethods.ts``.

A payment flow (``payment/``, or any payment adapter) registers, per payment-method code from the
backend's ``vbwd_payment_method`` table, a ``redirect_path`` (gateway: hop to
its ``/pay/<name>`` page) or an ``instant_pay`` (in-band: finish in one API
call). The checkout names no method; :func:`dispatch_after_submit` mirrors
``PublicCheckoutView.vue:343-369``. An entry counts only while its fe-user
plugin is enabled — the same toggle that governs the SPA entry.
"""
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import quote

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest

from .checkout_sources import running_theme_checkout_plugin

logger = logging.getLogger(__name__)

CONFIRMATION_PATH = "/checkout/confirmation"


@dataclass(frozen=True)
class CheckoutPaymentMethod:
    """``redirect_path(invoice_id)`` and/or ``instant_pay(theme_request, invoice_id)``."""

    code: str
    owner_fe_user_plugin: str
    redirect_path: Optional[Callable[[str], str]] = None
    instant_pay: Optional[Callable[[ThemeRequest, str], Any]] = None

    def __post_init__(self) -> None:
        if self.redirect_path is None and self.instant_pay is None:
            raise ValueError(
                f"checkout payment method '{self.code}' needs a redirect_path or instant_pay"
            )


class CheckoutPaymentMethodRegistry:
    """Method code → entry; a later registration of a code replaces the earlier one."""

    def __init__(self, is_fe_user_plugin_enabled: Callable[[str], bool]) -> None:
        self._is_fe_user_plugin_enabled = is_fe_user_plugin_enabled
        self._entries_by_code: Dict[str, CheckoutPaymentMethod] = {}

    def register(self, entry: CheckoutPaymentMethod) -> None:
        self._entries_by_code[entry.code] = entry

    def get(self, code: str) -> Optional[CheckoutPaymentMethod]:
        """The entry for ``code`` while its fe-user plugin is enabled, else ``None``."""
        entry = self._entries_by_code.get(code)
        if entry is None or not self._is_fe_user_plugin_enabled(
            entry.owner_fe_user_plugin
        ):
            return None
        return entry


def confirmation_url(invoice_id: str) -> str:
    return f"{CONFIRMATION_PATH}?invoice_id={quote(invoice_id, safe='')}"


def dispatch_after_submit(
    theme_request: ThemeRequest,
    checkout_result: Mapping[str, Any],
    payment_method_code: Optional[str],
    registry: CheckoutPaymentMethodRegistry,
) -> Optional[str]:
    """Where the browser goes after a successful submit; ``None`` = stay on the page."""
    invoice_id = (checkout_result.get("invoice") or {}).get("id")
    if not invoice_id:
        return None
    entry = registry.get(payment_method_code) if payment_method_code else None
    if entry is not None and entry.instant_pay is not None:
        try:
            entry.instant_pay(theme_request, str(invoice_id))
        except ThemeApiError as payment_error:
            # As in the SPA: the confirmation page shows the invoice state.
            logger.warning(
                "[theme_checkout] instant pay failed for %s: %s",
                payment_method_code,
                payment_error,
            )
        return confirmation_url(str(invoice_id))
    if entry is not None and entry.redirect_path is not None:
        return entry.redirect_path(str(invoice_id))
    return confirmation_url(str(invoice_id))


def resolve_checkout_payment_method_registry() -> CheckoutPaymentMethodRegistry:
    """The running app's table; payment adapters register their methods here."""
    registry: CheckoutPaymentMethodRegistry = (
        running_theme_checkout_plugin().payment_method_registry
    )
    return registry
