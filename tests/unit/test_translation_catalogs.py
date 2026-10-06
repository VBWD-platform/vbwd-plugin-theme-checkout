"""S152-05b — theme_checkout's translated catalogs (de, es, …) keep the theme catalog contract.

They are generated from the fe-user locales by
``plugins/theme/bin/sync_translations_from_fe_user.py``; the drift test checks
their values against the SPA.
"""
from plugins.theme.tests.catalog_contract import catalog_contract_violations
from plugins.theme_checkout.theme_checkout.plugin_paths import TRANSLATIONS_DIRECTORY


def test_the_translated_catalogs_keep_the_contract():
    assert catalog_contract_violations(TRANSLATIONS_DIRECTORY) == []


def test_german_ui_strings_ship():
    assert (TRANSLATIONS_DIRECTORY / "de.json").is_file()
