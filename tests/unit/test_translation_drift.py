"""S152-07 — theme_checkout's English catalog never drifts from the SPA's copy.

* Every message a template asks for (``_('…')``) and every error key the Python
  code chooses is in ``translations/en.json``.
* Every entry equals the SPA's English for the same key (fe-user core
  ``vue/src/i18n/locales/en.json`` + ``plugins/checkout/locales/en.json``), with
  ``%(name)s`` ≡ ``{name}``. Theme-only keys are the SPA's hard-coded English
  (checkout store errors, fe-core CouponInput defaults). The fe-user half skips
  when fe-user is not next to vbwd-backend (plugin CI).
* The payment flows' entries share these catalogs (layout B) and are checked
  against the SPA payment plugins by ``payment/test_translation_drift.py``.
"""
import json
import re
from pathlib import Path

import pytest

from plugins.theme.tests.catalog_contract import translated_catalog_paths
from plugins.theme_checkout.tests.unit.payment.payment_catalog import is_payment_key
from plugins.theme_checkout.theme_checkout import email_block, submit
from plugins.theme_checkout.theme_checkout.plugin_paths import (
    TEMPLATES_DIRECTORY,
    TRANSLATIONS_DIRECTORY,
)

FE_USER_ROOT = Path(__file__).resolve().parents[4].parent / "vbwd-fe-user"
FE_USER_CATALOGS = (
    FE_USER_ROOT / "vue" / "src" / "i18n" / "locales" / "en.json",
    FE_USER_ROOT / "plugins" / "checkout" / "locales" / "en.json",
)
THEME_ONLY_COPY = {
    "checkout.errors.noItemsSelected": "No items selected",
    "checkout.errors.checkoutFailed": "Checkout failed",
    "checkout.coupon.placeholder": "Coupon code",
    "checkout.coupon.apply": "Apply",
    "checkout.coupon.remove": "Remove",
    "checkout.coupon.appliedLabel": "Coupon applied:",
}
CODE_CHOSEN_KEYS = {
    email_block.LOGIN_FAILED_KEY,
    email_block.LOGIN_FAILED_RETRY_KEY,
    email_block.REGISTRATION_FAILED_KEY,
    email_block.REGISTRATION_FAILED_RETRY_KEY,
    submit.NO_ITEMS_SELECTED_KEY,
    submit.CHECKOUT_FAILED_KEY,
}
TRANSLATION_CALL = re.compile(r"""_\(\s*'([A-Za-z0-9_.]+)'\s*[,)]""")


def _checkout_entries(catalog_path):
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {key: value for key, value in catalog.items() if not is_payment_key(key)}


def _catalog():
    return _checkout_entries(TRANSLATIONS_DIRECTORY / "en.json")


def _flatten(prefix, node):
    for key, value in node.items():
        if isinstance(value, dict):
            yield from _flatten(f"{prefix}{key}.", value)
        else:
            yield f"{prefix}{key}", value


def _template_keys():
    keys = set()
    for template in TEMPLATES_DIRECTORY.rglob("*.j2"):
        keys.update(TRANSLATION_CALL.findall(template.read_text(encoding="utf-8")))
    return keys


def test_every_requested_message_is_in_the_catalog():
    missing = (_template_keys() | CODE_CHOSEN_KEYS) - set(_catalog())

    assert not missing, sorted(missing)


def test_the_catalog_has_no_unused_entries():
    unused = set(_catalog()) - _template_keys() - CODE_CHOSEN_KEYS

    assert not unused, sorted(unused)


def test_theme_only_copy_is_the_spa_hard_coded_english():
    catalog = _catalog()

    assert {key: catalog[key] for key in THEME_ONLY_COPY} == THEME_ONLY_COPY


def test_every_entry_equals_the_spa_english():
    if not all(path.is_file() for path in FE_USER_CATALOGS):
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    spa = {}
    for path in FE_USER_CATALOGS:
        spa.update(_flatten("", json.loads(path.read_text(encoding="utf-8"))))
    drifted = {
        key: (value, spa.get(key))
        for key, value in _catalog().items()
        if key not in THEME_ONLY_COPY
        and re.sub(r"%\((\w+)\)s", r"{\1}", value) != spa.get(key)
    }

    assert not drifted, drifted


def _spa_translations(language):
    """The SPA's messages in ``language``, merged in the same order as English."""
    spa = {}
    for path in FE_USER_CATALOGS:
        localized = path.with_name(f"{language}.json")
        if localized.is_file():
            spa.update(_flatten("", json.loads(localized.read_text(encoding="utf-8"))))
    return spa


def test_every_translated_entry_equals_the_spa_translation():
    if not all(path.is_file() for path in FE_USER_CATALOGS):
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    drifted = {}
    for catalog_path in translated_catalog_paths(TRANSLATIONS_DIRECTORY):
        spa = _spa_translations(catalog_path.stem)
        for key, value in _checkout_entries(catalog_path).items():
            if re.sub(r"%\((\w+)\)s", r"{\1}", value) != spa.get(key):
                drifted[f"{catalog_path.stem}:{key}"] = (value, spa.get(key))

    assert not drifted, drifted
