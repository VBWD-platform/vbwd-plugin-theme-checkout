"""S152-07 C — the payment flows theme_checkout registers on enable (layout B merge).

Per built-in flow: ``/pay/<provider>``, ``…/success``, ``…/cancel`` (owner = the
provider's fe-user plugin, auth ``user``: the SPA routes are ``requiresAuth``),
the create fragment and the success fragment of its kind (status poll or
capture). Into theme_checkout's dispatch table: stripe / paypal as redirects,
token-payment's ``token_balance`` as an instant pay. No separate payment plugin:
enabling theme_checkout alone registers all of it.
"""
from types import SimpleNamespace

import pytest
from flask import Flask

from plugins.theme import ThemePlugin
from plugins.theme.theme.page_registry import USER_PAGE
from plugins.theme_checkout import ThemeCheckoutPlugin
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    BUILT_IN_FLOWS,
)
from plugins.theme_cms import ThemeCmsPlugin


@pytest.fixture
def enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("VBWD_VAR_DIR", str(tmp_path / "var"))
    manifest = tmp_path / "fe-user-plugins.json"
    manifest.write_text(
        '{"plugins": {"stripe-payment": {"enabled": true}, "paypal-payment": {"enabled": true},'
        ' "token-payment": {"enabled": true}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("VBWD_FE_USER_PLUGINS_JSON", str(manifest))
    plugins = {
        "theme": ThemePlugin(),
        "theme_cms": ThemeCmsPlugin(),
        "theme_checkout": ThemeCheckoutPlugin(),
    }
    app = Flask(__name__)
    app.plugin_manager = SimpleNamespace(get_plugin=plugins.get)
    with app.app_context():
        for plugin in plugins.values():
            plugin.on_enable()
        yield SimpleNamespace(app=app, **plugins)


def test_each_flow_has_its_three_auth_pages(enabled):
    pages = {page.rule: page for page in enabled.theme.page_registry.pages()}

    for provider, owner in (("stripe", "stripe-payment"), ("paypal", "paypal-payment")):
        for rule, template in (
            (f"/pay/{provider}", "payment/pay.html.j2"),
            (f"/pay/{provider}/success", "payment/success.html.j2"),
            (f"/pay/{provider}/cancel", "payment/cancel.html.j2"),
        ):
            assert pages[rule].owner_fe_user_plugin == owner, rule
            assert pages[rule].auth == USER_PAGE, rule
            assert pages[rule].template == template, rule


def test_each_flow_has_its_create_fragment_and_the_success_fragment_of_its_kind(
    enabled,
):
    fragments = {
        fragment.rule: fragment
        for fragment in enabled.theme.fragment_registry.fragments()
    }

    assert fragments["/_render/_fragment/pay/stripe/create"].methods == ("POST",)
    assert fragments["/_render/_fragment/pay/stripe/status"].methods == ("GET",)
    assert fragments["/_render/_fragment/pay/paypal/create"].methods == ("POST",)
    assert fragments["/_render/_fragment/pay/paypal/capture"].methods == ("POST",)
    assert "/_render/_fragment/pay/stripe/capture" not in fragments
    assert "/_render/_fragment/pay/paypal/status" not in fragments
    assert fragments["/_render/_fragment/pay/paypal/capture"].owner_fe_user_plugin == (
        "paypal-payment"
    )


def test_the_checkout_dispatch_table_gets_the_payment_methods(enabled):
    methods = enabled.theme_checkout.payment_method_registry

    assert methods.get("stripe").redirect_path("inv-1") == "/pay/stripe?invoice=inv-1"
    assert methods.get("paypal").redirect_path("inv-1") == "/pay/paypal?invoice=inv-1"
    assert methods.get("token_balance").instant_pay is not None
    assert enabled.theme_checkout.payment_flow_registry.get("stripe") is not None


def test_theme_checkout_owns_the_built_in_flows_and_registers_their_pages_on_enable(
    enabled,
):
    rules = {page.rule for page in enabled.theme.page_registry.pages()}

    assert enabled.theme_checkout.payment_flow_registry.descriptors() == list(
        BUILT_IN_FLOWS
    )
    for descriptor in BUILT_IN_FLOWS:
        assert descriptor.pay_path in rules, descriptor.provider
        assert (
            enabled.theme_checkout.payment_method_registry.get(
                descriptor.payment_method_code
            )
            is not None
        ), descriptor.provider


def test_enabling_twice_registers_once(enabled):
    with enabled.app.app_context():
        enabled.theme_checkout.on_enable()

    rules = [page.rule for page in enabled.theme.page_registry.pages()]
    assert rules.count("/pay/stripe") == 1
