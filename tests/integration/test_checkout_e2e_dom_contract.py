"""S152-07 — every selector the fe-user e2e specs use on THEMED checkout URLs is in
the themed output (D2 / R4), rendered on the real app.

Each row: (selector, spec file, line, which themed output must contain it).
``plan-name`` is the subscription source's summary line (theme_subscription,
S152-08): here it comes from the test source, so the shell is proven to carry
whatever the source renders. Specs that drive ``/dashboard/checkout/*`` stay on
the SPA (D7) and are not listed. The drift guard re-reads the specs (skipped
when fe-user is not next to vbwd-backend) so a renamed selector turns this red;
the line documents the use (``plugins.theme.tests.e2e_spec_contract``).
"""
import json
import re
from pathlib import Path

import pytest

from plugins.theme.tests.e2e_spec_contract import spec_selector_drift
from plugins.theme_checkout.tests.integration.test_checkout_flow import (
    CART,
    RENDER,
    _confirmation_page,
)

FE_USER_ROOT = Path(__file__).resolve().parents[4].parent / "vbwd-fe-user"
COUPON_PUBLIC = "vue/tests/e2e/checkout/coupon-public.spec.ts"
CONFIRMATION_EXISTS = "vue/tests/e2e/checkout/checkout-confirmation-page-exists.spec.ts"
DRAFT_CHECKOUT = "plugins/checkout/tests/e2e/draft-checkout.spec.ts"
FIXTURES = "vue/tests/e2e/fixtures/checkout.fixtures.ts"

CONTRACT = [
    ('[data-testid="order-summary"]', COUPON_PUBLIC, 28, "island"),
    ('[data-testid="coupon-input"]', COUPON_PUBLIC, 31, "island"),
    ("'order-total'", COUPON_PUBLIC, 33, "island"),
    ('[data-testid="coupon-apply"]', COUPON_PUBLIC, 37, "island"),
    ('[data-testid="order-discount"]', COUPON_PUBLIC, 39, "island_discounted"),
    ('[data-testid="coupon-error"]', COUPON_PUBLIC, 51, "island_bogus_coupon"),
    ('[data-testid="checkout-confirmation"]', CONFIRMATION_EXISTS, 18, "confirmation"),
    ('[data-testid="confirmation-banner"]', CONFIRMATION_EXISTS, 23, "confirmation"),
    ('[data-testid="order-summary"]', DRAFT_CHECKOUT, 49, "island"),
    ('[data-testid="plan-name"]', DRAFT_CHECKOUT, 50, "island"),
    ('[data-testid="checkout-draft-expired"]', DRAFT_CHECKOUT, 65, "draft_expired"),
    ('[data-testid="order-summary"]', FIXTURES, 62, "island"),
    ('[data-testid="billing-address-block"]', FIXTURES, 65, "island"),
    ('[data-testid="billing-street"]', FIXTURES, 66, "island"),
    ('[data-testid="billing-first-name"]', FIXTURES, 71, "island"),
    ('[data-testid="billing-last-name"]', FIXTURES, 72, "island"),
    ('[data-testid="billing-city"]', FIXTURES, 74, "island"),
    ('[data-testid="billing-zip"]', FIXTURES, 75, "island"),
    ('[data-testid="billing-country"]', FIXTURES, 76, "island"),
    ('[data-testid="payment-methods-block"]', FIXTURES, 80, "island"),
    ('[data-testid="terms-checkbox"] input[type="checkbox"]', FIXTURES, 92, "island"),
    ('[data-testid="confirm-checkout"]', FIXTURES, 96, "island"),
]


def _themed_outputs(client, cms):
    def island(**fields):
        return client.post(
            "/_render/_fragment/checkout/form",
            data={"source": "fake", "cart": json.dumps(CART), **fields},
        ).get_data(as_text=True)

    _confirmation_page(cms, client)
    return {
        "island": island(),
        "island_discounted": island(coupon_action="apply", coupon_input="TENOFF"),
        "island_bogus_coupon": island(
            coupon_action="apply", coupon_input="NOTACODE123"
        ),
        "draft_expired": client.get("/checkout?draft=gone", headers=RENDER).get_data(
            as_text=True
        ),
        "confirmation": client.get(
            "/checkout/confirmation?invoice_id=00000000-0000-0000-0000-000000000000",
            headers=RENDER,
        ).get_data(as_text=True),
    }


def _present(selector, html):
    testid = re.search(r"data-testid=\"([^\"]+)\"|'([a-z-]+)'", selector)
    name = testid.group(1) or testid.group(2)
    element = re.search(rf'<[^>]*data-testid="{re.escape(name)}"[^>]*>', html)
    if element is None:
        return False
    if 'input[type="checkbox"]' in selector:
        after = html[element.end() :]
        return re.search(r'<input type="checkbox"', after) is not None
    return True


def test_every_spec_selector_is_in_the_themed_output(client, cms):
    outputs = _themed_outputs(client, cms)

    missing = [
        f"{spec}:{line} {selector} (in {output})"
        for selector, spec, line, output in CONTRACT
        if not _present(selector, outputs[output])
    ]

    assert not missing, missing


def test_the_spec_lines_still_use_these_selectors():
    if not (FE_USER_ROOT / COUPON_PUBLIC).is_file():
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    pins = [(selector, spec, line) for selector, spec, line, _output in CONTRACT]

    assert spec_selector_drift(FE_USER_ROOT, pins) == []
