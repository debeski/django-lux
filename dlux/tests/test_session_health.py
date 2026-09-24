"""A password that is accepted and a login page that returns anyway.

The browser discards a session cookie it cannot store for the page it is on, and
nothing in the login flow fails — so the only place this can be reported is the
login page itself.
"""

from django.test import RequestFactory, SimpleTestCase, override_settings

from dlux.auth.session_health import session_cookie_problem


class SessionCookieProblemTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, secure=False, host="localhost"):
        return self.factory.get("/accounts/login/", secure=secure, HTTP_HOST=host)

    @override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_DOMAIN=None)
    def test_a_secure_cookie_on_an_http_page_is_reported(self):
        message = session_cookie_problem(self._request())
        self.assertIn("Secure", message)
        self.assertIn("HTTP", message)

    @override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_DOMAIN=None)
    def test_the_same_page_over_https_is_fine(self):
        self.assertEqual(session_cookie_problem(self._request(secure=True)), "")

    @override_settings(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_DOMAIN="example.gov.ly")
    def test_a_cookie_scoped_to_another_domain_is_reported(self):
        message = session_cookie_problem(self._request(host="localhost:8088"))
        self.assertIn("example.gov.ly", message)
        self.assertIn("localhost", message)

    @override_settings(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_DOMAIN="example.gov.ly")
    def test_the_domain_itself_and_its_subdomains_are_fine(self):
        for host in ("example.gov.ly", "app.example.gov.ly"):
            with self.subTest(host=host):
                self.assertEqual(session_cookie_problem(self._request(host=host)), "")

    @override_settings(SESSION_COOKIE_SECURE=False, SESSION_COOKIE_DOMAIN=None)
    def test_a_plain_deployment_reports_nothing(self):
        self.assertEqual(session_cookie_problem(self._request()), "")

    @override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_DOMAIN="example.gov.ly")
    def test_the_transport_is_named_before_the_domain(self):
        # Both are wrong on http://localhost; fixing the transport first is the
        # advice that also works for a deployment behind a proxy.
        message = session_cookie_problem(self._request(host="localhost"))
        self.assertIn("Secure", message)

    @override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_DOMAIN=None)
    def test_the_sites_own_wording_is_used_when_it_has_one(self):
        message = session_cookie_problem(self._request(), {"login_cookie_insecure": "لا يمكن إتمام الدخول"})
        self.assertEqual(message, "لا يمكن إتمام الدخول")
