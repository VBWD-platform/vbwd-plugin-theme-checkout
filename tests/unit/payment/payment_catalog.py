"""Which entries of theme_checkout's merged catalogs belong to the payment flows.

The payment templates compose their keys from the flow's namespace
(``stripe.payment.redirecting``), so a key is a payment key when it sits under a
built-in flow's namespace or under the composables' ``payment.errors.``. The
checkout drift test leaves these out; the payment drift test checks only these.
"""
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    BUILT_IN_FLOWS,
)

PAYMENT_ERRORS_PREFIX = "payment.errors."
PAYMENT_KEY_PREFIXES = (PAYMENT_ERRORS_PREFIX,) + tuple(
    f"{descriptor.namespace}." for descriptor in BUILT_IN_FLOWS
)


def is_payment_key(key: str) -> bool:
    return key.startswith(PAYMENT_KEY_PREFIXES)
