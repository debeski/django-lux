from types import SimpleNamespace
from unittest import TestCase

from microsys_sso.services import build_userinfo_claims, validate_redirect_uri


class RedirectPolicyTests(TestCase):
    def test_redirect_uri_must_be_exactly_registered(self):
        app = SimpleNamespace(redirect_uris="https://client.example/callback")

        self.assertEqual(
            validate_redirect_uri(app, "https://client.example/other"),
            (False, "redirect_uri_not_registered"),
        )

    def test_https_is_required_when_localhost_is_not_allowed(self):
        app = SimpleNamespace(redirect_uris="http://client.example/callback")

        self.assertEqual(
            validate_redirect_uri(app, "http://client.example/callback", require_https=True),
            (False, "redirect_uri_requires_https"),
        )

    def test_localhost_http_can_be_allowed_for_development(self):
        app = SimpleNamespace(redirect_uris="http://localhost:8000/callback")

        self.assertEqual(
            validate_redirect_uri(
                app,
                "http://localhost:8000/callback",
                require_https=True,
                allow_localhost=True,
            ),
            (True, ""),
        )

    def test_userinfo_claims_are_portable_and_do_not_export_permissions(self):
        user = SimpleNamespace(
            pk=42,
            is_authenticated=True,
            is_active=True,
            email="admin@example.com",
            first_name="Ada",
            last_name="Lovelace",
            get_username=lambda: "ada",
            get_full_name=lambda: "Ada Lovelace",
        )
        policy = SimpleNamespace(is_active=True, allow_all_authenticated=True)
        app = SimpleNamespace(client_id="client-123", microsys_sso_policy=policy)

        claims = build_userinfo_claims(user, app)

        self.assertEqual(claims["sub"], "42")
        self.assertEqual(claims["microsys_sso_role"], "user")
        self.assertEqual(claims["microsys_sso"]["role"], "user")
        self.assertEqual(claims["microsys_sso_client_id"], "client-123")
        self.assertNotIn("permissions", claims)
        self.assertNotIn("is_superuser", claims)
