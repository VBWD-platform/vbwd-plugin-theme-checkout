"""Test doubles shared by the theme_checkout unit tests.

``FakeThemeRequest`` has the fields adapters read from a ``ThemeRequest``.
``ScriptedApi`` stands in for ``call_api``: it answers ``(METHOD, path)`` from a
script and records every call; an answer that is an exception is raised, as
``call_api`` raises ``ThemeApiError`` on a non-2xx status.
"""
from decimal import Decimal
from types import MappingProxyType

from plugins.theme.theme.viewer import ANONYMOUS_VIEWER, Viewer
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CORE_CART_KEY,
    CheckoutSource,
    CheckoutSummary,
)


class FakeThemeRequest:
    def __init__(self, query=None, view_args=None, user_id=None, path="/checkout"):
        self.path = path
        self.query_args = MappingProxyType(dict(query or {}))
        self.view_args = MappingProxyType(dict(view_args or {}))
        self.viewer = (
            Viewer(user_id=user_id, access_level_slugs=frozenset(), permissions=())
            if user_id
            else ANONYMOUS_VIEWER
        )
        self.language = "en"
        self.http_request = None


class ScriptedApi:
    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.calls = []

    def __call__(self, theme_request, method, path, **options):
        self.calls.append((method, path, options))
        answer = self.answers.get((method, path))
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            from plugins.theme.theme.theme_api import ThemeApiError

            raise ThemeApiError(404, f"no scripted answer for {method} {path}")
        return answer

    def paths(self):
        return [(method, path) for method, path, _options in self.calls]


def fake_source(
    source_id="fake",
    matches=lambda context: context.source == "fake",
    summary=None,
    submit_result=None,
    priority=0,
    cart_key=CORE_CART_KEY,
):
    """A source answering a fixed summary / submit result (both may raise)."""
    received = {"load": [], "submit": []}

    def load_summary(theme_request, context):
        received["load"].append(context)
        if isinstance(summary, Exception):
            raise summary
        return summary or CheckoutSummary(
            line_items=({"name": "Widget", "price": "10.00"},),
            order_total=Decimal("10.00"),
            currency="EUR",
        )

    def submit(theme_request, context, payment_method_code):
        received["submit"].append((context, payment_method_code))
        if isinstance(submit_result, Exception):
            raise submit_result
        return submit_result or {"invoice": {"id": "inv-1"}}

    source = CheckoutSource(
        id=source_id,
        matches=matches,
        load_summary=load_summary,
        submit=submit,
        summary_template="fake/summary.html.j2",
        priority=priority,
        cart_key=cart_key,
    )
    return source, received


DEFAULT_ANSWERS = {
    "profile": None,
    "user_details": {},
    "countries": {"countries": [{"code": "DE", "name": "Germany"}]},
    "payment_methods": {
        "methods": [
            {"code": "stripe", "name": "Pay with Stripe", "short_description": "Cards"},
            {
                "code": "invoice",
                "name": "Invoice",
                "instructions": "Pay within 14 days",
            },
        ]
    },
    "terms": {"title": "Terms", "content": "## Rules\n\nBe nice"},
}


class FakeCheckoutApi:
    """Same methods as ``CheckoutApi``; answers by method name, records every call.

    An answer that is an exception instance is raised. ``factory`` is what the
    context builders receive as their ``api_factory``.
    """

    def __init__(self, **answers):
        self.answers = {**DEFAULT_ANSWERS, **answers}
        self.calls = []

    def _answer(self, name, *arguments):
        self.calls.append((name,) + arguments)
        answer = self.answers.get(name)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def factory(self, theme_request):
        self.theme_request = theme_request
        return self

    def called(self, name):
        return [call for call in self.calls if call[0] == name]

    def has_bearer(self):
        return self.answers.get("profile") is not None

    def profile(self):
        return self._answer("profile")

    def user_details(self):
        return self._answer("user_details")

    def countries(self):
        return self._answer("countries")

    def payment_methods(self, currency):
        return self._answer("payment_methods", currency)

    def terms(self):
        return self._answer("terms")

    def check_email(self, email):
        return self._answer("check_email", email)

    def login(self, email, password):
        return self._answer("login", email, password)

    def register(self, email, password):
        return self._answer("register", email, password)

    def invoice(self, invoice_id):
        return self._answer("invoice", invoice_id)

    def token_bundles(self):
        return self._answer("token_bundles")

    def validate_coupon(self, code, cart_total, scope):
        return self._answer("validate_coupon", code, cart_total, scope)

    def default_currency(self):
        return self._answer("default_currency") or "EUR"
