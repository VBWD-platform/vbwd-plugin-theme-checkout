"""S152-07 B — what theme_checkout registers on enable (pages, fragments, CMS components).

Every page and fragment is owned by fe-user ``checkout`` (same toggle as the SPA);
the three CMS widget twins land in theme_cms's ``ComponentTemplateRegistry``
under the names fe-user ``checkout/index.ts`` registers.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.theme import ThemePlugin
from plugins.theme_checkout import ThemeCheckoutPlugin
from plugins.theme_cms import ThemeCmsPlugin

FE_USER_CHECKOUT_INDEX = (
    Path(__file__).resolve().parents[5]
    / "vbwd-fe-user"
    / "plugins"
    / "checkout"
    / "index.ts"
)


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))
    theme_plugin = ThemePlugin()
    theme_cms_plugin = ThemeCmsPlugin()
    checkout_plugin = ThemeCheckoutPlugin()
    plugins = {
        "theme": theme_plugin,
        "theme_cms": theme_cms_plugin,
        "theme_checkout": checkout_plugin,
    }
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(get_plugin=plugins.get)
    with app.app_context():
        theme_plugin.on_enable()
        theme_cms_plugin.on_enable()
        checkout_plugin.on_enable()
        yield SimpleNamespace(**plugins)


def test_registers_the_checkout_pages_for_fe_user_checkout(enabled):
    pages = {page.rule: page for page in enabled.theme.page_registry.pages()}

    assert pages["/checkout"].owner_fe_user_plugin == "checkout"
    assert pages["/checkout"].template == "checkout/page.html.j2"
    assert pages["/checkout/confirmation"].owner_fe_user_plugin == "checkout"
    assert pages["/checkout/confirmation"].template == "cms/dispatch.html.j2"


def test_registers_the_checkout_fragments(enabled):
    fragments = {
        fragment.rule: fragment
        for fragment in enabled.theme.fragment_registry.fragments()
    }

    expected_methods = {
        "/_render/_fragment/checkout/form": ("POST",),
        "/_render/_fragment/checkout/submit": ("POST",),
        "/_render/_fragment/checkout/email-check": ("GET",),
        "/_render/_fragment/checkout/login": ("POST",),
        "/_render/_fragment/checkout/register": ("POST",),
    }
    for rule, methods in expected_methods.items():
        assert fragments[rule].methods == methods
        assert fragments[rule].owner_fe_user_plugin == "checkout"


def test_registers_the_cms_widget_twins_into_theme_cms(enabled):
    registry = enabled.theme_cms.component_registry

    for name in ("CheckoutForm", "CheckoutConfirmation", "TokenBundleCollection"):
        assert registry.resolve(name) is not None, name


def test_enabling_twice_does_not_register_twice(enabled):
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(
        get_plugin={
            "theme": enabled.theme,
            "theme_cms": enabled.theme_cms,
            "theme_checkout": enabled.theme_checkout,
        }.get
    )
    with app.app_context():
        enabled.theme_checkout.on_enable()

    rules = [page.rule for page in enabled.theme.page_registry.pages()]
    assert rules.count("/checkout") == 1


def test_contributes_its_templates_and_translations(enabled):
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "theme_checkout"
            / "translations"
            / "en.json"
        ).read_text(encoding="utf-8")
    )

    assert catalog["checkout.title"] == "Checkout"


def test_the_component_names_are_the_ones_fe_user_registers():
    if not FE_USER_CHECKOUT_INDEX.is_file():
        pytest.skip("fe-user checkout plugin is not next to vbwd-backend (plugin CI)")
    source = FE_USER_CHECKOUT_INDEX.read_text(encoding="utf-8")

    for name in ("CheckoutForm", "CheckoutConfirmation", "TokenBundleCollection"):
        assert f"registerCmsVueComponent('{name}'" in source


def test_owns_the_confirmation_section_registry_the_confirmation_widget_reads(
    enabled, monkeypatch
):
    """Selling adapters register into ``confirmation_section_registry``; the
    CheckoutConfirmation widget renders whatever is there (S152-09b)."""
    from plugins.theme_checkout.theme_checkout.confirmation_sections import (
        ConfirmationSection,
    )
    from plugins.theme_checkout.tests.unit.fakes import FakeThemeRequest
    from plugins.theme_checkout.theme_checkout import confirmation

    invoice = {"id": "inv-1", "status": "PAID"}
    monkeypatch.setattr(
        confirmation.CheckoutConfirmation,
        "_read_invoice",
        lambda self, theme_request, invoice_id: invoice,
    )
    monkeypatch.setattr(
        enabled.theme_checkout.confirmation_section_registry,
        "_is_fe_user_plugin_enabled",
        lambda name: True,
    )
    enabled.theme_checkout.confirmation_section_registry.register(
        ConfirmationSection(
            name="extra",
            owner_fe_user_plugin="extra",
            applies=lambda invoice: True,
            template="extra.html.j2",
            build_context=lambda invoice, theme_request: {"seen": invoice["id"]},
        )
    )
    component = enabled.theme_cms.component_registry.resolve("CheckoutConfirmation")

    context = component.build_context(
        {}, {}, {}, FakeThemeRequest({"invoice_id": "inv-1"}, user_id="u-1")
    )

    assert context["sections"] == [
        {"name": "extra", "template": "extra.html.j2", "context": {"seen": "inv-1"}}
    ]
