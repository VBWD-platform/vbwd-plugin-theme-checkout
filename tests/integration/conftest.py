"""Integration fixtures: a real ``create_app`` in theme mode with the checkout theme stack.

* Boot is narrowed to cms, checkout, theme, theme_cms, theme_checkout and a
  test-only selling adapter (``fake_checkout_adapter.py``), enabled in
  dependency order by a stand-in for ``load_persisted_state``.
* The fe-user manifest enables fe-user "cms" and "checkout".
* Data lives in the shared ``*_test`` database; each test runs in a rolled-back
  transaction (core ``rollback_isolation``) with the core test admin + user
  seeded inside it. cms content is seeded through the cms admin HTTP API.
"""
import json
import os

import pytest

from vbwd.plugins.manager import PluginManager

from plugins.theme_checkout.tests.integration.fake_checkout_adapter import (
    FAKE_CHECKOUT_ADAPTER_NAME,
    FakeCheckoutAdapterPlugin,
)

BOOT_ORDER = (
    "cms",
    "checkout",
    "theme",
    "theme_cms",
    "theme_checkout",
    FAKE_CHECKOUT_ADAPTER_NAME,
)
TEST_USER = {"email": "test@example.com", "password": "TestPass123@"}


def _test_database_url() -> str:
    base = os.getenv("DATABASE_URL", "postgresql://vbwd:vbwd@postgres:5432/vbwd")
    prefix, _, database_name = base.rpartition("/")
    return f"{prefix}/{database_name.split('?')[0]}_test"


def _enable_only_the_checkout_theme_stack(plugin_manager: PluginManager) -> None:
    plugin_manager.register_plugin(FakeCheckoutAdapterPlugin())
    plugin_manager.initialize_plugin(FAKE_CHECKOUT_ADAPTER_NAME)
    for plugin_name in BOOT_ORDER:
        plugin = plugin_manager.get_plugin(plugin_name)
        plugin.validate_environment()
        plugin.enable()


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    from vbwd.app import create_app
    from vbwd.extensions import db
    from vbwd.testing.integration_db import ensure_schema_and_baseline

    var_directory = tmp_path_factory.mktemp("theme-checkout-var")
    manifest_path = var_directory / "fe-user-plugins.json"
    manifest_path.write_text(
        json.dumps(
            {"plugins": {"cms": {"enabled": True}, "checkout": {"enabled": True}}}
        ),
        encoding="utf-8",
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            PluginManager, "load_persisted_state", _enable_only_the_checkout_theme_stack
        )
        patch.setenv("VBWD_FRONTEND_MODE", "theme")
        patch.setenv("VBWD_VAR_DIR", str(var_directory))
        patch.setenv("VBWD_FE_USER_PLUGINS_JSON", str(manifest_path))
        application = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": _test_database_url(),
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "RATELIMIT_ENABLED": False,
            }
        )
        with application.app_context():
            ensure_schema_and_baseline(db)
        yield application
        with application.app_context():
            db.engine.dispose()


@pytest.fixture
def db(app):
    from vbwd.extensions import db as database
    from vbwd.testing.integration_db import rollback_isolation
    from vbwd.testing.test_data_seeder import TestDataSeeder

    with app.app_context():
        with rollback_isolation(database):
            previous_seed_flag = os.environ.get("TEST_DATA_SEED")
            os.environ["TEST_DATA_SEED"] = "true"
            try:
                TestDataSeeder(database.session).seed()
            finally:
                if previous_seed_flag is None:
                    os.environ.pop("TEST_DATA_SEED", None)
                else:
                    os.environ["TEST_DATA_SEED"] = previous_seed_flag
            yield database


@pytest.fixture
def client(app, db):
    return app.test_client()


@pytest.fixture
def bearer(client):
    """``Authorization`` header of the seeded test user (what the runtime sends)."""
    login = client.post("/api/v1/auth/login", json=TEST_USER)
    assert login.status_code == 200, login.get_json()
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


@pytest.fixture
def cms(client):
    from plugins.theme_cms.tests.integration.cms_seed import CmsAdminSeeder

    return CmsAdminSeeder(client)
