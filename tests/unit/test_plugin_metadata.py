"""Metadata + baseline-config contract for the theme_checkout plugin (S152-00b)."""
import json
from pathlib import Path

from plugins.theme_checkout import ThemeCheckoutPlugin

PLUGIN_DIRECTORY = Path(__file__).resolve().parents[2]


def _load_plugin_json(file_name: str) -> dict:
    return json.loads((PLUGIN_DIRECTORY / file_name).read_text(encoding="utf-8"))


def test_metadata_name_is_the_manifest_key():
    assert ThemeCheckoutPlugin().metadata.name == "theme_checkout"


def test_metadata_version():
    assert ThemeCheckoutPlugin().metadata.version == "1.0.0"


def test_dependencies_are_exactly_declared():
    """theme_cms: /checkout/confirmation is the ``checkout-confirmation`` CMS page and
    the checkout widgets are CMS components — fe-user checkout imports cms the same way.
    """
    assert ThemeCheckoutPlugin().metadata.dependencies == [
        "theme>=1.0",
        "theme_cms",
        "checkout",
    ]


def test_mounts_no_blueprint_of_its_own():
    plugin = ThemeCheckoutPlugin()

    assert plugin.get_url_prefix() == ""
    assert plugin.get_blueprint() is None


def test_admin_config_fields_all_exist_in_config():
    config = _load_plugin_json("config.json")
    admin_config = _load_plugin_json("admin-config.json")
    admin_field_keys = [
        field["key"] for tab in admin_config["tabs"] for field in tab["fields"]
    ]

    assert admin_field_keys
    assert set(admin_field_keys) <= set(config)


def test_debug_mode_toggle_defaults_off():
    assert _load_plugin_json("config.json")["debug_mode"]["default"] is False
