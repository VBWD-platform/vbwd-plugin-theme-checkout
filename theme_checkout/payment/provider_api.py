"""A payment provider's public API as its fe-user views call it — through core C2 (D3).

The buyer's bearer is forwarded (the runtime adds it to every ``/_render/``
fragment request), so ``require_auth`` and the invoice ownership checks of the
provider plugin apply unchanged.
"""
from typing import Any
from urllib.parse import quote

from plugins.theme.theme.theme_api import call_api
from plugins.theme.theme.theme_request import ThemeRequest

from .flow_descriptors import PaymentFlowDescriptor

SESSION_STATUS_PATH = "/session-status/{session_id}"
CAPTURE_ORDER_PATH = "/capture-order"


class ProviderApi:
    """The create / status / capture endpoints of one provider for one request."""

    def __init__(
        self, descriptor: PaymentFlowDescriptor, theme_request: ThemeRequest
    ) -> None:
        self._descriptor = descriptor
        self._theme_request = theme_request

    def _url(self, path: str) -> str:
        return f"{self._descriptor.api_prefix}{path}"

    def create_session(self, invoice_id: str) -> Any:
        return call_api(
            self._theme_request,
            "POST",
            self._url(self._descriptor.create_path),
            json={"invoice_id": invoice_id},
        )

    def session_status(self, session_id: str) -> Any:
        return call_api(
            self._theme_request,
            "GET",
            self._url(
                SESSION_STATUS_PATH.format(session_id=quote(session_id, safe=""))
            ),
        )

    def capture_order(self, order_id: str) -> Any:
        return call_api(
            self._theme_request,
            "POST",
            self._url(CAPTURE_ORDER_PATH),
            json={"order_id": order_id},
        )
