"""Integration fixtures: a real ``create_app`` in theme mode with the payment theme stack.

* Boot: cms, checkout, stripe, paypal, token_payment (the REAL payment plugins
  and their routes), theme, theme_cms, theme_checkout (which carries the payment
  flows) and the theme_checkout test selling adapter (for the instant-pay dispatch).
* The payment plugins' "enabled" status + sandbox config come from an overlay on
  the real config store (``check_plugin_enabled`` reads it); nothing is written.
* Provider SDK traffic is stubbed per test at the outbound boundary only
  (``stripe.checkout.Session``, ``requests`` for PayPal) — no domain plugin code
  is touched. Data: shared ``*_test`` DB, rolled back per test.
"""
import json
import os
from decimal import Decimal

import pytest

from vbwd.plugins.config_store import PluginConfigEntry
from vbwd.plugins.manager import PluginManager

from plugins.theme_checkout.tests.integration.fake_checkout_adapter import (
    FAKE_CHECKOUT_ADAPTER_NAME,
    FakeCheckoutAdapterPlugin,
)

BOOT_ORDER = (
    "cms",
    "checkout",
    "stripe",
    "paypal",
    "token_payment",
    "theme",
    "theme_cms",
    "theme_checkout",
    FAKE_CHECKOUT_ADAPTER_NAME,
)
FE_USER_PLUGINS = (
    "cms",
    "checkout",
    "stripe-payment",
    "paypal-payment",
    "token-payment",
)
PAYMENT_PLUGIN_CONFIG = {
    "stripe": {"sandbox": True, "test_secret_key": "sk_test_theme_checkout_payment"},
    "paypal": {"sandbox": True, "test_client_id": "id", "test_client_secret": "secret"},
    "token_payment": {},
}
TEST_USER = {"email": "test@example.com", "password": "TestPass123@"}


def _test_database_url() -> str:
    base = os.getenv("DATABASE_URL", "postgresql://vbwd:vbwd@postgres:5432/vbwd")
    prefix, _, database_name = base.rpartition("/")
    return f"{prefix}/{database_name.split('?')[0]}_test"


def _enable_only_the_payment_theme_stack(plugin_manager: PluginManager) -> None:
    plugin_manager.register_plugin(FakeCheckoutAdapterPlugin())
    plugin_manager.initialize_plugin(FAKE_CHECKOUT_ADAPTER_NAME)
    for plugin_name in BOOT_ORDER:
        plugin = plugin_manager.get_plugin(plugin_name)
        plugin.validate_environment()
        plugin.enable()


class PaymentPluginsEnabledStore:
    """The real config store, with the payment plugins reported enabled + configured."""

    def __init__(self, real_store):
        self._real_store = real_store

    def get_by_name(self, plugin_name):
        if plugin_name in PAYMENT_PLUGIN_CONFIG:
            return PluginConfigEntry(
                plugin_name=plugin_name,
                status="enabled",
                config=PAYMENT_PLUGIN_CONFIG[plugin_name],
            )
        return self._real_store.get_by_name(plugin_name)

    def get_config(self, plugin_name):
        if plugin_name in PAYMENT_PLUGIN_CONFIG:
            return dict(PAYMENT_PLUGIN_CONFIG[plugin_name])
        return self._real_store.get_config(plugin_name)

    def __getattr__(self, name):
        return getattr(self._real_store, name)


@pytest.fixture(scope="module")
def manifest_path(tmp_path_factory):
    path = (
        tmp_path_factory.mktemp("theme-checkout-payment-var") / "fe-user-plugins.json"
    )
    write_manifest(path, FE_USER_PLUGINS)
    return path


def write_manifest(path, enabled_plugins):
    path.write_text(
        json.dumps({"plugins": {name: {"enabled": True} for name in enabled_plugins}}),
        encoding="utf-8",
    )
    stat = os.stat(path)
    later = stat.st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(later, later))


@pytest.fixture(scope="module")
def app(manifest_path):
    from vbwd.app import create_app
    from vbwd.extensions import db
    from vbwd.testing.integration_db import ensure_schema_and_baseline

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            PluginManager, "load_persisted_state", _enable_only_the_payment_theme_stack
        )
        patch.setenv("VBWD_FRONTEND_MODE", "theme")
        patch.setenv("VBWD_VAR_DIR", str(manifest_path.parent))
        patch.setenv("VBWD_FE_USER_PLUGINS_JSON", str(manifest_path))
        application = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": _test_database_url(),
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "RATELIMIT_ENABLED": False,
            }
        )
        application.config_store = PaymentPluginsEnabledStore(application.config_store)
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
    login = client.post("/api/v1/auth/login", json=TEST_USER)
    assert login.status_code == 200, login.get_json()
    return {"Authorization": f"Bearer {login.get_json()['token']}"}


@pytest.fixture
def pending_invoice(app, db):
    """A PENDING invoice of the seeded test user, saved through the core model."""
    from vbwd.models.enums import InvoiceStatus
    from vbwd.models.invoice import UserInvoice

    user = app.container.user_repository().find_by_email(TEST_USER["email"])
    invoice = UserInvoice(
        user_id=user.id,
        invoice_number="INV-S152-07-PAY",
        amount=Decimal("49.00"),
        total_amount=Decimal("49.00"),
        currency="EUR",
        status=InvoiceStatus.PENDING,
    )
    db.session.add(invoice)
    db.session.flush()
    return invoice
