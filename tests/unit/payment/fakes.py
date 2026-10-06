"""Test doubles for the payment-flow unit tests (``FakeThemeRequest`` is in ``../fakes.py``)."""


class FakeProviderApi:
    """Same methods as ``ProviderApi``; answers by method name (a list = one per call).

    An answer that is an exception instance is raised, as ``call_api`` raises
    ``ThemeApiError`` on a non-2xx status.
    """

    def __init__(self, **answers):
        self.answers = answers
        self.calls = []

    def _answer(self, name, *arguments):
        self.calls.append((name,) + arguments)
        answer = self.answers.get(name)
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def factory(self, descriptor, theme_request):
        self.descriptor = descriptor
        return self

    def create_session(self, invoice_id):
        return self._answer("create_session", invoice_id)

    def session_status(self, session_id):
        return self._answer("session_status", session_id)

    def capture_order(self, order_id):
        return self._answer("capture_order", order_id)
