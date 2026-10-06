"""The page and fragment contexts of one :class:`PaymentFlowDescriptor`.

Mirrors the SPA views: ``<Provider>PaymentView`` + ``usePaymentRedirect`` (create
→ provider URL), ``StripeSuccessView`` + ``usePaymentStatus`` (poll every 2 s, 15
attempts, then the confirmation), ``PayPalSuccessView`` (capture) and the cancel
view. Polling is an htmx chain: each status answer carries the next request,
so the server stays stateless. An inner 401 is re-raised so the fragment
answers 401 and the runtime ends the session (D4).
"""
from typing import Any, Callable, Dict, Optional

from plugins.theme.theme.fragment_registry import ThemeFragmentRedirect
from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme_checkout.theme_checkout.payment_methods import (
    CONFIRMATION_PATH,
    confirmation_url,
)

from .flow_descriptors import PaymentFlowDescriptor, SuccessHandling
from .provider_api import ProviderApi

FRAGMENT_URL = "/_render/_fragment/pay/{provider}/{action}"
MAXIMUM_STATUS_ATTEMPTS = 15
STATUS_POLL_DELAY = "2s"
CONFIRMED_STATUSES = ("complete", "paid", "succeeded")
ALREADY_CAPTURED_MARKERS = ("already", "completed")
UNAUTHORIZED = 401
NO_REDIRECT_URL_KEY = "payment.errors.noRedirectUrl"
SESSION_FAILED_KEY = "payment.errors.sessionFailed"
NO_SESSION_KEY = "payment.errors.noSession"
STATUS_FAILED_KEY = "payment.errors.statusFailed"
NO_ORDER_TOKEN_KEY = "payment.errors.noOrderToken"
CAPTURE_FAILED_KEY = "payment.errors.captureFailed"

ProviderApiFactory = Callable[[PaymentFlowDescriptor, ThemeRequest], Any]


def _reraise_unauthorized(refusal: ThemeApiError) -> None:
    if refusal.status == UNAUTHORIZED:
        raise refusal


def _error_fields(refusal: ThemeApiError, default_key: str) -> Dict[str, Optional[str]]:
    """``err.response.data.error || err.message || '<default>'``."""
    return {
        "error_message": refusal.message or None,
        "error_key": None if refusal.message else default_key,
    }


def _attempt(raw_attempt: Any) -> int:
    try:
        return max(int(raw_attempt), 0)
    except (TypeError, ValueError):
        return 0


def _confirmation(invoice_id: str) -> str:
    return confirmation_url(invoice_id) if invoice_id else CONFIRMATION_PATH


class PaymentFlowPages:
    """Contexts of ``/pay/<provider>``, ``…/success``, ``…/cancel`` and their fragments."""

    def __init__(
        self,
        descriptor: PaymentFlowDescriptor,
        api_factory: ProviderApiFactory = ProviderApi,
    ) -> None:
        self._descriptor = descriptor
        self._api_factory = api_factory

    def _base(self, **fields: Any) -> Dict[str, Any]:
        return {
            "provider": self._descriptor.provider,
            "translation_namespace": self._descriptor.namespace,
            "page_title": "",
            "success_handling": self._descriptor.success_handling.value,
            **fields,
        }

    def fragment_url(self, action: str) -> str:
        return FRAGMENT_URL.format(provider=self._descriptor.provider, action=action)

    def pay_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        return self._base(
            invoice_id=theme_request.query_args.get("invoice") or "",
            create_url=self.fragment_url("create"),
        )

    def create_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        invoice_id = theme_request.query_args.get("invoice_id") or ""
        base = self._base(invoice_id=invoice_id, create_url=self.fragment_url("create"))
        try:
            session = self._api_factory(self._descriptor, theme_request).create_session(
                invoice_id
            )
        except ThemeApiError as refusal:
            _reraise_unauthorized(refusal)
            return {**base, **_error_fields(refusal, SESSION_FAILED_KEY)}
        session_url = session.get(self._descriptor.session_url_field)
        if not session_url:
            return {**base, "error_message": None, "error_key": NO_REDIRECT_URL_KEY}
        raise ThemeFragmentRedirect(session_url)

    def success_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        query = theme_request.query_args
        if self._descriptor.success_handling is SuccessHandling.CAPTURE_ORDER:
            return self._capture_success_context(query)
        session_id = query.get("session_id")
        if not session_id:
            return self._base(
                state="error", error_message=None, error_key=NO_SESSION_KEY
            )
        return self._base(
            state="verifying", poll=self._poll(session_id, 0, "", delay=None)
        )

    def _capture_success_context(self, query: Any) -> Dict[str, Any]:
        if query.get("subscription_id"):
            return self._base(state="confirmed")
        order_id = query.get("token")
        if not order_id:
            return self._base(
                state="error", error_message=None, error_key=NO_ORDER_TOKEN_KEY
            )
        return self._base(
            state="capturing",
            capture={"url": self.fragment_url("capture"), "order_id": order_id},
        )

    def _poll(
        self, session_id: str, attempt: int, invoice_id: str, delay: Optional[str]
    ) -> Dict[str, Any]:
        return {
            "url": self.fragment_url("status"),
            "session_id": session_id,
            "attempt": attempt,
            "invoice_id": invoice_id,
            "delay": delay,
        }

    def status_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        query = theme_request.query_args
        session_id = query.get("session_id") or ""
        attempt = _attempt(query.get("attempt"))
        invoice_id = query.get("invoice_id") or ""
        if attempt > MAXIMUM_STATUS_ATTEMPTS:
            raise ThemeFragmentRedirect(_confirmation(invoice_id))
        if attempt == MAXIMUM_STATUS_ATTEMPTS:
            return self._base(
                state="timed_out",
                confirmation_url=_confirmation(invoice_id),
                poll=self._poll(session_id, attempt + 1, invoice_id, STATUS_POLL_DELAY),
            )
        try:
            status = self._api_factory(self._descriptor, theme_request).session_status(
                session_id
            )
        except ThemeApiError as refusal:
            _reraise_unauthorized(refusal)
            return self._base(
                state="error", **_error_fields(refusal, STATUS_FAILED_KEY)
            )
        invoice_id = str(status.get("invoice_id") or invoice_id)
        if str(status.get("status") or "").lower() in CONFIRMED_STATUSES:
            raise ThemeFragmentRedirect(_confirmation(invoice_id))
        return self._base(
            state="verifying",
            poll=self._poll(session_id, attempt + 1, invoice_id, STATUS_POLL_DELAY),
        )

    def capture_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        order_id = theme_request.query_args.get("order_id") or ""
        try:
            self._api_factory(self._descriptor, theme_request).capture_order(order_id)
        except ThemeApiError as refusal:
            _reraise_unauthorized(refusal)
            message = (refusal.message or "").lower()
            if any(marker in message for marker in ALREADY_CAPTURED_MARKERS):
                return self._base(state="confirmed", error_message=None, error_key=None)
            return self._base(
                state="error", **_error_fields(refusal, CAPTURE_FAILED_KEY)
            )
        return self._base(state="confirmed", error_message=None, error_key=None)

    def cancel_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        return self._base()
