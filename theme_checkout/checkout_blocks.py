"""The data of the checkout's step blocks, each the twin of one fe-user component.

* buyer → ``EmailBlock`` (logged-in state from ``/user/profile``);
* billing → ``BillingAddressBlock`` (countries + a logged-in buyer's saved address);
* payment → ``PaymentMethodsBlock`` / ``usePaymentMethods`` (first method auto-selected);
* terms → ``TermsCheckbox`` (its markdown-ish rendering, escaped first).

Posted form values win over loaded defaults, so a re-rendered island keeps what
the buyer typed.
"""
import html
import re
from typing import Any, Dict, List, Mapping, Optional

from plugins.theme.theme.theme_api import ThemeApiError

# BillingAddressBlock fields → (posted form name, ``/user/details`` key).
BILLING_FIELDS = {
    "first_name": ("billing_first_name", "first_name"),
    "last_name": ("billing_last_name", "last_name"),
    "company": ("billing_company", "company"),
    "street": ("billing_street", "address_line_1"),
    "city": ("billing_city", "city"),
    "state": ("billing_state", "state"),
    "zip": ("billing_zip", "postal_code"),
    "country": ("billing_country", "country"),
}
REQUIRED_BILLING_FIELDS = (
    "first_name",
    "last_name",
    "street",
    "city",
    "zip",
    "country",
)
# BillingAddressBlock.loadCountries' fallback when /settings/countries fails.
FALLBACK_COUNTRIES = [
    {"code": "DE", "name": "Germany"},
    {"code": "AT", "name": "Austria"},
    {"code": "CH", "name": "Switzerland"},
    {"code": "US", "name": "United States"},
    {"code": "GB", "name": "United Kingdom"},
]
PAYMENT_METHOD_FIELD = "payment_method"
TERMS_FIELD = "terms"


def load_buyer(api: Any) -> Optional[Dict[str, str]]:
    """``{email, name}`` of the logged-in buyer, or ``None`` (anonymous / refused token)."""
    if not api.has_bearer():
        return None
    try:
        profile = api.profile()
    except ThemeApiError:
        return None
    details = profile.get("details") or {}
    name_parts = [details.get("first_name"), details.get("last_name")]
    return {
        "email": (profile.get("user") or {}).get("email") or "",
        "name": " ".join(part for part in name_parts if part),
    }


def _saved_address(api: Any) -> Mapping[str, Any]:
    try:
        return api.user_details() or {}
    except ThemeApiError:
        return {}


def load_billing(
    api: Any, form: Mapping[str, Any], is_logged_in: bool
) -> Dict[str, Any]:
    """Field values (posted, else saved) and the country list."""
    saved = _saved_address(api) if is_logged_in else {}
    values = {
        field: form.get(form_name) or saved.get(details_key) or ""
        for field, (form_name, details_key) in BILLING_FIELDS.items()
    }
    try:
        countries = api.countries().get("countries") or []
    except ThemeApiError:
        countries = FALLBACK_COUNTRIES
    return {"values": values, "countries": countries}


def is_billing_complete(values: Mapping[str, str]) -> bool:
    return all(values.get(field) for field in REQUIRED_BILLING_FIELDS)


def _method_view(method: Mapping[str, Any]) -> Dict[str, Any]:
    """The fields ``PaymentMethodsBlock`` shows (short description wins)."""
    return {
        "code": method.get("code"),
        "name": method.get("name") or "",
        "description": method.get("short_description")
        or method.get("description")
        or "",
        "instructions": method.get("instructions") or "",
    }


def load_payment_methods(
    api: Any, currency: str, form: Mapping[str, Any]
) -> Dict[str, Any]:
    """The active methods for ``currency``; the posted choice, else the first one."""
    try:
        methods: List[Dict[str, Any]] = [
            _method_view(method)
            for method in api.payment_methods(currency).get("methods") or []
        ]
    except ThemeApiError:
        return {
            "methods": [],
            "selected_code": None,
            "error": True,
            "instructions": None,
        }
    codes = [method.get("code") for method in methods]
    posted_code = form.get(PAYMENT_METHOD_FIELD)
    selected_code = (
        posted_code if posted_code in codes else (codes[0] if codes else None)
    )
    selected = next(
        (method for method in methods if method.get("code") == selected_code), None
    )
    return {
        "methods": methods,
        "selected_code": selected_code,
        "error": False,
        "instructions": (selected or {}).get("instructions") or None,
    }


def render_terms_html(content: str) -> str:
    """``TermsCheckbox.renderedContent``: escape, then headings / list items / paragraphs."""
    escaped = html.escape(content, quote=True).replace("&#x27;", "&#039;")
    rendered = re.sub(r"^### (.+)$", r"<h4>\1</h4>", escaped, flags=re.MULTILINE)
    rendered = re.sub(r"^## (.+)$", r"<h3>\1</h3>", rendered, flags=re.MULTILINE)
    rendered = re.sub(r"^- (.+)$", r"<li>\1</li>", rendered, flags=re.MULTILINE)
    return "<p>" + rendered.replace("\n\n", "</p><p>") + "</p>"


def load_terms(api: Any, form: Mapping[str, Any]) -> Dict[str, Any]:
    """Accepted flag + popup title/content (``None`` → the "failed to load" copy)."""
    accepted = bool(form.get(TERMS_FIELD))
    try:
        terms = api.terms() or {}
    except ThemeApiError:
        return {"accepted": accepted, "title": None, "content_html": None}
    return {
        "accepted": accepted,
        "title": terms.get("title"),
        "content_html": render_terms_html(terms.get("content") or ""),
    }
