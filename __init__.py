"""Theme adapter mirroring the fe-user checkout plugin (S152-07).

Renders only when ``VBWD_FRONTEND_MODE=theme``; in the default ``vue`` mode the
Vue SPA serves every page. On enable it contributes its templates,
translations and ported stylesheet (the checkout-wide ``.card`` / ``.btn`` rules
selling adapters' pay pages share) and registers ``/checkout`` (the island form), the
``checkout-confirmation`` CMS page at ``/checkout/confirmation``, the checkout
htmx fragments and the CheckoutForm / CheckoutConfirmation /
TokenBundleCollection CMS widgets. It also registers the payment-provider
pages of every :class:`PaymentFlowDescriptor` (``/pay/<provider>``, success,
cancel + their fragments, owned by the provider's fe-user plugin) and the
checkout methods they dispatch to (stripe / paypal redirects, token-payment's
instant pay). It owns the dispatch tables selling adapters and payment flows
register into: :class:`CheckoutSourceRegistry`,
:class:`CheckoutPaymentMethodRegistry`, :class:`PaymentFlowRegistry` and the
confirmation page's :class:`ConfirmationSectionRegistry`. It talks to the
backend over the public API only (D3).
"""
from typing import Optional

from flask import current_app

from vbwd.plugins.base import BasePlugin, PluginMetadata

from plugins.theme.theme.fe_user_manifest import FeUserPluginManifest
from plugins.theme.theme.fragment_registry import ThemeFragmentRegistry
from plugins.theme.theme.page_registry import ThemePageRegistry, resolve_theme_plugin
from plugins.theme_checkout.theme_checkout.checkout_sources import (
    CheckoutSourceRegistry,
)
from plugins.theme_checkout.theme_checkout.confirmation_sections import (
    ConfirmationSectionRegistry,
)
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    BUILT_IN_FLOWS,
    TOKEN_BALANCE_METHOD,
    PaymentFlowRegistry,
)
from plugins.theme_checkout.theme_checkout.payment.registration import (
    flow_checkout_method,
    flow_fragments,
    flow_pages,
)
from plugins.theme_checkout.theme_checkout.payment_methods import (
    CheckoutPaymentMethodRegistry,
)
from plugins.theme_checkout.theme_checkout.plugin_paths import (
    STYLESHEETS_DIRECTORY,
    TEMPLATES_DIRECTORY,
    TRANSLATIONS_DIRECTORY,
)
from plugins.theme_checkout.theme_checkout.registration import (
    checkout_fragments,
    checkout_pages,
    register_checkout_components,
)
from plugins.theme_cms.theme_cms.pages import CmsPages
from plugins.theme_cms.theme_cms.registries import THEME_CMS_PLUGIN_NAME

CHECKOUT_PAGE_RULE = "/checkout"


class ThemeCheckoutPlugin(BasePlugin):
    """Theme adapter mirroring the fe-user checkout plugin."""

    def __init__(self) -> None:
        super().__init__()
        self.source_registry = CheckoutSourceRegistry()
        fe_user_manifest = FeUserPluginManifest()
        self.payment_method_registry = CheckoutPaymentMethodRegistry(
            fe_user_manifest.is_enabled
        )
        self.confirmation_section_registry = ConfirmationSectionRegistry(
            fe_user_manifest.is_enabled
        )
        self.payment_flow_registry = PaymentFlowRegistry()
        for descriptor in BUILT_IN_FLOWS:
            self.payment_flow_registry.register(descriptor)

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="theme_checkout",
            version="1.0.0",
            author="VBWD Team",
            description="Theme adapter mirroring the fe-user checkout plugin.",
            dependencies=["theme>=1.0", "theme_cms", "checkout"],
        )

    def on_enable(self) -> None:
        theme_plugin = resolve_theme_plugin()
        # A declared dependency: enabled before this plugin (dependency order).
        theme_cms_plugin = getattr(current_app, "plugin_manager").get_plugin(
            THEME_CMS_PLUGIN_NAME
        )
        register_checkout_components(
            theme_cms_plugin.component_registry,
            self.source_registry,
            self.confirmation_section_registry,
        )
        self._register_payment_methods()
        if any(
            page.rule == CHECKOUT_PAGE_RULE
            for page in theme_plugin.page_registry.pages()
        ):
            return
        theme_plugin.theme_registry.add_contributed_template_path(TEMPLATES_DIRECTORY)
        theme_plugin.theme_registry.add_contributed_translation_path(
            TRANSLATIONS_DIRECTORY
        )
        theme_plugin.theme_registry.add_contributed_stylesheet_path(
            STYLESHEETS_DIRECTORY
        )
        cms_pages = CmsPages(
            theme_cms_plugin.page_type_registry, theme_cms_plugin.component_registry
        )
        for page in checkout_pages(self.source_registry, cms_pages):
            theme_plugin.page_registry.register(page)
        for fragment in checkout_fragments(
            self.source_registry, self.payment_method_registry
        ):
            theme_plugin.fragment_registry.register(fragment)
        self._register_payment_flow_routes(
            theme_plugin.page_registry, theme_plugin.fragment_registry
        )

    def _register_payment_methods(self) -> None:
        """token-payment's instant pay + each flow's redirect into the dispatch table."""
        self.payment_method_registry.register(TOKEN_BALANCE_METHOD)
        for descriptor in self.payment_flow_registry.descriptors():
            self.payment_method_registry.register(flow_checkout_method(descriptor))

    def _register_payment_flow_routes(
        self,
        page_registry: ThemePageRegistry,
        fragment_registry: ThemeFragmentRegistry,
    ) -> None:
        """Each flow's ``/pay/<provider>`` pages and fragments."""
        for descriptor in self.payment_flow_registry.descriptors():
            for page in flow_pages(descriptor):
                page_registry.register(page)
            for fragment in flow_fragments(descriptor):
                fragment_registry.register(fragment)

    def get_url_prefix(self) -> Optional[str]:
        # No blueprint of its own: the theme mounts the registered pages.
        return ""
