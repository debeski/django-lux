from unittest import TestCase

from dlux_sso_client.settings import configure_dlux_sso


class DluxSSOClientSettingsTests(TestCase):
    def test_configure_client_is_idempotent_and_does_not_require_dlux(self):
        scope = {
            "INSTALLED_APPS": ["django.contrib.auth"],
            "MIDDLEWARE": [
                "django.contrib.sessions.middleware.SessionMiddleware",
                "django.contrib.auth.middleware.AuthenticationMiddleware",
            ],
            "AUTHENTICATION_BACKENDS": [],
        }

        configure_dlux_sso(
            scope,
            issuer_url="https://sso.example.com/",
            client_id="client-id",
            client_secret="client-secret",
            role_mapping={"staff_roles": ["admin", "staff"]},
        )
        configure_dlux_sso(
            scope,
            issuer_url="https://sso.example.com/",
            client_id="client-id",
            client_secret="client-secret",
            role_mapping={"staff_roles": ["admin", "staff"]},
        )

        self.assertEqual(scope["INSTALLED_APPS"].count("dlux_sso_client"), 1)
        self.assertNotIn("dlux", scope["INSTALLED_APPS"])
        self.assertEqual(
            scope["AUTHENTICATION_BACKENDS"][0],
            "dlux_sso_client.backends.DluxSSOAuthenticationBackend",
        )
        self.assertEqual(scope["OIDC_OP_AUTHORIZATION_ENDPOINT"], "https://sso.example.com/o/authorize/")
        self.assertTrue(scope["OIDC_USE_NONCE"])
        self.assertEqual(scope["DLUX_SSO_CLIENT"]["staff_roles"], ["admin", "staff"])

