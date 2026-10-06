"""Where theme_checkout's contributed templates, translations and stylesheets live."""
from pathlib import Path

PACKAGE_DIRECTORY = Path(__file__).resolve().parent
TEMPLATES_DIRECTORY = PACKAGE_DIRECTORY / "templates"
TRANSLATIONS_DIRECTORY = PACKAGE_DIRECTORY / "translations"
# ``public/`` CSS: the SPA checkout, confirmation and payment view CSS (S152-06c/06d rules).
STYLESHEETS_DIRECTORY = PACKAGE_DIRECTORY / "stylesheets"
