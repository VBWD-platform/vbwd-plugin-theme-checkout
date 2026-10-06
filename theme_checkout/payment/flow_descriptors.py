"""Declarative payment flows (S152 "Payment providers are declarative").

Each provider is a :class:`PaymentFlowDescriptor` — no code per provider. The
generic ``/pay/<provider>`` pages read it; the checkout's dispatch table gets
its ``redirect_path``. A descriptor is active only while its fe-user plugin is
enabled (the theme's owner gate on every page and fragment). Only the
``redirect`` kind is built (stripe, paypal); ``poll`` and ``custom`` come with
their providers in S153 and are refused until then.
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from plugins.theme.theme.theme_api import call_api
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme_checkout.theme_checkout.payment_methods import CheckoutPaymentMethod

PROVIDER_PATTERN = re.compile(r"^[a-z0-9-]+$")
PAY_PATH = "/pay/{provider}"
TOKEN_PAYMENT_PAY_PATH = "/api/v1/plugins/token-payment/invoices/{invoice_id}/pay"


class FlowKind(Enum):
    REDIRECT = "redirect"
    POLL = "poll"
    CUSTOM = "custom"


BUILT_KINDS = (FlowKind.REDIRECT,)


class SuccessHandling(Enum):
    """How the success page confirms: poll ``session-status`` or POST ``capture-order``."""

    POLL_SESSION_STATUS = "poll_session_status"
    CAPTURE_ORDER = "capture_order"


class PaymentFlowRegistrationError(ValueError):
    """A descriptor the registry refuses (bad provider, duplicate, kind not built)."""


@dataclass(frozen=True)
class PaymentFlowDescriptor:
    """One provider's flow. ``translation_namespace`` defaults to ``provider``
    (the fe-user plugin's locale root: ``stripe.*``, ``paypal.*``)."""

    provider: str
    fe_user_plugin: str
    payment_method_code: str
    kind: FlowKind
    api_prefix: str
    success_handling: SuccessHandling
    create_path: str = "/create-session"
    session_url_field: str = "session_url"
    translation_namespace: Optional[str] = None

    @property
    def namespace(self) -> str:
        return self.translation_namespace or self.provider

    @property
    def pay_path(self) -> str:
        return PAY_PATH.format(provider=self.provider)

    def checkout_redirect_path(self, invoice_id: str) -> str:
        """``registerCheckoutPaymentMethod(code, {redirectPath})`` of the SPA plugin."""
        return f"{self.pay_path}?invoice={quote(invoice_id, safe='')}"


class PaymentFlowRegistry:
    """Provider → descriptor, in registration order."""

    def __init__(self) -> None:
        self._descriptors_by_provider: Dict[str, PaymentFlowDescriptor] = {}

    def register(self, descriptor: PaymentFlowDescriptor) -> None:
        if not PROVIDER_PATTERN.match(descriptor.provider):
            raise PaymentFlowRegistrationError(
                f"payment flow provider '{descriptor.provider}' must match {PROVIDER_PATTERN.pattern}"
            )
        if descriptor.kind not in BUILT_KINDS:
            raise PaymentFlowRegistrationError(
                f"payment flow kind '{descriptor.kind.value}' ({descriptor.provider}) is not "
                "built yet — it arrives with its providers in S153"
            )
        if descriptor.provider in self._descriptors_by_provider:
            raise PaymentFlowRegistrationError(
                f"payment flow '{descriptor.provider}' is already registered"
            )
        self._descriptors_by_provider[descriptor.provider] = descriptor

    def descriptors(self) -> List[PaymentFlowDescriptor]:
        return list(self._descriptors_by_provider.values())

    def get(self, provider: str) -> Optional[PaymentFlowDescriptor]:
        return self._descriptors_by_provider.get(provider)


STRIPE_FLOW = PaymentFlowDescriptor(
    provider="stripe",
    fe_user_plugin="stripe-payment",
    payment_method_code="stripe",
    kind=FlowKind.REDIRECT,
    api_prefix="/api/v1/plugins/stripe",
    success_handling=SuccessHandling.POLL_SESSION_STATUS,
)

PAYPAL_FLOW = PaymentFlowDescriptor(
    provider="paypal",
    fe_user_plugin="paypal-payment",
    payment_method_code="paypal",
    kind=FlowKind.REDIRECT,
    api_prefix="/api/v1/plugins/paypal",
    success_handling=SuccessHandling.CAPTURE_ORDER,
)

BUILT_IN_FLOWS = (STRIPE_FLOW, PAYPAL_FLOW)


def _pay_with_token_balance(theme_request: ThemeRequest, invoice_id: str) -> Any:
    """token-payment's ``instantPay``: ``POST /plugins/token-payment/invoices/<id>/pay``."""
    return call_api(
        theme_request,
        "POST",
        TOKEN_PAYMENT_PAY_PATH.format(invoice_id=quote(invoice_id, safe="")),
        json={},
    )


# token-payment registers no page in the SPA: it is an in-band checkout method only.
TOKEN_BALANCE_METHOD = CheckoutPaymentMethod(
    code="token_balance",
    owner_fe_user_plugin="token-payment",
    instant_pay=_pay_with_token_balance,
)
