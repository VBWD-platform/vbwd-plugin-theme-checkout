"""Payment-provider pages — declarative flow descriptors (S152-07, merged into theme_checkout).

Payment pages only exist after a checkout, so they live with it. For each
:class:`~.flow_descriptors.PaymentFlowDescriptor` (stripe, paypal) theme_checkout
registers the generic ``/pay/<provider>``, ``…/success`` and ``…/cancel`` pages,
their htmx fragments and the provider's checkout redirect; token-payment (no page
in the SPA) becomes an instant-pay checkout method. Every page, fragment and
method is owned by the provider's fe-user plugin. It talks to the payment
plugins over their public API only (D3).
"""
