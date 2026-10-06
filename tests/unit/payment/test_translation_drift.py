"""S152-07 C — the payment entries of theme_checkout's catalog equal the SPA payment plugins' copy.

Each built-in flow's namespace carries every key the generic ``/pay/*`` templates
compose (``<namespace>.payment.*``, ``.success.*``, ``.cancel.*``); the
``payment.errors.*`` keys are the SPA composables' hard-coded English. The
fe-user half skips when fe-user is not next to vbwd-backend (plugin CI). The
catalog is shared with the checkout (layout B); only payment keys are checked here.
"""
import json
import re
from pathlib import Path

import pytest

from plugins.theme.tests.catalog_contract import translated_catalog_paths
from plugins.theme_checkout.theme_checkout.payment import flow_pages
from plugins.theme_checkout.theme_checkout.payment.flow_descriptors import (
    BUILT_IN_FLOWS,
)
from plugins.theme_checkout.theme_checkout.plugin_paths import TRANSLATIONS_DIRECTORY
from plugins.theme_checkout.tests.unit.payment.payment_catalog import is_payment_key

FE_USER_PLUGINS = (
    Path(__file__).resolve().parents[5].parent / "vbwd-fe-user" / "plugins"
)
COMPOSED_SUFFIXES = (
    "payment.redirecting",
    "payment.retry",
    "payment.noInvoice",
    "success.verifying",
    "success.viewInvoices",
    "cancel.title",
    "cancel.message",
    "cancel.tryAgain",
)
POLL_SUFFIXES = ("success.processing", "success.viewOrder")
CAPTURE_SUFFIXES = ("success.title", "success.message")
ERROR_COPY = {
    flow_pages.NO_REDIRECT_URL_KEY: "No redirect URL received",
    flow_pages.SESSION_FAILED_KEY: "Payment session failed",
    flow_pages.NO_SESSION_KEY: "No session ID",
    flow_pages.STATUS_FAILED_KEY: "Status check failed",
    flow_pages.NO_ORDER_TOKEN_KEY: "No order token found",
    flow_pages.CAPTURE_FAILED_KEY: "Payment capture failed",
}


def _payment_entries(catalog_path):
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {key: value for key, value in catalog.items() if is_payment_key(key)}


def _catalog():
    return _payment_entries(TRANSLATIONS_DIRECTORY / "en.json")


def _flatten(prefix, node):
    for key, value in node.items():
        if isinstance(value, dict):
            yield from _flatten(f"{prefix}{key}.", value)
        else:
            yield f"{prefix}{key}", value


def test_every_flow_namespace_has_the_composed_keys():
    catalog = _catalog()
    for descriptor in BUILT_IN_FLOWS:
        kind_suffixes = (
            CAPTURE_SUFFIXES
            if descriptor.success_handling.value == "capture_order"
            else POLL_SUFFIXES
        )
        for suffix in COMPOSED_SUFFIXES + kind_suffixes:
            assert f"{descriptor.namespace}.{suffix}" in catalog, (
                descriptor.provider,
                suffix,
            )


def test_error_copy_is_the_spa_composables_english():
    catalog = _catalog()

    assert {key: catalog[key] for key in ERROR_COPY} == ERROR_COPY


def _flow_catalogs(language):
    return [
        FE_USER_PLUGINS
        / f"{descriptor.fe_user_plugin}"
        / "locales"
        / f"{language}.json"
        for descriptor in BUILT_IN_FLOWS
    ]


def test_every_flow_entry_equals_the_spa_english():
    catalogs = _flow_catalogs("en")
    if not all(path.is_file() for path in catalogs):
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    spa = {}
    for path in catalogs:
        spa.update(_flatten("", json.loads(path.read_text(encoding="utf-8"))))
    drifted = {
        key: (value, spa.get(key))
        for key, value in _catalog().items()
        if key not in ERROR_COPY
        and re.sub(r"%\((\w+)\)s", r"{\1}", value) != spa.get(key)
    }

    assert not drifted, drifted


def test_every_translated_entry_equals_the_spa_translation():
    if not all(path.is_file() for path in _flow_catalogs("en")):
        pytest.skip("fe-user is not next to vbwd-backend (plugin CI)")
    drifted = {}
    for catalog_path in translated_catalog_paths(TRANSLATIONS_DIRECTORY):
        spa = {}
        for path in _flow_catalogs(catalog_path.stem):
            if path.is_file():
                spa.update(_flatten("", json.loads(path.read_text(encoding="utf-8"))))
        for key, value in _payment_entries(catalog_path).items():
            if re.sub(r"%\((\w+)\)s", r"{\1}", value) != spa.get(key):
                drifted[f"{catalog_path.stem}:{key}"] = (value, spa.get(key))

    assert not drifted, drifted
