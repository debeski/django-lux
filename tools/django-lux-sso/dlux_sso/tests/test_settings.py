from unittest import TestCase

from dlux_sso.settings import dlux_sso_settings


class DluxSSOSettingsTests(TestCase):
    def test_settings_helper_is_idempotent_and_additive(self):
        scope = {
            "DEBUG": True,
            "INSTALLED_APPS": ["django.contrib.auth", "dlux"],
            "MIDDLEWARE": [
                "django.contrib.sessions.middleware.SessionMiddleware",
                "django.contrib.auth.middleware.AuthenticationMiddleware",
            ],
        }

        dlux_sso_settings(scope)
        dlux_sso_settings(scope)

        self.assertEqual(scope["INSTALLED_APPS"].count("dlux_sso"), 1)
        self.assertEqual(scope["INSTALLED_APPS"].count("oauth2_provider"), 1)
        self.assertEqual(scope["MIDDLEWARE"].count("oauth2_provider.middleware.OAuth2TokenMiddleware"), 1)
        self.assertTrue(scope["OAUTH2_PROVIDER"]["OIDC_ENABLED"])
        self.assertEqual(
            scope["OAUTH2_PROVIDER"]["OAUTH2_VALIDATOR_CLASS"],
            "dlux_sso.validators.DluxOIDCValidator",
        )
        self.assertTrue(scope["DLUX_SSO_PROVIDER"]["allow_localhost_redirects"])

