"""What theme_checkout puts into the theme platform: pages, htmx fragments, CMS widgets.

All are owned by fe-user ``checkout`` (the SPA's toggle governs both renderers).
``/checkout/confirmation`` is, as in fe-user, the ``checkout-confirmation`` CMS
page rendered through theme_cms's own page pipeline (``CmsPages``).
"""
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Dict, List, Mapping

from plugins.theme.theme.fragment_registry import ThemeFragment
from plugins.theme.theme.page_registry import PUBLIC_PAGE, ThemePage
from plugins.theme.theme.theme_request import ThemeRequest
from plugins.theme_cms.theme_cms.pages import DISPATCH_TEMPLATE, CmsPages
from plugins.theme_cms.theme_cms.registries import (
    ComponentTemplate,
    ComponentTemplateRegistry,
)

from .checkout_form import CheckoutForm
from .checkout_page import CheckoutPage
from .checkout_sources import CheckoutSourceRegistry
from .confirmation import CheckoutConfirmation
from .confirmation_sections import ConfirmationSectionRegistry
from .email_block import EmailBlock
from .payment_methods import CheckoutPaymentMethodRegistry
from .submit import CheckoutSubmit
from .token_bundles import TokenBundleCollection

CHECKOUT_FE_USER_PLUGIN = "checkout"
CONFIRMATION_CMS_SLUG = "checkout-confirmation"
CHECKOUT_PAGE_PRIORITY = 50
FRAGMENT_PREFIX = "/_render/_fragment/checkout"


def _page(rule: str, endpoint: str, template: str, build_context) -> ThemePage:
    return ThemePage(
        rule=rule,
        endpoint=endpoint,
        owner_fe_user_plugin=CHECKOUT_FE_USER_PLUGIN,
        priority=CHECKOUT_PAGE_PRIORITY,
        auth=PUBLIC_PAGE,
        template=template,
        build_context=build_context,
    )


def _fragment(name: str, template: str, build_context, method: str) -> ThemeFragment:
    return ThemeFragment(
        rule=f"{FRAGMENT_PREFIX}/{name}",
        endpoint=f"checkout_{name.replace('-', '_')}_fragment",
        owner_fe_user_plugin=CHECKOUT_FE_USER_PLUGIN,
        template=template,
        build_context=build_context,
        methods=(method,),
    )


def checkout_pages(
    source_registry: CheckoutSourceRegistry, cms_pages: CmsPages
) -> List[ThemePage]:
    def confirmation_context(theme_request: ThemeRequest) -> Dict[str, Any]:
        cms_request = replace(
            theme_request, view_args=MappingProxyType({"slug": CONFIRMATION_CMS_SLUG})
        )
        return cms_pages.slug_page_context(cms_request)

    return [
        _page(
            "/checkout",
            "checkout_page",
            "checkout/page.html.j2",
            CheckoutPage(source_registry).context,
        ),
        _page(
            "/checkout/confirmation",
            "checkout_confirmation_page",
            DISPATCH_TEMPLATE,
            confirmation_context,
        ),
    ]


def checkout_fragments(
    source_registry: CheckoutSourceRegistry,
    payment_method_registry: CheckoutPaymentMethodRegistry,
) -> List[ThemeFragment]:
    email_block = EmailBlock()
    return [
        _fragment(
            "form",
            "checkout/_island.html.j2",
            CheckoutForm(source_registry).context,
            "POST",
        ),
        _fragment(
            "submit",
            "checkout/_submit_result.html.j2",
            CheckoutSubmit(source_registry, payment_method_registry).context,
            "POST",
        ),
        _fragment(
            "email-check",
            "checkout/_email_auth.html.j2",
            email_block.check_context,
            "GET",
        ),
        _fragment(
            "login", "checkout/_auth_result.html.j2", email_block.login_context, "POST"
        ),
        _fragment(
            "register",
            "checkout/_auth_result.html.j2",
            email_block.register_context,
            "POST",
        ),
    ]


def register_checkout_components(
    component_registry: ComponentTemplateRegistry,
    source_registry: CheckoutSourceRegistry,
    section_registry: ConfirmationSectionRegistry,
) -> None:
    """The twins of fe-user ``registerCmsVueComponent`` (skipped when already there)."""
    checkout_page = CheckoutPage(source_registry)

    def checkout_form_context(
        widget_config: Mapping[str, Any],
        page: Mapping[str, Any],
        route_params: Mapping[str, Any],
        theme_request: ThemeRequest,
    ) -> Dict[str, Any]:
        return checkout_page.context(theme_request)

    components = (
        ComponentTemplate(
            "CheckoutForm",
            "checkout/components/checkout_form.html.j2",
            checkout_form_context,
        ),
        ComponentTemplate(
            "CheckoutConfirmation",
            "checkout/components/checkout_confirmation.html.j2",
            CheckoutConfirmation(section_registry).build_context,
        ),
        ComponentTemplate(
            "TokenBundleCollection",
            "checkout/components/token_bundle_collection.html.j2",
            TokenBundleCollection().build_context,
        ),
    )
    for component in components:
        if component_registry.resolve(component.name) is None:
            component_registry.register(component)
