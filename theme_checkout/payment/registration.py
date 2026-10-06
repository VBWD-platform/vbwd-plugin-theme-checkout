"""The pages, fragments and checkout methods one :class:`PaymentFlowDescriptor` produces.

Every page and fragment is owned by the descriptor's fe-user plugin, so a
disabled provider plugin answers 404 on both renderers. The pages are ``user``
pages (the SPA routes are ``requiresAuth``): the template renders with
``data-auth="pending"`` and the runtime sends an anonymous visitor to
``/login?redirect=``.
"""
from typing import List

from plugins.theme.theme.fragment_registry import ThemeFragment
from plugins.theme.theme.page_registry import USER_PAGE, ThemePage
from plugins.theme_checkout.theme_checkout.payment_methods import CheckoutPaymentMethod

from .flow_descriptors import PaymentFlowDescriptor, SuccessHandling
from .flow_pages import PaymentFlowPages

PAYMENT_PAGE_PRIORITY = 50


def flow_pages(descriptor: PaymentFlowDescriptor) -> List[ThemePage]:
    contexts = PaymentFlowPages(descriptor)
    pages = (
        ("", "pay", "payment/pay.html.j2", contexts.pay_context),
        ("/success", "success", "payment/success.html.j2", contexts.success_context),
        ("/cancel", "cancel", "payment/cancel.html.j2", contexts.cancel_context),
    )
    return [
        ThemePage(
            rule=f"{descriptor.pay_path}{suffix}",
            endpoint=f"payment_{descriptor.provider.replace('-', '_')}_{name}",
            owner_fe_user_plugin=descriptor.fe_user_plugin,
            priority=PAYMENT_PAGE_PRIORITY,
            auth=USER_PAGE,
            template=template,
            build_context=build_context,
        )
        for suffix, name, template, build_context in pages
    ]


def flow_fragments(descriptor: PaymentFlowDescriptor) -> List[ThemeFragment]:
    contexts = PaymentFlowPages(descriptor)
    if descriptor.success_handling is SuccessHandling.CAPTURE_ORDER:
        success_fragment = (
            "capture",
            "payment/_capture.html.j2",
            contexts.capture_context,
            "POST",
        )
    else:
        success_fragment = (
            "status",
            "payment/_status.html.j2",
            contexts.status_context,
            "GET",
        )
    fragments = (
        ("create", "payment/_create.html.j2", contexts.create_context, "POST"),
        success_fragment,
    )
    return [
        ThemeFragment(
            rule=contexts.fragment_url(action),
            endpoint=f"payment_{descriptor.provider.replace('-', '_')}_{action}_fragment",
            owner_fe_user_plugin=descriptor.fe_user_plugin,
            template=template,
            build_context=build_context,
            methods=(method,),
        )
        for action, template, build_context, method in fragments
    ]


def flow_checkout_method(descriptor: PaymentFlowDescriptor) -> CheckoutPaymentMethod:
    """The SPA plugin's ``registerCheckoutPaymentMethod(code, {redirectPath})``."""
    return CheckoutPaymentMethod(
        code=descriptor.payment_method_code,
        owner_fe_user_plugin=descriptor.fe_user_plugin,
        redirect_path=descriptor.checkout_redirect_path,
    )
