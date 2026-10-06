"""Render theme_checkout templates through the REAL theme renderer: the basic theme
plus the templates and translations theme_cms and theme_checkout contribute, and
a test-only ``fake/summary.html.j2`` standing in for a checkout source's summary.
"""
from pathlib import Path

from flask import Flask

from plugins.theme import ThemePlugin
from plugins.theme_checkout.theme_checkout.plugin_paths import (
    TEMPLATES_DIRECTORY,
    TRANSLATIONS_DIRECTORY,
)
from plugins.theme_cms.theme_cms import plugin_paths as theme_cms_paths

TEST_TEMPLATES = Path(__file__).parent / "templates"


def theme_plugin() -> ThemePlugin:
    plugin = ThemePlugin()
    plugin.on_enable()
    registry = plugin.theme_registry
    for templates in (
        theme_cms_paths.TEMPLATES_DIRECTORY,
        TEMPLATES_DIRECTORY,
        TEST_TEMPLATES,
    ):
        registry.add_contributed_template_path(templates)
    for translations in (
        theme_cms_paths.TRANSLATIONS_DIRECTORY,
        TRANSLATIONS_DIRECTORY,
    ):
        registry.add_contributed_translation_path(translations)
    return plugin


def render(plugin: ThemePlugin, template: str, context) -> str:
    app = Flask(__name__)
    app.testing = True
    with app.app_context():
        return plugin.renderer.render(
            template, {"language": "en", "default_language": "en", **context}
        )


def render_component(plugin: ThemePlugin, template: str, component_context) -> str:
    return render(plugin, template, {"component_context": component_context})
