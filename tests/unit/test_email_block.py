"""S152-07 B — the checkout ``EmailBlock`` fragments (``useEmailCheck`` + login/register).

* email check: trimmed + lower-cased; an invalid address (or one with ``+``) is
  ``idle`` (no API call); ``GET /auth/check-email`` → existing / new user;
  a failure → ``error``.
* login / register: a token → the session directive with EmailBlock's keys
  (``auth_token``, ``user_id``, ``user_email``; no redirect — the island
  re-renders logged in); otherwise EmailBlock's error copy.
"""
import pytest

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme_checkout.tests.unit.fakes import FakeCheckoutApi, FakeThemeRequest
from plugins.theme_checkout.theme_checkout.email_block import EmailBlock


def _block(**answers):
    api = FakeCheckoutApi(**answers)
    return EmailBlock(api_factory=api.factory), api


@pytest.mark.parametrize(
    "raw_email", ["", "not-an-email", "a+tag@example.com", "a@b", "a@b.c"]
)
def test_an_invalid_email_is_idle_without_an_api_call(raw_email):
    block, api = _block()

    assert block.check_context(FakeThemeRequest({"email": raw_email})) == {
        "state": "idle",
        "email": "",
    }
    assert api.calls == []


@pytest.mark.parametrize(
    "exists, state", [(True, "existing_user"), (False, "new_user")]
)
def test_a_valid_email_is_checked_normalised(exists, state):
    block, api = _block(check_email={"exists": exists})

    context = block.check_context(FakeThemeRequest({"email": "  Buyer@Example.COM "}))

    assert context == {"state": state, "email": "buyer@example.com"}
    assert api.called("check_email") == [("check_email", "buyer@example.com")]


def test_a_failed_check_is_the_error_state():
    block, _api = _block(check_email=ThemeApiError(429, "slow down"))

    assert block.check_context(FakeThemeRequest({"email": "a@example.com"}))[
        "state"
    ] == ("error")


def test_login_with_a_token_starts_the_inline_session():
    block, api = _block(
        login={
            "success": True,
            "token": "t",
            "user_id": "u-1",
            "user": {"email": "x@y.zz"},
        }
    )

    context = block.login_context(
        FakeThemeRequest({"email": "a@example.com", "password": "pw"})
    )

    assert api.called("login") == [("login", "a@example.com", "pw")]
    assert context == {
        "session": {"token": "t", "user_id": "u-1", "user_email": "x@y.zz"},
        "error_message": None,
        "error_key": None,
    }


def test_login_without_a_user_email_keeps_the_typed_email():
    block, _api = _block(login={"token": "t", "user_id": "u-1"})

    context = block.login_context(
        FakeThemeRequest({"email": "a@example.com", "password": "pw"})
    )

    assert context["session"]["user_email"] == "a@example.com"


def test_a_refused_login_shows_the_retry_copy():
    block, _api = _block(login=ThemeApiError(401, "Invalid credentials"))

    context = block.login_context(
        FakeThemeRequest({"email": "a@example.com", "password": "x"})
    )

    assert context == {
        "session": None,
        "error_message": None,
        "error_key": "common.errors.loginFailedRetry",
    }


def test_a_tokenless_login_body_shows_its_error_or_login_failed():
    with_error, _ = _block(login={"success": False, "error": "Account locked"})
    without_error, _ = _block(login={"success": False})
    request = FakeThemeRequest({"email": "a@example.com", "password": "x"})

    assert with_error.login_context(request)["error_message"] == "Account locked"
    assert (
        without_error.login_context(request)["error_key"] == "common.errors.loginFailed"
    )


def test_register_with_a_token_starts_the_inline_session():
    block, api = _block(register={"success": True, "token": "t", "user_id": "u-2"})

    context = block.register_context(
        FakeThemeRequest({"email": "new@example.com", "password": "Str0ng!Passw0rd"})
    )

    assert api.called("register") == [
        ("register", "new@example.com", "Str0ng!Passw0rd")
    ]
    assert context["session"] == {
        "token": "t",
        "user_id": "u-2",
        "user_email": "new@example.com",
    }


def test_a_refused_registration_shows_the_api_message():
    block, _api = _block(register=ThemeApiError(400, "Email already registered"))

    context = block.register_context(
        FakeThemeRequest({"email": "a@example.com", "password": "x"})
    )

    assert context["error_message"] == "Email already registered"
    assert context["session"] is None
