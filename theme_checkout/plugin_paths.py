"""Where theme_checkout's contributed templates and translations live."""
from pathlib import Path

PACKAGE_DIRECTORY = Path(__file__).resolve().parent
TEMPLATES_DIRECTORY = PACKAGE_DIRECTORY / "templates"
TRANSLATIONS_DIRECTORY = PACKAGE_DIRECTORY / "translations"
