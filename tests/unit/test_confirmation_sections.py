"""S152-09b — ``ConfirmationSectionRegistry``: the twin of fe-user
``registries/checkoutConfirmationRegistry.ts``.

Selling adapters add sections to ``/checkout/confirmation`` without the checkout
naming them (theme_booking's BookingConfirmationDetails is the first). A section
is a name, an ``applies(invoice)`` predicate, a template, a
``build_context(invoice, theme_request)`` (``None`` = render nothing, the Vue
component's root ``v-if``) and an ``order``. As in the SPA, a re-registration
of a name replaces it, and an entry counts only while its fe-user plugin is
enabled. Sections need the owner's invoice, so they only ever render inside the
CheckoutConfirmation region re-render (bearer): the anonymous page has none.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.theme_checkout.tests.unit.fakes import FakeCheckoutApi, FakeThemeRequest
from plugins.theme_checkout.theme_checkout.confirmation import CheckoutConfirmation
from plugins.theme_checkout.theme_checkout.confirmation_sections import (
    ConfirmationSection,
    ConfirmationSectionRegistry,
    resolve_confirmation_section_registry,
)

INVOICE = {"id": "inv-1", "status": "PAID", "line_items": [{"kind": "booking"}]}


def _always_enabled(_fe_user_plugin):
    return True


def _section(name, order=0, applies=None, context=None, owner="booking"):
    received = []

    def build_context(invoice, theme_request):
        received.append((invoice, theme_request))
        return {"name": name} if context is None else context

    section = ConfirmationSection(
        name=name,
        owner_fe_user_plugin=owner,
        applies=applies or (lambda invoice: True),
        template=f"fake/{name}.html.j2",
        build_context=build_context,
        order=order,
    )
    return section, received


def _names(sections):
    return [section.name for section in sections]


def test_sections_come_in_order_then_registration_order():
    registry = ConfirmationSectionRegistry(_always_enabled)
    for name, order in (("late", 20), ("first", 0), ("second", 0), ("middle", 10)):
        registry.register(_section(name, order)[0])

    assert _names(registry.sections_for(INVOICE)) == [
        "first",
        "second",
        "middle",
        "late",
    ]


def test_a_re_registered_name_replaces_the_earlier_section():
    """``register`` filters the name out and appends (checkoutConfirmationRegistry.ts)."""
    registry = ConfirmationSectionRegistry(_always_enabled)
    registry.register(_section("booking")[0])
    registry.register(_section("ghrm")[0])
    replacement, _received = _section("booking", context={"replaced": True})
    registry.register(replacement)

    assert _names(registry.sections_for(INVOICE)) == ["ghrm", "booking"]
    assert registry.sections_for(INVOICE)[1] is replacement


def test_only_sections_that_apply_to_the_invoice_are_returned():
    registry = ConfirmationSectionRegistry(_always_enabled)
    registry.register(_section("booking", applies=lambda invoice: False)[0])
    registry.register(_section("other", applies=lambda invoice: invoice is INVOICE)[0])

    assert _names(registry.sections_for(INVOICE)) == ["other"]


def test_a_section_counts_only_while_its_fe_user_plugin_is_enabled():
    registry = ConfirmationSectionRegistry(lambda name: name == "booking")
    registry.register(_section("booking", owner="booking")[0])
    registry.register(_section("ghrm", owner="ghrm")[0])

    assert _names(registry.sections_for(INVOICE)) == ["booking"]


def test_resolve_returns_the_running_theme_checkout_registry():
    registry = ConfirmationSectionRegistry(_always_enabled)
    plugin = SimpleNamespace(confirmation_section_registry=registry)
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(
        get_plugin=lambda name: plugin if name == "theme_checkout" else None
    )

    with app.app_context():
        assert resolve_confirmation_section_registry() is registry


def test_resolve_without_theme_checkout_raises_lookup_error():
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(get_plugin=lambda name: None)

    with app.app_context(), pytest.raises(LookupError):
        resolve_confirmation_section_registry()


# ── CheckoutConfirmation renders the sections ────────────────────────────────


def _confirmation_context(registry, user_id="u-1"):
    api = FakeCheckoutApi(invoice={"invoice": INVOICE})
    theme_request = FakeThemeRequest({"invoice_id": "inv-1"}, user_id=user_id)
    component = CheckoutConfirmation(api_factory=api.factory, section_registry=registry)
    return component.build_context({}, {}, {}, theme_request), theme_request


def test_the_owners_confirmation_carries_each_applying_sections_context():
    registry = ConfirmationSectionRegistry(_always_enabled)
    booking, received = _section("booking", order=5)
    registry.register(booking)
    registry.register(_section("first", order=1)[0])

    context, theme_request = _confirmation_context(registry)

    assert context["sections"] == [
        {
            "name": "first",
            "template": "fake/first.html.j2",
            "context": {"name": "first"},
        },
        {
            "name": "booking",
            "template": "fake/booking.html.j2",
            "context": {"name": "booking"},
        },
    ]
    assert received == [(INVOICE, theme_request)]


def test_a_section_without_data_renders_nothing():
    registry = ConfirmationSectionRegistry(_always_enabled)
    registry.register(_section("booking")[0])
    registry.register(
        ConfirmationSection(
            name="hidden",
            owner_fe_user_plugin="booking",
            applies=lambda invoice: True,
            template="fake/hidden.html.j2",
            build_context=lambda invoice, theme_request: None,
        )
    )

    context, _theme_request = _confirmation_context(registry)

    assert [item["name"] for item in context["sections"]] == ["booking"]


def test_the_anonymous_page_builds_no_section():
    registry = ConfirmationSectionRegistry(_always_enabled)
    booking, received = _section("booking")
    registry.register(booking)

    context, _theme_request = _confirmation_context(registry, user_id=None)

    assert context["sections"] == []
    assert received == []
