"""The checkout ``EmailBlock`` fragments — ``useEmailCheck`` and the inline login/sign-up.

A token answers the runtime's session directive with EmailBlock's keys
(``auth_token``, ``user_id``, ``user_email``) and no redirect: the runtime fires
``vbwd:session-started`` and the island re-renders for the logged-in buyer.
"""
import re
from typing import Any, Callable, Dict, Mapping, Optional

from plugins.theme.theme.theme_api import ThemeApiError
from plugins.theme.theme.theme_request import ThemeRequest

from .checkout_api import CheckoutApi

# useEmailCheck.isValidEmail — and no "+" (Q&A decision in the SPA).
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PLUS_SIGN = "+"
LOGIN_FAILED_KEY = "common.errors.loginFailed"
LOGIN_FAILED_RETRY_KEY = "common.errors.loginFailedRetry"
REGISTRATION_FAILED_KEY = "common.errors.registrationFailed"
REGISTRATION_FAILED_RETRY_KEY = "common.errors.registrationFailedRetry"


def _normalised_email(raw_email: Optional[str]) -> Optional[str]:
    email = (raw_email or "").strip().lower()
    if not EMAIL_PATTERN.match(email) or PLUS_SIGN in email:
        return None
    return email


def _auth_result(
    body: Mapping[str, Any], typed_email: str, failed_key: str
) -> Dict[str, Any]:
    if not body.get("token"):
        error_message = body.get("error") or None
        return {
            "session": None,
            "error_message": error_message,
            "error_key": None if error_message else failed_key,
        }
    return {
        "session": {
            "token": body["token"],
            "user_id": body.get("user_id"),
            "user_email": (body.get("user") or {}).get("email") or typed_email,
        },
        "error_message": None,
        "error_key": None,
    }


class EmailBlock:
    """Context builders of the three EmailBlock fragments."""

    def __init__(
        self, api_factory: Callable[[ThemeRequest], Any] = CheckoutApi
    ) -> None:
        self._api_factory = api_factory

    def check_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        email = _normalised_email(theme_request.query_args.get("email"))
        if email is None:
            return {"state": "idle", "email": ""}
        try:
            exists = self._api_factory(theme_request).check_email(email).get("exists")
        except ThemeApiError:
            return {"state": "error", "email": email}
        return {"state": "existing_user" if exists else "new_user", "email": email}

    def login_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        email, password = self._credentials(theme_request)
        try:
            body = self._api_factory(theme_request).login(email, password)
        except ThemeApiError:
            return {
                "session": None,
                "error_message": None,
                "error_key": LOGIN_FAILED_RETRY_KEY,
            }
        return _auth_result(body, email, LOGIN_FAILED_KEY)

    def register_context(self, theme_request: ThemeRequest) -> Dict[str, Any]:
        email, password = self._credentials(theme_request)
        try:
            body = self._api_factory(theme_request).register(email, password)
        except ThemeApiError as refusal:
            return {
                "session": None,
                "error_message": refusal.message or None,
                "error_key": None if refusal.message else REGISTRATION_FAILED_RETRY_KEY,
            }
        return _auth_result(body, email, REGISTRATION_FAILED_KEY)

    @staticmethod
    def _credentials(theme_request: ThemeRequest) -> "tuple[str, str]":
        form = theme_request.query_args
        email = (
            _normalised_email(form.get("email")) or (form.get("email") or "").strip()
        )
        return email, form.get("password") or ""
