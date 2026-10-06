"""Shared integration harness for the selling adapters (S152-08).

theme_shop, theme_dataset and theme_subscription each boot a real
``create_app`` in theme mode with their own plugin stack and drive the themed
checkout through its fragments. The boot (a stand-in for
``load_persisted_state`` enabling only the stack, in dependency order, with its
event + line-item handlers wired), the
rolled-back test transaction with the core test admin + user, and the
checkout-flow steps live here once.
"""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence, Tuple

import pytest

from plugins.theme.tests.e2e_spec_contract import spec_selector_drift
from vbwd.plugins.manager import PluginManager

RENDER = {"X-VBWD-Render": "1"}
FE_USER_ROOT = Path(__file__).resolve().parents[4].parent / "vbwd-fe-user"
SPA_ONLY_PREFIX = "/dashboard"
GOTO_TARGET = re.compile(r"page\.goto\(\s*[`'\"]([^`'\"$]*)")
# (selector text in the spec, spec path under fe-user, documented line, themed output
#  name, regex in it) — the drift guard reads the selector, never the line.
ContractRow = Tuple[str, str, int, str, str]
TEST_USER = {"email": "test@example.com", "password": "TestPass123@"}
ADMIN_USER = {"email": "admin@example.com", "password": "AdminPass123@"}
FORM_FRAGMENT = "/_render/_fragment/checkout/form"
SUBMIT_FRAGMENT = "/_render/_fragment/checkout/submit"
REGIONS_FRAGMENT = "/_render/_fragment/regions"
INVOICE_METHOD = {"code": "invoice", "name": "Invoice", "is_active": True}
EURO = {"code": "EUR", "name": "Euro", "symbol": "€", "exchange_rate": "1.0"}


def _test_database_url() -> str:
    base = os.getenv("DATABASE_URL", "postgresql://vbwd:vbwd@postgres:5432/vbwd")
    prefix, _, database_name = base.rpartition("/")
    return f"{prefix}/{database_name.split('?')[0]}_test"


@contextmanager
def themed_app(
    var_directory, boot_order: Iterable[str], fe_user_plugins: Iterable[str]
) -> Iterator[Any]:
    """A theme-mode app with exactly ``boot_order`` enabled and the fe-user toggles on."""
    from vbwd.app import create_app
    from vbwd.extensions import db
    from vbwd.testing.integration_db import ensure_schema_and_baseline

    manifest_path = var_directory / "fe-user-plugins.json"
    manifest_path.write_text(
        json.dumps({"plugins": {name: {"enabled": True} for name in fe_user_plugins}}),
        encoding="utf-8",
    )

    def enable_only_the_stack(plugin_manager: PluginManager) -> None:
        from vbwd.events.bus import event_bus
        from vbwd.events.line_item_registry import line_item_registry

        for plugin_name in boot_order:
            plugin = plugin_manager.get_plugin(plugin_name)
            plugin.validate_environment()
            plugin.enable()
            # As load_persisted_state wires them: a paid invoice reaches the plugins.
            plugin.register_event_handlers(event_bus)
            plugin.register_line_item_handlers(line_item_registry)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(PluginManager, "load_persisted_state", enable_only_the_stack)
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


@contextmanager
def rolled_back_test_data(app) -> Iterator[Any]:
    """One test's transaction (rolled back) with the core test admin + user seeded."""
    from vbwd.extensions import db
    from vbwd.testing.integration_db import rollback_isolation
    from vbwd.testing.test_data_seeder import TestDataSeeder

    with app.app_context():
        with rollback_isolation(db):
            previous_seed_flag = os.environ.get("TEST_DATA_SEED")
            os.environ["TEST_DATA_SEED"] = "true"
            try:
                TestDataSeeder(db.session).seed()
            finally:
                if previous_seed_flag is None:
                    os.environ.pop("TEST_DATA_SEED", None)
                else:
                    os.environ["TEST_DATA_SEED"] = previous_seed_flag
            yield db


def bearer_of(client, credentials: Mapping[str, str]) -> Dict[str, str]:
    login = client.post("/api/v1/auth/login", json=dict(credentials))
    assert login.status_code == 200, login.get_json()
    body = login.get_json()
    return {"Authorization": f"Bearer {body.get('token') or body.get('access_token')}"}


def ensure_invoice_payment_method(client, admin_headers: Mapping[str, str]) -> None:
    """The ``invoice`` method the specs pick, created inside the test's rollback."""
    methods = client.get("/api/v1/settings/payment-methods?currency=EUR").get_json()
    if any(method["code"] == "invoice" for method in methods.get("methods") or []):
        return
    created = client.post(
        "/api/v1/admin/payment-methods/", json=INVOICE_METHOD, headers=admin_headers
    )
    assert created.status_code == 201, created.get_json()


def ensure_euro_currency(client, admin_headers: Mapping[str, str]) -> None:
    """The operating currency the sellables' pricing resolves in (a cold test DB has none)."""
    listing = client.get("/api/v1/admin/currencies", headers=admin_headers).get_json()
    currencies = listing.get("currencies") if isinstance(listing, dict) else listing
    if any(currency.get("code") == EURO["code"] for currency in currencies or []):
        return
    created = client.post("/api/v1/admin/currencies", json=EURO, headers=admin_headers)
    assert created.status_code == 201, created.get_json()


def post_island(client, bearer, fields: Mapping[str, Any]) -> str:
    response = client.post(FORM_FRAGMENT, data=dict(fields), headers=bearer)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_data(as_text=True)


def submit_checkout(client, bearer, fields: Mapping[str, Any]):
    """Confirm with the invoice method and accepted terms (fillCheckoutRequirements)."""
    return client.post(
        SUBMIT_FRAGMENT,
        data={**fields, "payment_method": "invoice", "terms": "1"},
        headers=bearer,
    )


def regions_html(client, bearer, path: str) -> str:
    response = client.get(REGIONS_FRAGMENT, query_string={"path": path}, headers=bearer)
    assert response.status_code == 200, response.get_data(as_text=True)
    return "".join(response.get_json()["regions"].values())


def confirmation_page(cms, client) -> Any:
    """The ``checkout-confirmation`` CMS page with its CheckoutConfirmation widget."""
    existing = client.get("/api/v1/cms/posts/checkout-confirmation")
    if existing.status_code == 200:
        return existing.get_json()
    widget = cms.vue_widget("CheckoutConfirmation")
    return cms.page_with_widgets([widget], slug="checkout-confirmation")


def contract_misses(
    rows: Sequence[ContractRow], outputs: Mapping[str, str]
) -> List[str]:
    """Rows whose selector is not in its themed output (D2 / R4)."""
    return [
        f"{spec}:{line} {fragment} (in {output})"
        for fragment, spec, line, output, pattern in rows
        if not re.search(pattern, outputs[output])
    ]


def contract_drift(rows: Sequence[ContractRow]) -> List[str]:
    """Rows whose selector the spec no longer uses (the line only documents it)."""
    return spec_selector_drift(
        FE_USER_ROOT, ((fragment, spec, line) for fragment, spec, line, *_ in rows)
    )


def themed_page_gotos(spec: str) -> List[str]:
    """The spec's ``page.goto`` targets outside the SPA-only dashboard (D7)."""
    source = (FE_USER_ROOT / spec).read_text(encoding="utf-8")
    return [
        target
        for target in GOTO_TARGET.findall(source)
        if not target.startswith(SPA_ONLY_PREFIX)
    ]
