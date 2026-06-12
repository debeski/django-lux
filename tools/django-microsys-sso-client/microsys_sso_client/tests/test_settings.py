from unittest import TestCase

from microsys_sso_client.settings import configure_microsys_sso


class MicrosysSSOClientSettingsTests(TestCase):
    def test_configure_client_is_idempotent_and_does_not_require_microsys(self):
        scope = {
            "INSTALLED_APPS": ["django.contrib.auth"],
            "MIDDLEWARE": [
                "django.contrib.sessions.middleware.SessionMiddleware",
                "django.contrib.auth.middleware.AuthenticationMiddleware",
            ],
            "AUTHENTICATION_BACKENDS": [],
        }

        configure_microsys_sso(
            scope,
            issuer_url="https://sso.example.com/",
            client_id="client-id",
            client_secret="client-secret",
            role_mapping={"staff_roles": ["admin", "staff"]},
        )
        configure_microsys_sso(
            scope,
            issuer_url="https://sso.example.com/",
            client_id="client-id",
            client_secret="client-secret",
            role_mapping={"staff_roles": ["admin", "staff"]},
        )

        self.assertEqual(scope["INSTALLED_APPS"].count("microsys_sso_client"), 1)
        self.assertNotIn("microsys", scope["INSTALLED_APPS"])
        self.assertEqual(
            scope["AUTHENTICATION_BACKENDS"][0],
            "microsys_sso_client.backends.MicrosysSSOAuthenticationBackend",
        )
        self.assertEqual(scope["OIDC_OP_AUTHORIZATION_ENDPOINT"], "https://sso.example.com/o/authorize/")
        self.assertTrue(scope["OIDC_USE_NONCE"])
        self.assertEqual(scope["MICROSYS_SSO_CLIENT"]["staff_roles"], ["admin", "staff"])

