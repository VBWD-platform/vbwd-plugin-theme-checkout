"""The ``CheckoutConfirmation`` CMS component — the twin of ``CheckoutConfirmationView.vue``.

It lives in the ``checkout-confirmation`` CMS page's layout, so theme_cms renders
it inside a personalised region (D12): the anonymous page shows the pending
banner without any API call, and the region re-render for a logged-in viewer
reads ``GET /api/v1/user/invoices/<id>`` with the bearer (the API scopes by
owner). The banner copy is the SPA's (hard-coded English there too). The
sections other adapters register (:mod:`.confirmation_sections`) follow the
invoice card, built from the same invoice.
"""
import html
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from markupsafe import Markup

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme_cms.theme_cms.components.pricing import format_money

from .checkout_api import CheckoutApi
from .confirmation_sections import ConfirmationSectionRegistry

PENDING_STATUS = "pending"
INVOICE_ID_PARAMETERS = ("invoice_id", "invoice")
STATUS_COPY = {
    "paid": (
        "Payment Successful",
        "Your payment has been processed successfully. Thank you for your order!",
    ),
    "pending": (
        "Payment Processing",
        "Your payment is being processed. This may take a moment.",
    ),
    "authorized": (
        "Payment Authorized",
        "Your payment has been authorized and will be charged upon completion.",
    ),
    "failed": (
        "Payment Failed",
        "Your payment could not be processed. Please try again.",
    ),
    "cancelled": ("Payment Cancelled", "Your payment was cancelled."),
}
DEFAULT_STATUS_COPY = ("Order Received", "Your order has been received.")
NOON_HOUR = 12


def status_copy(status: str) -> Tuple[str, str]:
    return STATUS_COPY.get(status, DEFAULT_STATUS_COPY)


def locale_datetime(raw: Optional[str]) -> str:
    """``new Date(raw).toLocaleString()`` in en-US (the stored time, no browser zone)."""
    if not raw:
        return ""
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    hour = moment.hour % NOON_HOUR or NOON_HOUR
    meridiem = "AM" if moment.hour < NOON_HOUR else "PM"
    return (
        f"{moment.month}/{moment.day}/{moment.year}, "
        f"{hour}:{moment.minute:02d}:{moment.second:02d} {meridiem}"
    )


def _invoice_view(invoice: Mapping[str, Any]) -> Dict[str, Any]:
    currency = invoice.get("currency")
    total = invoice.get("total_amount") or invoice.get("amount") or ""
    return {
        "number": invoice.get("invoice_number") or "",
        "amount": format_money(total, currency) if total else "",
        "total_raw": total,
        "subtotal": format_money(invoice["subtotal"], currency)
        if invoice.get("subtotal")
        else "",
        "tax_amount": format_money(invoice["tax_amount"], currency)
        if invoice.get("tax_amount")
        else "",
        "currency": currency or "",
        "payment_method": invoice.get("payment_method") or "",
        "payment_ref": invoice.get("payment_ref") or "",
        "user_id": invoice.get("user_id") or "",
        "date": locale_datetime(invoice.get("paid_at") or invoice.get("invoiced_at")),
        "line_items": [
            {
                "description": item.get("description") or "",
                "quantity": item.get("quantity"),
                "unit_price": format_money(item.get("unit_price") or 0, currency),
                "amount": format_money(item.get("amount") or 0, currency),
            }
            for item in invoice.get("line_items") or []
        ],
    }


def _line_items_html(line_items: List[Mapping[str, Any]]) -> str:
    """``buildLineItemsHtml`` — with every cell escaped."""
    if not line_items:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(str(item['description']))}</td>"
        f"<td>{html.escape(str(item['quantity'] or 1))}</td>"
        f"<td>{html.escape(item['amount'])}</td></tr>"
        for item in line_items
    )
    return (
        '<table class="line-items-table"><thead><tr><th>Description</th><th>Qty</th>'
        f"<th>Price</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _rendered_content(
    page: Mapping[str, Any],
    invoice_id: str,
    status: str,
    invoice: Optional[Dict[str, Any]],
) -> Markup:
    """The CMS page HTML with ``{{variable}}`` placeholders filled (values escaped)."""
    invoice = invoice or {}
    variables = {
        "invoice_number": invoice.get("number", ""),
        "invoice_id": invoice_id,
        "status": status,
        "total_amount": invoice.get("amount", ""),
        "subtotal": invoice.get("subtotal", ""),
        "tax_amount": invoice.get("tax_amount", ""),
        "currency": invoice.get("currency", ""),
        "payment_method": invoice.get("payment_method", ""),
        "payment_date": invoice.get("date", ""),
        "payment_ref": invoice.get("payment_ref", ""),
        "user_id": invoice.get("user_id", ""),
    }
    content = str(page.get("content_html") or "")
    for name, value in variables.items():
        content = re.sub(
            r"\{\{\s*" + name + r"\s*\}\}",
            lambda _match: html.escape(str(value)),
            content,
        )
    line_items = _line_items_html(invoice.get("line_items") or [])
    content = re.sub(
        r"\{\{\s*line_items_html\s*\}\}", lambda _match: line_items, content
    )
    return Markup(content)


class CheckoutConfirmation:
    """``build_context(widget_config, page, route_params, theme_request)`` of the component."""

    def __init__(
        self,
        section_registry: ConfirmationSectionRegistry,
        api_factory: Callable[[ThemeRequest], Any] = CheckoutApi,
    ) -> None:
        self._section_registry = section_registry
        self._api_factory = api_factory

    def build_context(
        self,
        widget_config: Mapping[str, Any],
        page: Mapping[str, Any],
        route_params: Mapping[str, Any],
        theme_request: ThemeRequest,
    ) -> Dict[str, Any]:
        query = theme_request.query_args
        invoice_id = next(
            (query[name] for name in INVOICE_ID_PARAMETERS if query.get(name)), ""
        )
        raw_invoice = self._read_invoice(theme_request, invoice_id)
        status = str((raw_invoice or {}).get("status") or PENDING_STATUS).lower()
        invoice = _invoice_view(raw_invoice) if raw_invoice else None
        title, message = status_copy(status)
        return {
            "status": status,
            "title": title,
            "message": message,
            "invoice": invoice,
            "clear_shop_cart": raw_invoice is not None,
            "content_html": _rendered_content(page, invoice_id, status, invoice),
            "sections": self._sections(raw_invoice, theme_request)
            if raw_invoice
            else [],
        }

    def _sections(
        self, invoice: Mapping[str, Any], theme_request: ThemeRequest
    ) -> List[Dict[str, Any]]:
        built = (
            (section, section.build_context(invoice, theme_request))
            for section in self._section_registry.sections_for(invoice)
        )
        return [
            {"name": section.name, "template": section.template, "context": context}
            for section, context in built
            if context is not None
        ]

    def _read_invoice(
        self, theme_request: ThemeRequest, invoice_id: str
    ) -> Optional[Mapping[str, Any]]:
        if not invoice_id or theme_request.viewer.user_id is None:
            return None
        try:
            response = self._api_factory(theme_request).invoice(invoice_id)
        except ThemeApiError:
            return None
        return response.get("invoice") or response
