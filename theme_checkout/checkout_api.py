"""The public API the fe-user checkout calls, always through core C2 (D3).

One method per ``/api/v1/*`` endpoint the SPA checkout components use
(``EmailBlock``, ``BillingAddressBlock``, ``PaymentMethodsBlock``,
``TermsCheckbox``, ``CheckoutConfirmationView``, ``TokenBundleCollection``,
the app-config store) and the sources' coupon validation (S152-08). The
caller's headers are forwarded, so a buyer's bearer reaches the API and its own
scoping applies; a non-2xx answer raises ``ThemeApiError``.
"""
from typing import Any, Mapping, Optional
from urllib.parse import quote

from plugins.theme.theme.theme_api import call_api
from plugins.theme.theme.theme_request import ThemeRequest

AUTHORIZATION_HEADER = "Authorization"
FALLBACK_CURRENCY = "EUR"


class CheckoutApi:
    """The checkout endpoints for one themed request."""

    def __init__(self, theme_request: ThemeRequest) -> None:
        self._theme_request = theme_request

    def _get(self, path: str, query: Optional[Mapping[str, Any]] = None) -> Any:
        return call_api(self._theme_request, "GET", path, query=query)

    def _post(self, path: str, payload: Mapping[str, Any]) -> Any:
        return call_api(self._theme_request, "POST", path, json=dict(payload))

    def has_bearer(self) -> bool:
        """Did the runtime send the buyer's token? (Navigations never carry one, D4.)"""
        http_request = self._theme_request.http_request
        return bool(
            http_request is not None and http_request.headers.get(AUTHORIZATION_HEADER)
        )

    def profile(self) -> Any:
        return self._get("/api/v1/user/profile")

    def user_details(self) -> Any:
        return self._get("/api/v1/user/details")

    def countries(self) -> Any:
        return self._get("/api/v1/settings/countries")

    def payment_methods(self, currency: str) -> Any:
        return self._get("/api/v1/settings/payment-methods", {"currency": currency})

    def terms(self) -> Any:
        return self._get("/api/v1/settings/terms")

    def check_email(self, email: str) -> Any:
        return self._get("/api/v1/auth/check-email", {"email": email})

    def login(self, email: str, password: str) -> Any:
        return self._post("/api/v1/auth/login", {"email": email, "password": password})

    def register(self, email: str, password: str) -> Any:
        return self._post(
            "/api/v1/auth/register", {"email": email, "password": password}
        )

    def invoice(self, invoice_id: str) -> Any:
        return self._get(f"/api/v1/user/invoices/{quote(invoice_id, safe='')}")

    def token_bundles(self) -> Any:
        return self._get("/api/v1/token-bundles")

    def validate_coupon(self, code: str, cart_total: float, scope: str) -> Any:
        return self._post(
            "/api/v1/coupons/validate",
            {"code": code, "cart_total": cart_total, "scope": scope},
        )

    def default_currency(self) -> str:
        """The operating currency (``useAppConfigStore().defaultCurrency``)."""
        return self._get("/api/v1/config").get("default_currency") or FALLBACK_CURRENCY
